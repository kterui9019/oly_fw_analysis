#!/usr/bin/env python3
"""Execute the acquired COLOR grain candidate with native CPU instructions."""
if not __debug__:
    raise RuntimeError('Grain verification requires assertions')

import argparse
from dataclasses import replace
from itertools import product
import json
from pathlib import Path
import struct

from penf_emulator import BASE, firmware
from penf_shading_candidate import apply_shading
from penf_probe import CALLER, RESULT
from penf_hsl_context_probe import reenter
from penf_tone_graph_candidate import build_graph
from penf_tone_transport_probe import (setup, settings, call, put32, u32, owner,
    acquisition, to_job, ACTIVE, WORDS, stopped, INITIAL_SP, PRESERVED)
from penf_tone_editor_probe import fixture, actuator, current, mode, ACTUATOR
from penf_creative_jobs_probe import JobProbe, JOB, QUEUE
from penf_tone_integration_probe import JOB as SNAPSHOT_JOB
from penf_grain_probe import fixture as engine_fixture, complete, Q, O, C, ICM, GAINS, M, upload

TAG = 0xf7524e00
IDS = (985, 986, 987)


def set_grain(s, levels):
    for setting, level in zip(IDS, levels):
        call(s, 0x602f0710, 0x80, 8, d0=setting, d1=1, a0=TAG | level)


def decode_cases(graph):
    s = setup(graph.base)
    values = [0, 1, 3, 0xffffffff, TAG - 1, TAG + 4, *range(TAG, TAG + 4)]
    for word in values:
        call(s, graph.symbols['grain_decode'], d0=word)
        assert s.regs['d0'] == (word & 3 if TAG <= word <= TAG + 3 else 0)
    return dict(words=values, invalid_decodes_off=True)


def storage_cases():
    import penf_tone_rgb_ownership_probe as storage
    previous = storage.STORAGE_IDS
    try:
        storage.STORAGE_IDS = tuple((key,) for key in IDS)
        return storage.storage_cases()
    finally:
        storage.STORAGE_IDS = previous


def snapshot_cases(graph):
    s = setup(graph.base)
    settings(s)
    for slot in range(45):
        levels = (1, 2, 3)
        profile = slot % 3
        set_grain(s, levels)
        call(s, graph.symbols['hl_publish'])
        assert s.read(graph.symbols['grain_source'], 12) == struct.pack('<3I', *(TAG | n for n in levels))
        address = owner(s, slot, profile + 1, alias=bool(slot % 2))
        acquisition(s, address, slot >= 40)
        expected = TAG | levels[profile]
        assert u32(s, graph.symbols['grain_rows'] + slot * 4) == expected
        set_grain(s, (0, 0, 0))
        call(s, graph.symbols['hl_publish'])
        call(s, graph.symbols['hl_owner_to_job'], a0=address, a2=SNAPSHOT_JOB + 14920)
        assert u32(s, SNAPSHOT_JOB + 14960) == expected
        address = owner(s, slot, 0)
        acquisition(s, address, slot >= 40)
        call(s, graph.symbols['hl_owner_to_job'], a0=address, a2=SNAPSHOT_JOB + 14920)
        assert u32(s, SNAPSHOT_JOB + 14960) == 0
    return dict(owners=45, profile_count=3, later_changes_do_not_change_acquired_grain=True,
                invalid_profile_reuse_clears_grain=True)


class GrainJobs(JobProbe):
    def __init__(self, graph, *, level=0, loaded=True, **options):
        super().__init__(grain=level, **options)
        self.graph = graph
        s = self.s
        s.regions = [replace(r, data=graph.image) if r.name == 'main' else r for r in s.regions]
        s.ram('grain_diagnostic', graph.symbols['grain_diagnostic'], bytes(5))
        s.ram('loaded_sections', 0x61c58404, bytes([0xa4 if loaded else 4]))
        s.write(JOB + 14960, struct.pack('<I', TAG | level))
        native_return = s.return_from_model

        def queue_return(value=0):
            if s.regs['pc'] == QUEUE:
                at = s.regs['mdr'] - 7
                instruction = s.read(at, 7)
                if instruction[0] == 0xdd:
                    target = (at + struct.unpack_from('<i', instruction, 1)[0]) & 0xffffffff
                    if target == graph.symbols['grain_queue_gate']:
                        assert instruction[-2:] == b'\xf0\x18'
                        s.regs['pc'] = target
            native_return(value)

        s.return_from_model = queue_return


