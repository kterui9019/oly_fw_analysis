#!/usr/bin/env python3
"""Compose an offline tone candidate over the exact pinned HSL main image."""
if not __debug__:
    raise RuntimeError('Tone audit probes require assertions; optimized Python execution is unsupported')

from dataclasses import dataclass
import json
from pathlib import Path
import struct
import subprocess

from penf_emulator import BASE, ROOT, firmware
from penf_landmarks import MAIN_SHA256
from penf_tone_endpoints import TOOLCHAIN
from penf_tone_integration_probe import SOURCES
from penf_tone_probe import sha

GRAIN_DIAGNOSTIC = 0x601cafdb

HSL = ROOT / 'patches/hsl/pen-f'
TOOLS = {name: TOOLCHAIN / path for name, path in (
    ('assembler','gas/as-new'),('linker','ld/ld-new'),('objcopy','binutils/objcopy'),
    ('objdump','binutils/objdump'),('nm','binutils/nm-new'))}


@dataclass(frozen=True)
class Candidate:
    image: bytes
    reference: bytes
    symbols: dict
    manifest: tuple


def run(*args):
    return subprocess.check_output([str(x) for x in args], stderr=subprocess.STDOUT, text=True)


def symbols(elf):
    return {name: int(address, 16) for address, kind, name in
            (line.split() for line in run(TOOLS['nm'], '-n', elf).splitlines())}


def assemble(folder, sources, layout):
    folder.mkdir(parents=True, exist_ok=False)
    objects = []
    for i, source in enumerate(sources):
        obj = folder / f'{i}.o'
        run(TOOLS['assembler'], '-o', obj, source)
        objects.append(obj)
    elf = folder / 'patch.elf'
    run(TOOLS['linker'], '--no-relax', '-T', layout, '-o', elf, *objects)
    (folder / 'patch.asm').write_text(run(TOOLS['objdump'], '-d', elf))
    return elf


def extract(elf, section):
    path = elf.parent / (section + '.bytes')
    run(TOOLS['objcopy'], '-O', 'binary', '--only-section=.' + section, elf, path)
    return path.read_bytes()


def reference_main(out, stock_main=None):
    spec = json.loads((HSL / 'patch.json').read_text())
    image = bytearray(firmware() if stock_main is None else stock_main)
    assert sha(image) == MAIN_SHA256, 'Wrong stock main hash'
    expected = {(r['name'], int(r['address'], 16)): r for r in spec['main_ranges']}
    written, names = set(), {}

    def install(name, address, data):
        row = expected[(name, address)]
        assert (name, address) not in written
        assert len(data) == row['bytes'] and sha(data) == row['after_sha256'], name
        at = address - BASE
        assert sha(image[at:at + len(data)]) == row['before_sha256'], name
        image[at:at + len(data)] = data
        written.add((name, address))

    for group in spec['groups']:
        elf = assemble(out / group['name'], [HSL / p for p in group['sources']], HSL / group['linker'])
        names.update(symbols(elf))
        for section, address in group['sections'].items():
            install(section, int(address, 16), extract(elf, section))
    for edit in spec['data_edits']:
        install(edit['name'], int(edit['address'], 16), bytes.fromhex(edit['after']))
    assert written == set(expected)
    assert sha(image) == spec['main_sha256']
    return bytes(image), names


