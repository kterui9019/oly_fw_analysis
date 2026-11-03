#!/usr/bin/env python3
"""Run native recording selection and conversion with bounded capture fixtures."""
if not __debug__:
    raise RuntimeError('Recording grain verification requires assertions')

import argparse
from dataclasses import replace
import hashlib
from itertools import product
import json
from pathlib import Path
import struct

from penf_creative_jobs_probe import JOB
from penf_emulator import BASE, firmware
from penf_grain_candidate_probe import GrainJobs, TAG, set_grain
from penf_hsl_context_probe import reenter, finished
from penf_probe import CALLER
from penf_tone_graph_candidate import GraphCandidate, build_graph
from penf_tone_transport_probe import (
    HL_ROWS, HL_PACKED, settings, call, acquisition, put32, u32,
)

DESCRIPTOR, PARAMS, CAPTURE, COMPANION = 0x2e000000, 0x2d000000, 0xadafa3c0, 0x19030000
CALLBACK, LOG = 0x605335e3, 0x6052face
LIMITS = [
    'Capture fields, recording descriptor, and memory regions are synthetic inputs.',
    'Native recording producer, constructor selection, and converter execute; heap allocation, diagnostic logging, and physical buffer lookup are modeled.',
    'Selection executes native dimension and service paths without replacing their results.',
    'Conversion stops at native preparation; the strength helper then executes separately.',
    'No full boot, scheduler timing, ISP execution, JPEG pixels, or physical camera result is claimed.',
]


def fixture(graph, profile=1, level=3, mode=11):
    p = GrainJobs(graph, mode=mode, level=0, fmt=0x105, shading=0)
    s = p.s
    p.recording_models = []
    settings(s)
    for name, address, data in (
        ('hl_source', graph.symbols['hl_profile_source'], HL_PACKED),
        ('tone_source', graph.symbols['tone_source'], bytes(60)),
        ('hl_rows', HL_ROWS, bytes(540)),
        ('tone_rows', graph.symbols['tone_rows'], bytes(720)),
        ('grain_rows', graph.symbols['grain_rows'], bytes(180)),
        ('recording_descriptor', DESCRIPTOR, bytes(512)),
        ('recording_header', PARAMS, bytes(64)),
        ('capture_parameters', CAPTURE, bytes(22080)),
        ('constructor_companion', COMPANION, bytes(5624)),
        ('recording_parent', 0x2c000000, bytes(4)),
        ('recording_copy_workspace', 0x618b9fdc, bytes(3*204)),
        ('recording_diagnostic_state', 0x618b9fac, bytes(6)),
        ('record_directory_override_disabled', 0xa1c281e0, bytes(4)),
        ('native_fixed_record_directory', 0xa1c281e4, bytes(32768)),
        ('native_conversion_table', 0xa1c5854c, bytes(368)),
    ):
        s.ram(name, address, data)
    put32(s, DESCRIPTOR+4, 0x2c000000)
    put32(s, DESCRIPTOR+24, 16)
    s.write(DESCRIPTOR+68, struct.pack('<H', 0x1001))
    s.write(DESCRIPTOR+120, struct.pack('<III', 1, CAPTURE, JOB))
    s.write(DESCRIPTOR+136, b'\x01')
    s.write(DESCRIPTOR+210, struct.pack('<H', 256))
    s.write(CAPTURE+18572, struct.pack('<H', 3))
    s.write(CAPTURE+18595, bytes([mode]))
    s.write(CAPTURE+18625, bytes([profile]))
    s.write(CAPTURE+19072, b'\x0c')
    s.write(CAPTURE+21942, struct.pack('<4H', 0, 0, 5184, 3888))
    s.ram('capture_slot_1', 0x618689b8+20,
          struct.pack('<6HIHH', 5, 0x101, 0, 0, 0, 0x201, CAPTURE, 0, 0))
    for entry, mask, frame, registers in (
        (0x6052f9f9, 0, 0, {}),
        (0x600746d9, 0, 0, dict(a0=0xa1c281e4, d0=4096)),
        *((0x60074640, 0xf0, 44, dict(a0=table, a1=0, d0=0xa1c281e4))
          for table in (0x60096820, 0x600a82a0, 0x60109350, 0x600a9fc4)),
        (0x6023463e, 0xf0, 32, {}),
    ):
        reenter(s, entry, mask, frame, registers)
        finished(s, s.run({CALLER+7}, limit=500000))
    set_grain(s, (level,)*3)
    call(s, graph.symbols['hl_publish'])
    acquisition(s, CAPTURE)
    assert u32(s, graph.symbols['grain_rows']) == TAG | level
    set_grain(s, ((level+1) % 4,)*3)
    call(s, graph.symbols['hl_publish'])
    return p