def engine_controls(graph, request):
    mode, stage = request['picture_mode'], int(request['stage'], 16)
    s, _ = engine_fixture(0x604fb7b8, 0x20, 8, mode, stage, image=graph.image)
    s.ram('grain_diagnostic', graph.symbols['grain_diagnostic'], bytes(5))
    packet = bytes.fromhex(request['request_hex'])
    s.write(Q, packet + bytes(1132 - len(packet)))
    s.ram('loaded_sections', 0x61c58404, b'\xa4')
    complete(s)
    combiner = s.regs['d0']
    if request['kind'] == 0:
        s.write(Q+212, struct.pack('<I', M))
        reenter(s, 0x604ea2ba, 0xf0, 20, dict(a0=C))
        complete(s)
        gain = u32(s, O + ICM + 112) if combiner in (31, 32) else None
        uploads = [upload(s, s.read(O+ICM, 164), bank) for bank in (0, 1)] if gain is not None else []
        reenter(s, 0x604f75e5, 0xf0, 24, dict(a0=Q, a1=RESULT))
        complete(s)
        tone = s.regs['a0']
        reenter(s, 0x604f83f1, 0xb0, 20, dict(a0=C))
        complete(s)
        chroma = u32(s, O + 0x20c + 76)
    else:
        gain = tone = chroma = None
        uploads = []
    return dict(combiner=combiner, gain=gain, tone=hex(tone) if tone else None, chroma=chroma, uploads=uploads,
        seed_descriptor='Explicit synthetic seed sample; captured job fixture has no sensor descriptor.')


def baseline_jobs(**options):
    probe = JobProbe(**options)
    image = apply_shading(firmware())
    probe.s.regions = [replace(r, data=image) if r.name == 'main' else r for r in probe.s.regions]
    return probe.all_jobs()


def pipeline_cases(graph):
    reports = []
    for fmt, alternate, level in product((0x0105, 0x0205), (0, 1), range(4)):
        p = GrainJobs(graph, mode=11, level=level, fmt=fmt, alternate=alternate)
        result = p.all_jobs()
        requests = result['requests']
        expected = [0] if level == 0 else [0x902, 0xf005, 0] if alternate else [0x900, 0x901, 0xf005, 0]
        assert [int(r['stage'], 16) for r in requests] == expected
        assert [r['picture_mode'] for r in requests] == ([12, 11, 11, 11] if level and not alternate else [11]*len(expected))
        controls = [engine_controls(graph, request) for request in requests]
        if level:
            index = 0 if alternate else 1
            assert controls[index]['gain'] == GAINS[0x902 if alternate else 0x901][level]
            assert controls[index]['combiner'] == (32 if alternate else 31)
            assert controls[index]['chroma'] == 0
            assert controls[index]['tone'] != '0x60610742'
            if not alternate:
                assert controls[0]['tone'] == '0x60610742'
                assert controls[0]['chroma'] == 0x808001
                assert requests[0]['outputs'][0]['pointer'] == requests[1]['mask']['pointer']
                assert requests[0]['source'] == requests[1]['source']
            assert requests[-1]['engine_selection']['jpeg_only_route']
            assert u32(p.s, JOB+12192) == 11
            assert u32(p.s, JOB+16) & 0x200000 == 0
        else:
            baseline = baseline_jobs(mode=11, grain=0, fmt=fmt, alternate=alternate)
            assert [r['request_hex'] for r in requests] == [r['request_hex'] for r in baseline['requests']]
        reports.append(dict(format=hex(fmt), alternate=alternate, level=level,
            stages=expected, controls=controls, dependency_chain=result['dependency_chain_verified']))
    for mode_value, level, alternate in product((1, 10, 12), (0, 3), (0, 1)):
        result = GrainJobs(graph, mode=mode_value, level=level, alternate=alternate).all_jobs()
        baseline = baseline_jobs(mode=mode_value, grain=level, alternate=alternate)
        assert [r['request_hex'] for r in result['requests']] == [r['request_hex'] for r in baseline['requests']]
    return dict(color=reports, unchanged_other_mode_cases=12,
        queue_model='Successful enqueue uses the actual originating native CALL mask/frame after the grain tail jump.',
        limits='Allocation, dimensions, parameter availability and queue acceptance modeled. ISP pixels and hardware completion excluded.')


