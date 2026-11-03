#!/usr/bin/env python3
"""Differential native checks for the five resident grain observations."""
if not __debug__:
    raise RuntimeError('Grain diagnostic verification requires assertions')

import json
from pathlib import Path
import struct

from penf_emulator import BASE
from penf_hsl_context_probe import reenter
from penf_probe import CALLER, ProbeState
from penf_tone_candidate import GRAIN_DIAGNOSTIC
from penf_tone_transport_probe import INITIAL_SP, REFERENCE_REGS

TAG = 0xf7524e00
CONTEXT = 0x19000000
REQUEST = 0x19004000
ROW = 0x19008000
JOB = 0x19009000


def baseline(path):
    path = Path(path)
    return (path.joinpath('main.bin').read_bytes(),
            {k: int(v, 16) for k, v in json.loads(path.joinpath('placement.json').read_text())['symbols'].items()})


def run(image, names, site, *, level=3, mode=11, kind=0, stage=0x901, initial=b'\0'*5):
    from dataclasses import replace
    s = ProbeState(CALLER, 0, 4, bytes(16), {})
    s.regions = [replace(r, data=image) if r.name == 'main' else r for r in s.regions]
    s.ram('diagnostic', GRAIN_DIAGNOSTIC, initial)
    context = bytearray(16000)
    struct.pack_into('<I', context, 12192, mode)
    struct.pack_into('<I', context, 14960, TAG | level)
    request = bytearray(1200)
    struct.pack_into('<HH', request, 10, mode, stage)
    request[16], request[1088] = kind, level
    s.ram('context', CONTEXT, context, aliases=False)
    s.ram('request', REQUEST, request, aliases=False)
    s.ram('pointer', ROW, struct.pack('<I', REQUEST), aliases=False)
    s.ram('job', JOB, bytes(128), aliases=False)
    s.ram('tone_rows', names['tone_rows'], bytes(720))
    s.ram('grain_rows', names['grain_rows'], bytes(180))
    s.ram('grain_source', names['grain_source'], struct.pack('<3I', TAG | level, 0, 0))
    if site == 'grain_acquire':
        regs = dict(d0=0, a0=0x12345678, a1=names['tone_rows'] + 0x40000000)
        stops = {CALLER + 7}
        reenter(s, names[site], 0, 4, dict(REFERENCE_REGS, **regs))
    elif site == 'grain_to_job':
        s.write(names['grain_rows'], struct.pack('<I', TAG | level))
        regs = dict(a0=names['tone_rows'] + 0x40000000, a2=JOB)
        stops = {CALLER + 7}
        reenter(s, names[site], 0, 4, dict(REFERENCE_REGS, **regs))
    elif site == 'grain_select':
        s.regs = dict(REFERENCE_REGS, pc=names[site], sp=INITIAL_SP, psw=0x80000000, a0=CONTEXT)
        stops = {0x604c5c46, 0x604c5d33, 0x604c58a7}
    elif site == 'grain_queue':
        s.regs = dict(REFERENCE_REGS, pc=names[site], sp=INITIAL_SP, psw=0x80000000, a0=CONTEXT, a1=REQUEST)
        stops = {0x604c2f1d}
    else:
        s.regs = dict(REFERENCE_REGS, pc=names[site], sp=INITIAL_SP, psw=0x80000000, d0=mode, a2=ROW)
        stops = {0x604fb918, 0x604fb887}
    result = s.run(stops, limit=5000)
    assert result['status'] == 'breakpoint', (site, result)
    return s, bytes(s.read(GRAIN_DIAGNOSTIC, 5))


def compare(old, new, site, **kwargs):
    before, after = (run(*x, site, **kwargs) for x in (old, new))
    a, b = before[0], after[0]
    exclude = {'a0', 'a1'} if site == 'grain_to_job' else set()
    if site == 'grain_to_job':
        assert a.regs['a0'] - old[1]['tone_rows'] == b.regs['a0'] - new[1]['tone_rows']
        assert a.regs['a1'] - old[1]['grain_rows'] == b.regs['a1'] - new[1]['grain_rows']
    if site == 'grain_acquire':
        exclude.add('a1')
        assert a.regs['a1'] - old[1]['tone_rows'] == b.regs['a1'] - new[1]['tone_rows']
    if site == 'grain_select':
        exclude.add('mdr')
        assert a.regs['mdr'] - old[1][site] == b.regs['mdr'] - new[1][site]
    assert {k:v for k,v in a.regs.items() if k not in exclude} == {k:v for k,v in b.regs.items() if k not in exclude}, (site, kwargs, a.regs, b.regs)
    assert a.read(REQUEST, 1200) == b.read(REQUEST, 1200)
    assert a.read(JOB, 128) == b.read(JOB, 128)
    assert a.read(old[1]['grain_rows'], 180) == b.read(new[1]['grain_rows'], 180)
    assert a.read(CONTEXT, 16000) == b.read(CONTEXT, 16000)
    return after[1]


