#!/usr/bin/env python3
import struct

from penf_grain_candidate_probe import GrainJobs, JOB, TAG, set_grain
from penf_tone_transport_probe import (HL_PACKED, HL_ROWS, INITIAL_SP, acquisition,
    block, call, owner, put32, settings, u32)
from penf_creative_jobs_probe import SIZE_QUERY, SERVICE
from penf_hsl_context_probe import reenter, finished
from penf_probe import CALLER

METADATA = 0xa1c67cb4
SLOTS = 0x618689b8
PTR = 0x1a090020


def fixture(graph, profile=1, level=3, initial=0):
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
    ):
        s.ram(name, address, data)
    set_grain(s, (level,) * 3)
    call(s, graph.symbols['hl_publish'])
    address = owner(s, 0, profile)
    s.write(address+18627, b"\0")
    acquisition(s, address)
    set_grain(s, (0,) * 3)
    call(s, graph.symbols['hl_publish'])
    s.write(SLOTS + 20, struct.pack('<H', 4))
    put32(s, SLOTS + 20 + 12, address)
    call(s, 0x60525680, 0xf0, 16, d0=1, d1=1, a0=0, a1=JOB+8)
    put32(s, JOB+4, 0x6051fbcc)
    s.ram('acquired_owner_pointer', PTR, struct.pack('<I', address), aliases=False)
    put32(s, JOB+14960, initial)
    return p


def construct(p):
    s = p.s
    s.regs = dict(pc=0x604c202c, sp=INITIAL_SP, psw=0, a3=JOB)
    for _ in range(64):
        r = s.run({0x604c2032, SIZE_QUERY, SERVICE}, limit=150000)
        assert r['status'] == 'breakpoint', r
        if s.regs['pc'] == 0x604c2032:
            break
        if s.regs['pc'] == SIZE_QUERY:
            for ptr, value in zip((s.regs['a1'], s.regs['d0']), p.dimensions):
                s.write(ptr, struct.pack('<H', value))
        else:
            assert s.regs['d0'] == 13, s.regs
        s.return_from_model(1)
    else:
        raise AssertionError('constructor did not return')
    count = struct.unpack('<H', s.read(JOB+12198, 2))[0]
    return [struct.unpack('<3I', s.read(JOB+11868+12*i, 12)) for i in range(count)]


def convert(p):
    s = p.s
    put32(s, INITIAL_SP+4, JOB+36)
    block(s, 0x605205f9, 0x60520621, a0=PTR, d3=PTR)


def prepare(p):
    s = p.s
    reenter(s, 0x604c20ce, 0xf0, 104, dict(d0=JOB))
    for _ in range(64):
        r = s.run({CALLER+7, SERVICE}, limit=150000)
        assert r['status'] == 'breakpoint', r
        if s.regs['pc'] == CALLER+7:
            finished(s, r)
            return
        assert s.regs['d0'] == 11, s.regs
        s.return_from_model(0)
    raise AssertionError('preparation did not return')


def native_order_case(graph, profile=1, level=3, initial=0):
    p = fixture(graph, profile, level, initial)
    entries = construct(p)
    convert(p)
    prepare(p)
    assert p.s.read(JOB+5733, 1)[0] == level, ("strength", p.s.read(JOB+5733, 1)[0], "expected", level)
    for i, (entry, _, _) in enumerate(entries):
        p.s.write(JOB+12196, struct.pack('<H', i))
        p.run_job(entry)
    expected = [0] if level == 0 else [0x900, 0x901, 0xf005, 0]
    assert [int(r['stage'], 16) for r in p.requests] == expected
    if level:
        assert bytes.fromhex(p.requests[1]['request_hex'])[1088] == level
    return p