def build_candidate(out, *, expanded=False, stock_main=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    reference, old = reference_main(out / 'hsl-reference', stock_main)
    late_start = 0x6115b014 if expanded else 0x6115b060
    late_end = 0x6115c800
    layout = out / 'tone.ld'
    layout.write_text('''SECTIONS {
.tone_early 0x60427e78 : { *(.tone_early) }
.tone_source 0x60427c30 : { *(.tone_source) }
.grain_primary_gate 0x60427fc0 : { *(.grain_primary_gate) }
.tone_storage_ids 0x601caa10 : { *(.tone_storage_ids) }
.tone_rgb_gate 0x60427fe8 : { *(.tone_rgb_gate) }
.tone_rgb_stock 0x601caa04 : { *(.tone_rgb_stock) }
.grain_select_gate 0x6069b26c : { *(.grain_select_gate) }
.grain_combiner_gate 0x6069b7b9 : { *(.grain_combiner_gate) }
.grain_queue_gate 0x601caa2e : { *(.grain_queue_gate) }
.tone_job_gate 0x60427fa8 : { *(.tone_job_gate) }
.tone_source_gate 0x6069b580 : { *(.tone_source_gate) }
.tone_job_bridge 0x6069b7ac : { *(.tone_job_bridge) }
.text 0x6115b060 : { *(.text) }
.tone_rows : { *(.tone_rows) }
.grain_rows : { *(.grain_rows) }
}
grain_native_604c2f1d = 0x604c2f1d;
grain_native_604c58a7 = 0x604c58a7;
grain_native_604c5c46 = 0x604c5c46;
grain_native_604c5d33 = 0x604c5d33;
grain_native_604fb887 = 0x604fb887;
grain_native_604fb918 = 0x604fb918;
grain_native_604c4b3f = 0x604c4b3f;
grain_native_604c5435 = 0x604c5435;
stock_rgb_builder = 0x604f6083;
stock_rgb_resume = 0x604f858d;
stock_spline_coefficients = 0x604bdea7;
stock_spline_evaluate = 0x604bdfe1;
stock_tone_builder = tone_stock_builder;
stock_tone_select = 0x604f7c18;
stock_tone_gate = 0x604bdd21;
stock_tone_apply = 0x604be08d;
stock_convert = 0x604bddcc;
stock_tone_resume = 0x604f85ef;
stock_active_get = 0x602f06e7;
stock_builder_after_entry = 0x604f7c7b;
tone_source_uncached = tone_source + 0x40000000;
tone_rows_uncached = tone_rows + 0x40000000;
tone_compact_rows = tone_rows_uncached + 640;
grain_source_uncached = grain_source + 0x40000000;
grain_rows_uncached = grain_rows + 0x40000000;
'''.replace('0x6115b060', hex(late_start)) + f'hl_owner_row = {old["hl_owner_row"]:#x};\nhl_return = {old["hl_no_owner"] + 2:#x};\ngrain_diagnostic = {GRAIN_DIAGNOSTIC:#x};\ngrain_diagnostic_uncached = grain_diagnostic + 0x40000000;\n')
    elf = assemble(out / 'tone', [*SOURCES, ROOT / 'patches/tone/pen-f/src/transport.s', ROOT / 'patches/tone/pen-f/src/rgb.s', ROOT / 'patches/tone/pen-f/src/grain.s'], layout)
    current = symbols(elf)
    image, manifest = bytearray(reference), []

    def install(name, address, data, expected=None):
        at = address - BASE
        before = reference[at:at + len(data)]
        assert len(before) == len(data)
        if expected is not None:
            assert before == expected, (name, before.hex())
        for row in manifest:
            assert address + len(data) <= row['address'] or row['address'] + row['bytes'] <= address, name
        image[at:at + len(data)] = data
        manifest.append(dict(name=name, address=address, bytes=len(data),
                             before_sha256=sha(before), after_sha256=sha(data)))

    allocations = {'tone_early': (0x60427e78, 0x60427ed0),
                   'tone_source': (0x60427c30, 0x60427c70),
                   'tone_rgb_gate': (0x60427fe8, 0x60428000),
                   'tone_rgb_stock': (0x601caa04, 0x601caa10),
                   'tone_storage_ids': (0x601caa10, 0x601caa2e),
                   'grain_primary_gate': (0x60427fc0, 0x60427fd8),
                   'grain_select_gate': (0x6069b26c, 0x6069b2b0),
                   'grain_combiner_gate': (0x6069b7b9, 0x6069b800),
                   'grain_queue_gate': (0x601caa2e, 0x601caa50),
                   'tone_job_gate': (0x60427fa8, 0x60427fc0),
                   'tone_source_gate': (0x6069b580, 0x6069b590),
                   'tone_job_bridge': (0x6069b7ac, 0x6069b7b8),
                   'text': (late_start, late_end)}
    for name, (start, end) in allocations.items():
        data = extract(elf, name)
        assert start + len(data) <= end, (name, len(data), end - start)
        install(name, start, data, b'\xff'*len(data) if name in ('tone_source','tone_storage_ids','tone_rgb_gate','tone_rgb_stock','grain_select_gate','grain_combiner_gate','grain_queue_gate','grain_primary_gate') else None)
    rows = extract(elf, 'tone_rows')
    assert len(rows) == 720 and current['tone_rows'] + len(rows) <= late_end
    install('tone_rows', current['tone_rows'], rows)
    grain_rows = extract(elf, 'grain_rows')
    assert len(grain_rows) == 180 and current['grain_rows'] + 180 <= late_end
    install('grain_rows', current['grain_rows'], grain_rows, b'\xff' * 180)

    def jump(name, at, target, short=False, expected=None):
        data = (b'\xcc' + struct.pack('<h', target - at) if short else
                b'\xdc' + struct.pack('<i', target - at))
        install(name, at, data, expected)

    assert reference[old['hl_no_owner'] + 2 - BASE:old['hl_no_owner'] + 5 - BASE] == bytes.fromhex('df0004')
    jump('publish_tail', old['hl_boot_publish'] - 3, current['tone_publish'], True, bytes.fromhex('df0004'))
    jump('source_tail', old['hl_source_done'], current['tone_source_gate'], True, bytes.fromhex('df0004'))
    jump('job_tail', old['hl_owner_row'] - 3, current['tone_job_bridge'], True, bytes.fromhex('df0004'))
    jump('native_rgb_call', 0x604f8588, current['tone_rgb_gate'], expected=bytes.fromhex('cdfbdaf0d8'))
    jump('native_tone_entry', 0x604f7c76, current['tone_build_gate'], expected=bytes.fromhex('f80404f1d3'))
    install('section8_load_end', 0x6004211d, struct.pack('<I', 0x6115c800), struct.pack('<I', 0x6115b800))
    install('job_allocation', 0x604c1c0f, bytes.fromhex('2c743a'), bytes.fromhex('2c603a'))
    install('job_zero_count', 0x604c1d1f, bytes.fromhex('8538'), bytes.fromhex('8524'))
    for name, at, target, before in (
        ('grain_job_select', 0x604c589c, 'grain_select_gate', 'fa04a02fa50cc605cc8f04'),
        ('grain_combiner_select', 0x604fb880, 'grain_combiner_gate', 'a00cc905cc9400'),
    ):
        expected = bytes.fromhex(before)
        data = b'\xdc' + struct.pack('<i', current[target] - at)
        install(name, at, data + b'\xcb' * (len(expected) - len(data)), expected)


    at = 0x604c5430
    install('grain_primary_select', at, b'\xdc' + struct.pack('<i', current['grain_primary_gate'] - at), bytes.fromhex('cd0ff7f014'))
    for at in (0x604d62d2, 0x604d635c, 0x604d64b3, 0x604d65be, 0x604d68cb):
        expected = b'\xdd' + struct.pack('<i', 0x604c2f1d - at) + b'\xf0\x18'
        data = b'\xdd' + struct.pack('<i', current['grain_queue_gate'] - at) + b'\xf0\x18'
        install(f'grain_mask_enqueue_{at:x}', at, data, expected)

    raw_source = (HSL / 'src/raw_development/raw_development.s').read_text()
    needle = ' .endr\nhl_raw_done:'
    assert raw_source.count(needle) == 1
    raw_source = raw_source.replace(needle, ''' .endr
 movbu (0xa1c58404),d0
 btst 128,d0
 beq hl_raw_done
 call tone_clear_hl_row,[],4
hl_raw_done:''')
    raw = out / 'raw.s'
    raw.write_text(raw_source)
    raw_layout = out / 'raw.ld'
    raw_layout.write_text((HSL / 'src/raw_development/layout.ld').read_text() +
                          f'\ntone_clear_hl_row = {current["tone_clear_hl_row"]:#x};\n')
    raw_elf = assemble(out / 'raw', [raw], raw_layout)
    raw_code = extract(raw_elf, 'raw_acquire')
    assert len(raw_code) <= 112
    assert extract(raw_elf, 'raw_acquire_hook') == reference[0x60af2f56 - BASE:0x60af2f5c - BASE]
    install('composed_raw_acquire', 0x60fdc750, raw_code)
    all_symbols = dict(old, **current)
    (out / 'manifest.json').write_text(json.dumps(dict(
        status='offline main-image composition, not an installable container',
        reference_sha256=sha(reference), candidate_sha256=sha(image),
        spans=manifest, symbols={k: hex(v) for k, v in all_symbols.items()}), indent=2) + '\n')
    return Candidate(bytes(image), reference, all_symbols, tuple(manifest))