def observers(old, new):
    sites = ('grain_acquire', 'grain_to_job', 'grain_select', 'grain_queue', 'grain_combiner')
    for index, site in enumerate(sites):
        for level in (0, 1, 2, 3, 4):
            initial = bytes(0 if i == index else 1 for i in range(5))
            result = compare(old, new, site, level=level, stage=0x900 if index == 3 else 0x901, initial=initial)
            expected = bytearray(initial)
            expected[index] = int(level == 3)
            assert result == bytes(expected), (site, level, result, expected)
        if index >= 2:
            for mode in (1, 12):
                assert compare(old, new, site, mode=mode, stage=0x900 if index == 3 else 0x901) == bytes(5)
        if index >= 3:
            assert compare(old, new, site, kind=1, stage=0x900 if index == 3 else 0x901) == bytes(5)
        if index == 3:
            for stage in (0x901, 0x902, 0xf005):
                assert compare(old, new, site, stage=stage) == bytes(5)
            assert compare(old, new, site, stage=0x900) == b'\0\0\0\1\0'
        if index == 4:
            for stage in (0x900, 0xf005):
                assert compare(old, new, site, stage=stage) == bytes(5)
            assert compare(old, new, site, stage=0x902) == b'\0\0\0\0\1'
        assert compare(old, new, site, stage=0x900 if index == 3 else 0x901, initial=b'\1'*5) == b'\1'*5


def footers(graph):
    from dataclasses import replace
    from itertools import product
    from penf_grain_candidate_probe import set_grain
    from penf_tone_editor_probe import fixture, actuator, current, mode, ACTUATOR
    from penf_tone_transport_probe import call

    s = fixture(graph.base, replace(graph.editor, image=graph.image))
    controller, output = 0x19110000, 0x19120010
    s.ram('diagnostic_controller', controller, struct.pack('<I', ACTUATOR), aliases=False)
    s.ram('diagnostic_current_controller', 0x6161b810, struct.pack('<I', controller))
    s.ram('diagnostic_footer', output-16, b'\xa5'*16 + bytes(92) + b'\x5a'*16, aliases=False)
    mode(s, 54)
    current(s, 1, (0, 0, 0))
    actuator(s, 1, 12)
    for level in range(4):
        set_grain(s, (level,)*3)
        for bits in product((0, 1), repeat=5):
            s.write(graph.symbols['grain_diagnostic'], bytes(bits))
            s.write(output, b'\xa6'*92)
            call(s, graph.symbols['tone_footer'], 0, 0, a0=output)
            payload = s.read(output, 92)
            label = payload[18:].decode('utf-16le').split('\0')[0]
            assert label == f"Grain {('Off', 'Low', 'Medium', 'High')[level]} R{''.join(map(str, bits))} @A028@", label
            assert payload[3] == int(level != 0) and payload[5] == 1
            assert struct.unpack_from('<H', payload, 10)[0] == 5
            assert s.read(output-16, 16) == b'\xa5'*16
            assert s.read(output+92, 16) == b'\x5a'*16
            assert s.read(graph.symbols['grain_diagnostic'], 5) == bytes(bits)


def requests(old, new):
    from itertools import product
    from types import SimpleNamespace
    from penf_grain_candidate_probe import GrainJobs

    graphs = []
    for image, symbols in (old, new):
        symbols = dict(symbols, grain_diagnostic=GRAIN_DIAGNOSTIC)
        graphs.append(SimpleNamespace(image=image, symbols=symbols))
    for mode, level, alternate, fmt in product((11, 12), (0, 3), (0, 1), (0x105, 0x205)):
        results = [GrainJobs(graph, mode=mode, level=level, alternate=alternate, fmt=fmt).all_jobs()
                   for graph in graphs]
        for key in ('fixture', 'requests', 'models', 'dependency_chain_verified',
                    'original_source_preserved', 'live_allocations_at_submission_end'):
            assert results[0][key] == results[1][key], (mode, level, alternate, fmt, key)
        assert [{k:v for k,v in job.items() if k != 'instructions'} for job in results[0]['jobs']] == [
            {k:v for k,v in job.items() if k != 'instructions'} for job in results[1]['jobs']]


def lifetime(image):
    from dataclasses import replace
    from penf_code_space_load_probe import load
    from penf_emulator import ROOT

    sections = json.loads((ROOT/'analysis/preset_startup_final/audit.json').read_text())['startup_sections']
    section1 = next(row for row in sections if row['id'] == 1)
    section8 = dict(next(row for row in sections if row['id'] == 8), end_exclusive='0x6115c800')
    assert struct.unpack_from('<I', image, 0x6004211d-BASE)[0] == 0x6115c800
    s = ProbeState(0x600421e1, 0, 0, bytes(16), {})
    s.regions = [replace(r, data=image) if r.name == 'main' else r for r in s.regions]
    s.ram('section_selection', 0x61c583fc, struct.pack('<I', 1)+bytes(8))
    for section in (section1, section8):
        low, high = (int(section[k], 16) for k in ('destination', 'end_exclusive'))
        s.ram('section'+str(section['id']), low, b'\xa5'*(high-low), executable=True)
    load(s, section1, image)
    assert s.read(GRAIN_DIAGNOSTIC, 5) == bytes(5)
    s.write(GRAIN_DIAGNOSTIC, b'\1'*5)
    s.write(0x61c583fc, struct.pack('<I', 8))
    load(s, section8, image)
    assert s.read(GRAIN_DIAGNOSTIC, 5) == b'\1'*5
    s.write(0x61c583fc, struct.pack('<I', 1))
    load(s, section1, image)
    assert s.read(GRAIN_DIAGNOSTIC, 5) == bytes(5)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', help='built pre-diagnostic graph directory')
    parser.add_argument('candidate', help='built diagnostic graph directory')
    args = parser.parse_args()
    old, new = baseline(args.baseline), baseline(args.candidate)
    observers(old, new)
    requests(old, new)
    lifetime(new[0])
    print('Observer, request differential, and loader lifetime checks passed')
