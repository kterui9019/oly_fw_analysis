#!/usr/bin/env python3
import struct
from dataclasses import replace
from itertools import product

from penf_emulator import BASE

from penf_grain_candidate_probe import GrainJobs, JOB, TAG, set_grain
from penf_tone_transport_probe import (HL_PACKED, HL_ROWS, INITIAL_SP, acquisition,
    block, call, owner, put32, settings, u32)
from penf_creative_jobs_probe import SIZE_QUERY, SERVICE
from penf_hsl_context_probe import reenter, finished
from penf_probe import CALLER

METADATA = 0xa1c67cb4
SLOTS = 0x618689b8
PTR = 0x1a090020


def fixture(graph, profile=1, level=3, initial=0, slot=1, logical=1):
    p = GrainJobs(graph, mode=11, level=0, fmt=0x105)
    s = p.s
    settings(s)
    for name, address, data in (
        ('hl_source', graph.symbols['hl_profile_source'], HL_PACKED),
        ('tone_source', graph.symbols['tone_source'], bytes(60)),
        ('hl_rows', HL_ROWS, bytes(540)),
        ('tone_rows', graph.symbols['tone_rows'], bytes(720)),
        ('grain_rows', graph.symbols['grain_rows'], bytes(180)),
        ('metadata', METADATA, bytes(180)),
        ('slots', SLOTS, bytes(41 * 20)),
        ('processing_lock', 0x8ff001b0, bytes(4)),
        ('processing_atomic', 0x8fe00006, bytes(2)),
        ('processing_cache', 0xa1c621f8, bytes(400)),
        ('processing_policy', 0x618b510e, bytes(2)),
        ('heap_large_bitmap', 0xa1c556b4, bytes(16)),
        ('heap_small_bitmap', 0xa1c5569c, bytes(24)),
        ('heap_cursor', 0xa1c554c8, struct.pack('<I', 0xffffffff)),
        ('initializer_buffer', 0x30000000, bytes(0x40000)),
    ):
        s.ram(name, address, data)
    call(s, 0x604fa059, 0x80, 4)
    set_grain(s, (level,) * 3)
    call(s, graph.symbols['hl_publish'])
    address = owner(s, slot - 1, profile, alias=bool(slot % 2))
    s.write(address + 18627, b'\x00')
    acquisition(s, address)
    set_grain(s, ((3 if level == 0 else 0),) * 3)
    call(s, graph.symbols['hl_publish'])
    s.write(SLOTS + 20 * slot, struct.pack('<H', 4))
    put32(s, SLOTS + 20 * slot + 12, address)
    call(s, 0x60525680, 0xf0, 16, d0=logical, d1=slot, a0=0, a1=JOB+8)
    put32(s, JOB+4, 0x6051fbcc)
    s.ram('acquired_owner_pointer', PTR, struct.pack('<I', address), aliases=False)
    put32(s, JOB+14960, initial)
    return p


def construct(p, job=JOB):
    s = p.s
    s.regs = dict(pc=0x604c202c, sp=INITIAL_SP, psw=0, a3=job)
    p.lookup_count = p.selection_calls = 0
    for _ in range(64):
        r = s.run({0x604c2032, SIZE_QUERY, SERVICE, 0x60249c22, 0x600241b5, 0x604c2a4f}, limit=150000)
        assert r['status'] == 'breakpoint', r
        if s.regs['pc'] == 0x604c2032:
            break
        if s.regs['pc'] in (0x60249c22, 0x604c2a4f):
            if s.regs['pc'] == 0x60249c22: p.lookup_count += 1
            else: p.selection_calls += 1
            step = s.run({0x604c2032, SIZE_QUERY, SERVICE, 0x600241b5}, limit=1)
            assert step['status'] == 'instruction_limit'
            continue
        assert s.regs['pc'] != 0x600241b5, 'unexpected native diagnostic logging'
        if s.regs['pc'] == SIZE_QUERY:
            for ptr, value in zip((s.regs['a1'], s.regs['d0']), p.dimensions):
                s.write(ptr, struct.pack('<H', value))
        else:
            assert s.regs['d0'] == 13, s.regs
        s.return_from_model(1)
    else:
        raise AssertionError('constructor did not return')
    assert p.selection_calls == 1, f'selection called {p.selection_calls} times'
    count = struct.unpack('<H', s.read(job+12198, 2))[0]
    return [struct.unpack('<3I', s.read(job+11868+12*i, 12)) for i in range(count)]