def joined_capture_case(graph):
    from penf_tone_transport_probe import HL_PACKED, HL_ROWS, block
    from penf_tone_points import FivePoints
    from penf_tone_rgb_probe import channel_words
    p = GrainJobs(graph, mode=11, level=0)
    s = p.s
    settings(s)
    s.ram('hl_source', graph.symbols['hl_profile_source'], HL_PACKED)
    s.ram('tone_source', graph.symbols['tone_source'], bytes(60))
    s.ram('hl_rows', HL_ROWS, bytes(540))
    s.ram('tone_rows', graph.symbols['tone_rows'], bytes(720))
    s.ram('grain_rows', graph.symbols['grain_rows'], bytes(180))
    words = tuple(FivePoints((32+c*16,256,544,768,992)).pack() for c in range(4))
    channel_words(s, (words,)*3)
    set_grain(s, (3, 1, 2))
    call(s, graph.symbols['hl_publish'])
    address = owner(s, 0, 1)
    acquisition(s, address)
    set_grain(s, (0, 0, 0))
    call(s, graph.symbols['hl_publish'])
    pointer = 0x1a090020
    s.ram('acquired_owner_pointer', pointer, struct.pack('<I', address), aliases=False)
    put32(s, INITIAL_SP+4, JOB+36)
    block(s, 0x605205f9, 0x605205ff, a0=pointer)
    assert u32(s, JOB+14960) == TAG | 3
    assert s.read(JOB+14944, 16) == struct.pack('<4I', *words)
    result = p.all_jobs()
    assert [r['picture_mode'] for r in result['requests']] == [12, 11, 11, 11]
    assert bytes.fromhex(result['requests'][1]['request_hex'])[1088] == 3
    assert u32(s, graph.symbols['grain_source']) == TAG
    return dict(acquired_level=3, later_level=0, submitted_level=3,
        native_acquire=True, native_preview_conversion_hook=True, native_job_selection=True,
        tone_snapshot_retained=True, request_stages=[r['stage'] for r in result['requests']])


def color_processing_cases(graph):
    from penf_tone_rgb_probe import gamma_state, run_gamma, CURVES, NEUTRAL
    from penf_tone_integration_probe import REQUEST, CONTEXT, OUTPUT
    reports = []
    for stage, picture_mode in ((0x900, 12), (0x901, 11), (0x902, 11)):
        results = []
        for edited in (False, True):
            words = tuple(curve.pack() for curve in CURVES[1:]) if edited else (NEUTRAL,)*3
            s = gamma_state(graph.base, words, stage=stage)
            put32(s, CONTEXT+48, picture_mode)
            s.write(REQUEST+10, struct.pack('<H', picture_mode))
            put32(s, SNAPSHOT_JOB+14944, CURVES[1].pack() if edited else NEUTRAL)
            s.write(SNAPSHOT_JOB+14920, bytes([3 if edited else 0])*24)
            banks = run_gamma(s, graph.base)
            pointer = u32(s, OUTPUT+4656)
            results.append((banks, s.read(OUTPUT+0x2a4, 300), s.read(pointer, 512), pointer))
        equal = [results[0][i] == results[1][i] for i in range(3)]
        assert equal == ([True]*3 if stage == 0x900 else [False]*3), (stage, equal)
        if stage == 0x900:
            assert results[0][3] == results[1][3] == 0x60610742
        reports.append(dict(stage=hex(stage), mode=picture_mode,
            custom_rgb_hsl_all_unchanged=equal, tone_pointers=[hex(r[3]) for r in results]))
    return dict(stages=reports, native_common_builder=True, pixels_emulated=False)