def omit_log(p):
    p.recording_models.append(dict(model='diagnostic logging', return_pc=hex(p.s.regs['mdr'])))
    p.s.return_from_model(0)


def construct(p, mode=11):
    s = p.s
    reenter(s, 0x60531e16, 0xf0, 24, dict(a0=DESCRIPTOR, a1=PARAMS))
    for _ in range(8):
        result = s.run({CALLER+7, LOG}, limit=500000)
        assert result['status'] == 'breakpoint', result
        if s.regs['pc'] == CALLER+7:
            break
        omit_log(p)
    finished(s, result)
    assert u32(s, PARAMS) == CALLBACK
    assert u32(s, PARAMS+4) == DESCRIPTOR
    assert struct.unpack('<BBH', s.read(PARAMS+8, 4)) == (0, 0, mode)
    reenter(s, 0x604c1c0a, 0xf0, 40, dict(a0=PARAMS, a1=PARAMS+40, d0=0))
    for _ in range(16):
        result = s.run({0x604c202c, 0x600233bd, LOG}, limit=500000)
        assert result['status'] == 'breakpoint', result
        if s.regs['pc'] == 0x604c202c:
            break
        if s.regs['pc'] == LOG:
            omit_log(p)
        else:
            size = s.regs['d0']
            assert size in (14964, 5624), size
            p.recording_models.append(dict(model='heap allocation', size=size))
            s.regs['a0'] = JOB if size == 14964 else COMPANION
            s.return_from_model(0)
    assert s.regs['pc'] == 0x604c202c, 'constructor did not reach selection'
    assert (u32(s, JOB+4), u32(s, JOB+8), u32(s, JOB+12192)) == (CALLBACK, DESCRIPTOR, mode)
    for _ in range(32):
        result = s.run({0x604c2032, LOG}, limit=500000)
        assert result['status'] == 'breakpoint', result
        if s.regs['pc'] == 0x604c2032:
            break
        omit_log(p)
    assert s.regs['pc'] == 0x604c2032, 'selection did not return'
    assert s.regs['d0'] == 0, s.regs
    count = struct.unpack('<H', s.read(JOB+12198, 2))[0]
    return [struct.unpack('<3I', s.read(JOB+11868+12*i, 12)) for i in range(count)]


def convert(p):
    s = p.s
    reenter(s, 0x60531fdb, 0xf0, 76, dict(a0=DESCRIPTOR))
    for _ in range(100):
        result = s.run({0x604c20ce, LOG, 0x60548b10}, limit=500000)
        assert result['status'] == 'breakpoint', result
        if s.regs['pc'] == 0x604c20ce:
            break
        if s.regs['pc'] == LOG:
            omit_log(p)
        else:
            handle = s.regs['d0']
            assert handle in (0x101, 0x201), handle
            p.recording_models.append(dict(model='physical buffer lookup', handle=hex(handle)))
            s.return_from_model(0x40000000 if handle == 0x101 else 0x41000000)
    assert s.regs['pc'] == 0x604c20ce, 'converter did not reach preparation'
    assert s.read(DESCRIPTOR+163, 1) == b'\x01'