def convert(p):
    s = p.s
    put32(s, INITIAL_SP+4, JOB+36)
    block(s, 0x605205f9, 0x60520621, a0=PTR, d3=PTR)


def initialize(p):
    s = p.s
    reenter(s, 0x604c2b5b, 0x20, 8, dict(a0=JOB, a1=0))
    hooks = {CALLER+7, SERVICE, 0x600233f9, 0x60086c0b, 0x60070bc0, 0x60070cb1, 0x60086c54}
    pcs = (0x60086c0b, 0x60070bc0, 0x60070cb1, 0x60086c54)
    callers = {'allocate': (0x600235a7, 0x600235b8, 0x600235c4, 0x600235cc),
               'free': (0x600235db, 0x600235ec, 0x600235f8, 0x60023600)}
    arguments = (1, 0x0a09000a, 10, 0x2400)
    results = (0x2400, 10, 0, 0)
    phase, heap_kind = 0, None
    mapped = set()
    for _ in range(128):
        r = s.run(hooks, limit=1500000)
        assert r['status'] == 'breakpoint', (r['status'], r.get('fault'))
        pc = s.regs['pc']
        if pc == CALLER+7:
            finished(s, r)
            assert s.regs['d0'] == 0 and phase == 0, s.regs
            return
        if pc == SERVICE:
            assert s.regs['d0'] == 18 and s.regs['a0'] == JOB+4, s.regs
            assert 0xa1c621f8 <= s.regs['a1'] < 0xa1c621f8 + 400, s.regs
            put32(s, s.regs['a1'] + 64, 0x30000000)
            s.return_from_model(1)
        elif pc == 0x600233f9:
            address = s.regs['a0']
            if address and address not in mapped:
                assert 0x6122a540 <= address < 0x6122a540 + 64 * 0x4040, hex(address)
                s.ram('initializer_heap_' + hex(address), address, bytes(16384))
                mapped.add(address)
            step = s.run(hooks - {pc}, limit=1)
            assert step['status'] == 'instruction_limit'
        else:
            if phase == 0:
                heap_kind = {0x600235a7: 'allocate', 0x600235db: 'free'}[s.regs['mdr']]
            assert (pc, s.regs['mdr'], s.regs['d0']) == (pcs[phase], callers[heap_kind][phase], arguments[phase]), s.regs
            if phase == 1: assert s.regs['d1'] == 255
            result = results[phase]
            phase = (phase + 1) % 4
            s.return_from_model(result)
    raise AssertionError('initializer did not return')


def prepare(p):
    s = p.s
    reenter(s, 0x604c20ce, 0xf0, 104, dict(d0=JOB))
    calls = 0
    for _ in range(64):
        r = s.run({CALLER+7, SERVICE, 0x604be99a}, limit=150000)
        assert r['status'] == 'breakpoint', r
        if s.regs['pc'] == CALLER+7:
            finished(s, r)
            assert calls == 1, f'preparation native call count {calls}'
            return
        if s.regs['pc'] == 0x604be99a:
            calls += 1
            step = s.run({CALLER+7, SERVICE}, limit=1)
            assert step['status'] == 'instruction_limit'
            continue
        assert s.regs['d0'] == 11, s.regs
        s.return_from_model(0)
    raise AssertionError('preparation did not return')