def unavailable_cases(graph):
    from penf_recovery_isolation_probe import without_ranges
    from penf_tone_transport_probe import block
    for mode_value, level in product((11, 12), (0, 3)):
        p = GrainJobs(graph, mode=mode_value, level=level, loaded=False)
        p.s.regions = without_ranges(p.s.regions, [(0x6115b014, 0x6115c800), (0xa115b014, 0xa115c800)])
        p.s.regions = [r for r in p.s.regions if not r.name.startswith('grain_diagnostic')]
        result = p.all_jobs()
        baseline = baseline_jobs(mode=mode_value, grain=level)
        assert [r['request_hex'] for r in result['requests']] == [r['request_hex'] for r in baseline['requests']]
    s = setup(graph.base, loaded=False)
    put32(s, SNAPSHOT_JOB+14960, TAG | 3)
    call(s, graph.symbols['tone_job_gate'], a2=SNAPSHOT_JOB+14920)
    assert s.read(SNAPSHOT_JOB+14944, 20) == bytes(20)
    for mode_value in (11, 1, 2):
        s = setup(graph.base)
        settings(s)
        set_grain(s, (1, 2, 3))
        call(s, graph.symbols['hl_publish'])
        address = owner(s, 3, 2, mode=mode_value)
        put32(s, graph.symbols['grain_rows']+12, TAG | 3)
        pointer = 0x1a090020
        s.ram('raw_grain_owner', pointer, struct.pack('<I', address), aliases=False)
        block(s, 0x60af2f56, 0x60af2f5c, a2=pointer)
        assert u32(s, graph.symbols['grain_rows']+12) == (TAG | 2 if mode_value == 11 else 0)
    for status in (0, 1, 0xffffffff):
        s = setup(graph.base)
        settings(s)
        set_grain(s, (1, 2, 3))
        call(s, graph.symbols['hl_publish'])
        address = owner(s, 42, 3)
        acquisition(s, address, True)
        put32(s, INITIAL_SP+12, address)
        put32(s, INITIAL_SP+1868, SNAPSHOT_JOB)
        put32(s, SNAPSHOT_JOB+14960, TAG | 1)
        block(s, graph.symbols['hl_after_compact_call'], 0x6055a291, d0=status)
        assert u32(s, SNAPSHOT_JOB+14960) == TAG | (3 if status == 0 else 1)
    return dict(unmapped_pipeline_cases=4, unloaded_conversion_clears_grain=True,
        raw_grain_reuse_cases=3, compact_success_failure_grain_cases=3)


def manager_cases(graph):
    s = fixture(graph.base, replace(graph.editor, image=graph.image))
    set_grain(s, (0, 0, 0))
    reports = []
    for profile, level in product(range(3), range(4)):
        high = 967 + profile * 3
        before = s.read(ACTIVE, WORDS * 8)
        actuator(s, (profile+1)%3+1, 7)
        reenter(s, graph.symbols['tone_manager_gate'], 0xe0, 16,
                dict(PRESERVED, a0=0x19102000, d0=high, d1=TAG | level))
        stop = (0x602c1067, 0x602c1080, 0x602c1099)[profile]
        stopped(s, s.run({stop}, limit=100000), stop)
        expected = bytearray(before)
        struct.pack_into('<I', expected, (WORDS+IDS[profile])*4, TAG | level)
        assert s.read(ACTIVE, WORDS*8) == expected
        assert u32(s, graph.symbols['grain_source']+profile*4) == TAG | level
        assert s.regs['d2'] == high
        reports.append((profile+1, level))
    for loaded, word in product((False, True), range(0xfffffff9, 0x100000000)):
        s.write(0x61c58404, bytes([0xa4 if loaded else 4]))
        before = s.read(ACTIVE, WORDS*8)
        reenter(s, graph.symbols['tone_manager_gate'], 0xe0, 16,
            dict(PRESERVED, a0=0x19102000, d0=970, d1=word))
        stopped(s, s.run({0x6075fbed}, limit=100000), 0x6075fbed)
        assert (s.regs['d0'], s.regs['d1']) == (970, word)
        assert s.read(ACTIVE, WORDS*8) == before
    return dict(commits=reports, native_negative_passthrough_cases=14,
        captured_profile_independent_of_current_cursor=True, stock_part0_unchanged=True)