def recording_case(graph, profile=1, level=3, reacquire=False):
    p = fixture(graph, profile, level)
    s = p.s
    entries = construct(p)
    captured = u32(s, JOB+14960)
    assert captured == TAG | level, f'constructor grain {captured:#x}, expected {TAG | level:#x}'
    expected = [(0x604c81db, 0, 0), (0x604c82eb, 0, 0), (0x604c971e, 0, 0)] if level else [
        (0x604c4c84, 0x604c9168, 0)]
    assert entries == expected, entries
    if reacquire:
        acquisition(s, CAPTURE)
        assert u32(s, graph.symbols['grain_rows']) == TAG | ((level+1) % 4)
    convert(p)
    assert u32(s, JOB+14960) == captured, 'recording conversion replaced the captured grain'
    assert struct.unpack('<H', s.read(JOB+12198, 2))[0] == len(entries)
    call(s, graph.symbols['grain_prepare_strength'], a0=JOB)
    assert s.read(JOB+5733, 1)[0] == level
    return dict(profile=profile, level=level, reacquire=reacquire,
                captured_word=hex(captured), entries=entries, prepared_strength=level,
                models=p.recording_models)


def recording_matrix(graph):
    return [recording_case(graph, profile, level, reacquire)
            for profile, level, reacquire in product((1, 2, 3), range(4), (False, True))]


def invalid_cases(graph):
    for mode, callback, context, owner in (
        (1, CALLBACK, 0x12345678, CAPTURE), (12, CALLBACK, 0x12345678, CAPTURE),
        (11, 0, 0x12345678, CAPTURE), (11, CALLBACK, 0, CAPTURE),
        (11, CALLBACK, DESCRIPTOR, 0), (11, CALLBACK, DESCRIPTOR, CAPTURE+1),
        (11, CALLBACK, DESCRIPTOR, 0x12345678),
    ):
        p = fixture(graph)
        s = p.s
        put32(s, JOB+4, callback)
        put32(s, JOB+8, context)
        put32(s, JOB+12192, mode)
        put32(s, DESCRIPTOR+124, owner)
        put32(s, JOB+14960, 0xffffffff)
        call(s, graph.symbols['grain_constructor_snapshot'], a3=JOB)
        assert u32(s, JOB+14960) == 0, (mode, callback, context, owner)


def other_mode_cases(graph):
    image = bytearray(graph.image)
    image[0x604c202d-BASE:0x604c2032-BASE] = bytes.fromhex('cd220ab010')
    native_constructor = replace(graph, image=bytes(image))
    for mode in (1, 12):
        observations = []
        for candidate in (native_constructor, graph):
            p = fixture(candidate, mode=mode)
            entries = construct(p, mode)
            selected = p.s.read(JOB, 14964)
            convert(p)
            observations.append((entries, selected, p.s.read(JOB, 14964)))
        assert observations[0] == observations[1], f'recording mode {mode} changed'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--candidate', type=Path, help='existing graph directory; otherwise build into output/candidate')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.candidate:
        image = (args.candidate/'main.bin').read_bytes()
        manifest = json.loads((args.candidate/'placement.json').read_text())
        assert hashlib.sha256(image).hexdigest() == manifest['candidate_sha256']
        graph = GraphCandidate(None, None, image, {k: int(v, 16) for k, v in manifest['symbols'].items()}, {})
    else:
        graph = build_graph(args.output/'candidate')
    report = dict(candidate_sha256=hashlib.sha256(graph.image).hexdigest(),
                  firmware_sha256=hashlib.sha256(firmware()).hexdigest(),
                  cases=recording_matrix(graph), limits=LIMITS)
    invalid_cases(graph)
    other_mode_cases(graph)
    (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f"Recording route passed {len(report['cases'])} capture cases and invalid-context controls")