def native_order_case(graph, profile=1, level=3, initial=0, *, resource_init=True):
    p = fixture(graph, profile, level, initial)
    entries = construct(p)
    if resource_init:
        initialize(p)
    convert(p)
    prepare(p)
    actual = p.s.read(JOB+5733, 1)[0]
    assert actual == level, f'prepared strength {actual}, expected {level}'
    for i, (entry, _, _) in enumerate(entries):
        p.s.write(JOB+12196, struct.pack('<H', i))
        p.run_job(entry)
    expected = [0] if level == 0 else [0x900, 0x901, 0xf005, 0]
    actual = [int(r['stage'], 16) for r in p.requests]
    assert actual == expected, f'stages {actual}, expected {expected}'
    if level:
        assert bytes.fromhex(p.requests[1]['request_hex'])[1088] == level
    return p


def order_matrix(graph):
    for profile, level in product((1, 2, 3), range(4)):
        p = native_order_case(graph, profile, level, initial=0xffffffff, resource_init=False)
        assert u32(p.s, JOB+14960) == TAG | level
        if level:
            from penf_grain_candidate_probe import engine_controls
            from penf_grain_probe import GAINS
            control = engine_controls(graph, p.requests[1])
            assert p.requests[0]['outputs'][0]['pointer'] == p.requests[1]['mask']['pointer']
            assert p.requests[0]['source'] == p.requests[1]['source']
            for previous, current in zip(p.requests, p.requests[1:]):
                assert current['dependency_token'] == previous['assigned_token']
            assert control['combiner'] == 31
            assert control['gain'] == GAINS[0x901][level]
            assert len(control['uploads']) == 2


def negative_controls(graph):
    image = bytearray(graph.image)
    for at, code in ((0x604c202d, 'cd220ab010'), (0x604c20d2, 'cdc8c8a00c')):
        image[at-BASE:at-BASE+5] = bytes.fromhex(code)
    old = replace(graph, image=bytes(image))
    for early in (False, True):
        p = fixture(old, initial=TAG | 3 if early else 0)
        entries = construct(p)
        convert(p)
        prepare(p)
        for i, (entry, _, _) in enumerate(entries):
            p.s.write(JOB+12196, struct.pack('<H', i))
            p.run_job(entry)
        stages = [int(r['stage'], 16) for r in p.requests]
        expected = [0x900, 0x901, 0xf005, 0] if early else [0]
        assert stages == expected, f'negative control stages {stages}, expected {expected}'
        strength = bytes.fromhex(p.requests[1 if early else 0]['request_hex'])[1088]
        assert strength == 0, f'negative control strength {strength}, expected 0'


def slot_cases(graph):
    for slot in range(1, 41):
        p = fixture(graph, profile=(slot-1) % 3 + 1, level=3, initial=0xffffffff, slot=slot)
        construct(p)
        assert u32(p.s, JOB+14960) == TAG | 3, f'slot {slot}'


def invalid_cases(graph):
    cases = ('callback', 'mode', 'before', 'after', 'unaligned', 'inactive',
             'index_zero', 'index_high', 'unowned', 'owner_invalid')
    for case in cases:
        p = fixture(graph, initial=0xffffffff)
        s = p.s
        if case == 'callback': put32(s, JOB+4, 0)
        elif case == 'mode': put32(s, JOB+12192, 10)
        elif case == 'before': put32(s, JOB+8, METADATA-1)
        elif case == 'after': put32(s, JOB+8, METADATA+180)
        elif case == 'unaligned': put32(s, JOB+8, METADATA+1)
        elif case == 'inactive': s.write(METADATA+12, b'\x00')
        elif case == 'index_zero': put32(s, METADATA+8, 0)
        elif case == 'index_high': put32(s, METADATA+8, 41)
        elif case == 'unowned': s.write(SLOTS+20, b'\x00\x00')
        elif case == 'owner_invalid': put32(s, SLOTS+32, 0x12345678)
        construct(p)
        assert u32(s, JOB+14960) == 0, case
        assert p.lookup_count == (1 if case == 'owner_invalid' else 0), case