def editor_cases(graph):
    s = fixture(graph.base, replace(graph.editor, image=graph.image))
    count = 0
    for profile, level, direction in product(range(3), range(4), (0, 1)):
        mode(s, 54+profile)
        current(s, profile+1, (0, 0, 0))
        set_grain(s, (level,)*3)
        actuator(s, profile+1, 12)
        call(s, 0x60c878ec, 0xf0, 28, a0=ACTUATOR)
        reenter(s, graph.symbols['tone_input'], 0, 0,
                dict(PRESERVED, a0=0x19101000, a1=ACTUATOR, d0=969+profile*3, d1=direction))
        stopped(s, s.run({0x607363b3}, limit=100000), 0x607363b3)
        expected = min(3, level+1) if direction else max(0, level-1)
        assert (s.regs['d0'], s.regs['a1']) == (967+profile*3, TAG | expected)
        count += 1
    native_inputs = ((0x60c871e3, 0, 1), (0x60c87245, 0, -1),
        (0x60c872a9, 0, -1), (0x60c8730d, 0, 1),
        (0x60c8736f, 1, -1), (0x60c8736f, -1, 1),
        (0x60c873ec, 1, 1), (0x60c873ec, -1, -1))
    for profile in range(3):
        mode(s, 54+profile)
        set_grain(s, (2,)*3)
        for entry, delta, change in native_inputs:
            actuator(s, profile+1, 12)
            call(s, 0x60c878ec, 0xf0, 28, a0=ACTUATOR)
            reenter(s, entry, 0, 0, dict(PRESERVED, a0=ACTUATOR, d1=delta & 0xffffffff))
            stopped(s, s.run({0x607363b3}, limit=100000), 0x607363b3)
            assert (s.regs['d0'], s.regs['a1']) == (967+profile*3, TAG | (2+change))
        actuator(s, profile+1, 12)
        put32(s, INITIAL_SP+4, ACTUATOR)
        put32(s, INITIAL_SP+20, 54+profile)
        s.regs = dict(PRESERVED, pc=0x60c875e4, sp=INITIAL_SP, d0=0, d1=0, a0=0, a1=0, a3=0, psw=0)
        stopped(s, s.run({0x607363b3}, limit=100000), 0x607363b3)
        assert (s.regs['d0'], s.regs['a1']) == (967+profile*3, TAG)
        put32(s, INITIAL_SP+4, ACTUATOR)
        put32(s, INITIAL_SP+20, 54+profile)
        s.regs = dict(PRESERVED, pc=0x60c87670, sp=INITIAL_SP, d0=0, d1=0, a0=0, a1=0, a3=0, psw=0)
        stopped(s, s.run({0x60c879c8}, limit=100000), 0x60c879c8)
        assert s.read(ACTUATOR+194, 2) == bytes(2)
    return dict(input_cases=count, native_arrow_dial_cases=24, held_reset_cases=3,
        info_returns_to_all=True, bounds=(0, 3), shared_page=12)


def viewer_cases(graph):
    from penf_tone_rgb_viewer_probe import state, press, UPDATE, VIEWER, settings_bytes
    viewer = state(graph)
    s = viewer.s
    labels = ('Off', 'Low', 'Medium', 'High')
    reports = []
    for profile, level in product(range(3), range(4)):
        mode(s, 54+profile)
        current(s, profile+1, (0, 0, 0))
        set_grain(s, (level,)*3)
        actuator(s, profile+1, 12)
        before = settings_bytes(s)
        reenter(s, UPDATE, 0, 0, dict(PRESERVED, a0=VIEWER))
        viewer.drive()
        viewer.guards()
        payload = s.read(0x619b5f80, 92)
        label = payload[18:].decode('utf-16le').split('\0')[0]
        assert label == f'Grain {labels[level]} R00000 @A028@', label
        assert payload[5] == 1
        press(viewer)
        assert struct.unpack('<H', s.read(ACTUATOR+194, 2))[0] == 12
        assert settings_bytes(s) == before
        viewer.guards()
        reports.append(dict(profile=profile+1, level=level, footer=label))
    return dict(native_viewer_publications=reports, delete_consumed_without_setting_changes=True)


def grain_graph_case(graph):
    from penf_tone_graph_probe import fixture as graph_fixture, paint
    s = graph_fixture(graph, page=12)
    result = paint(s, graph)
    assert result['rectangles'] == []
    return dict(custom_curve_rectangles=0, native_painter_returned=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    graph = build_graph(args.out/'candidate')
    checks = {}
    for check in (decode_cases, snapshot_cases, manager_cases, editor_cases, viewer_cases, grain_graph_case, joined_capture_case, color_processing_cases, unavailable_cases, pipeline_cases):
        checks[check.__name__] = check(graph)
        (args.out/'result.json').write_text(json.dumps(checks, indent=2)+'\n')
    checks['storage'] = storage_cases()
    (args.out/'result.json').write_text(json.dumps(checks, indent=2)+'\n')
    print(json.dumps({name: 'pass' for name in checks}))


if __name__ == '__main__':
    main()