def neutral_abi_cases(graph):
    from penf_recovery_isolation_probe import without_ranges
    image = bytearray(graph.image)
    for at, code in ((0x604c202d, 'cd220ab010'), (0x604c20d2, 'cdc8c8a00c')):
        image[at-BASE:at-BASE+5] = bytes.fromhex(code)
    old = replace(graph, image=bytes(image))
    for mode, loaded in product((11, 12), (False, True)):
        probes = []
        for candidate in (old, graph):
            p = fixture(candidate, initial=0)
            s = p.s
            put32(s, JOB+4, 0)
            put32(s, JOB+12192, mode)
            s.write(0x61c58404, bytes([0xa4 if loaded else 4]))
            if not loaded:
                s.regions = [r for r in s.regions if not r.name.startswith(('tone_rows', 'grain_rows'))]
                s.regions = without_ranges(s.regions, [(0x6115b014, 0x6115c800), (0xa115b014, 0xa115c800)])
            entries = construct(p)
            constructor = dict(s.regs)
            job_after_constructor = s.read(JOB, 14964)
            prepare(p)
            preparation = dict(s.regs)
            probes.append((entries, constructor, job_after_constructor, preparation, s.read(JOB, 14964)))
        assert probes[0] == probes[1], f'neutral ABI differs: mode={mode}, loaded={loaded}'


def owner_reuse_case(graph):
    p = fixture(graph, level=3)
    s = p.s
    second = 0x1b000000
    s.ram('second_job', second, s.read(JOB, 14964), aliases=False)
    entries = construct(p)
    assert u32(s, JOB+14960) == TAG | 3
    address = u32(s, SLOTS+32)
    set_grain(s, (1, 1, 1))
    call(s, graph.symbols['hl_publish'])
    acquisition(s, address)
    call(s, 0x60525680, 0xf0, 16, d0=2, d1=1, a0=0, a1=second+8)
    construct(p, second)
    assert u32(s, second+14960) == TAG | 1
    convert(p)
    prepare(p)
    assert u32(s, JOB+14960) == TAG | 3
    for i, (entry, _, _) in enumerate(entries):
        s.write(JOB+12196, struct.pack('<H', i))
        p.run_job(entry)
    strength = bytes.fromhex(p.requests[1]['request_hex'])[1088]
    assert strength == 3, f'held job submitted strength {strength}, expected 3'


def metadata_cases(graph):
    for logical in range(1, 10):
        p = fixture(graph, logical=logical)
        construct(p)
        assert u32(p.s, JOB+14960) == TAG | 3, f'metadata record {logical}'
        assert p.lookup_count == 1, f'owner lookup count for record {logical}'


def copy_guard_cases(graph):
    from penf_tone_transport_probe import setup
    from penf_tone_integration_probe import JOB as target
    s = setup(graph.base)
    settings(s)
    set_grain(s, (2, 2, 2))
    call(s, graph.symbols['hl_publish'])
    address = owner(s, 42, 1)
    acquisition(s, address, True)
    put32(s, target+4, 0x6051fbcc)
    put32(s, target+12192, 11)
    put32(s, target+14960, TAG | 3)
    call(s, graph.symbols['hl_owner_to_job'], a0=address, a2=target+14920)
    assert u32(s, target+14960) == TAG | 2, 'compact copy must update capture-tagged job'
    large = owner(s, 0, 1)
    acquisition(s, large)
    put32(s, target+14960, 0xffffffff)
    call(s, graph.symbols['hl_owner_to_job'], a0=large, a2=target+14920)
    assert u32(s, target+14960) == TAG | 2, 'invalid trailer must be replaced'
    put32(s, target+14960, TAG)
    call(s, graph.symbols['hl_owner_to_job'], a0=large, a2=target+14920)
    assert u32(s, target+14960) == TAG, 'captured Off must survive owner reuse'
    call(s, graph.symbols['hl_owner_to_job'], a0=0x12345678, a2=target+14920)
    assert u32(s, target+14960) == 0, 'invalid owner must clear capture-tagged job'
