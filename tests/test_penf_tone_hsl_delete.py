import struct
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from penf_hsl_context_probe import reenter
from penf_probe import CALLER
from penf_tone_editor_probe import ACTUATOR, actuator, current, fixture, mode
from penf_tone_graph_candidate import build_graph
from penf_tone_probe import INITIAL_SP, PRESERVED
from penf_tone_transport_probe import ACTIVE, WORDS, put32


class HslDeleteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='penf-hsl-delete-')
        cls.graph = build_graph(Path(cls.temp.name) / 'candidate')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_hsl_delete_from_common_dispatcher(self):
        controller, event, viewer = 0x19110000, 0x19111000, 0x19112000
        children, types, values = 0x19200000, 0x19210000, 0x19211000
        for loaded in (0xa4, 0x04):
            for profile in (1, 2, 3):
                for axis in (0, 1, 2):
                    with self.subTest(loaded=loaded, profile=profile, axis=axis):
                        s = fixture(self.graph.base, replace(self.graph.editor, image=self.graph.image))
                        data = bytearray(208)
                        struct.pack_into('<I', data, 0, 0x60f6eda0)
                        struct.pack_into('<H', data, 100, 0x13b1 + profile)
                        struct.pack_into('<H', data, 120, 13)
                        for i in range(13):
                            struct.pack_into('<I', data, 124 + i * 4, children + i * 160)
                        s.ram('hsl_actuator', ACTUATOR, data, aliases=False)
                        for i in range(13):
                            child = bytearray(140)
                            struct.pack_into('<H', child, 84, 1095 if i == 0 else 930 + (profile - 1) * 12 + i)
                            struct.pack_into('<HH', child, 88, 13 if i == 0 else 15, 0 if i == 0 else 7)
                            struct.pack_into('<II', child, 96, types, values)
                            s.ram('child' + str(i), children + i * 160, child, aliases=False)
                        s.ram('types', types, bytes(30), aliases=False)
                        s.ram('values', values, struct.pack('<15i', *range(7, -8, -1)), aliases=False)
                        s.ram('hsl_controller', controller, struct.pack('<2I', ACTUATOR, viewer), aliases=False)
                        s.ram('controller_global', 0x6161b810, struct.pack('<I', controller))
                        s.ram('screen', 0x6161b81c, struct.pack('<H', 0x13b1 + profile))
                        s.ram('event', event, b'\x02\x02' + bytes(30), aliases=False)
                        for address in (0x61618eb0, 0x6161ad04, 0x6161bf84):
                            s.ram(hex(address), address, bytes(4))
                        s.ram('axis', 0xa069b7b8, bytes([axis]))
                        for key in range(931, 967):
                            addr = 0x19300000 + (key - 931) * 256
                            s.ram('raw_value' + str(key), addr, bytes(256), aliases=False)
                            put32(s, 0x61c58bb4 + key * 4, addr)
                        s.write(0x61c58404, bytes([loaded]))
                        reenter(s, 0x60bcba4d, 0, 0,
                                dict(PRESERVED, a0=event, d0=0x9016, d1=0x1234, a1=0x4321))
                        result = s.run({self.graph.symbols['hsl_cycle']}, limit=100000)
                        self.assertEqual(result['status'], 'breakpoint', result.get('fault'))
                        self.assertEqual(s.regs['a0'], event)
                        self.assertEqual(s.regs['sp'], INITIAL_SP - 88)
                        result = s.run({CALLER + 7, 0x60bcbbc7, 0x60c84901}, limit=100000)
                        self.assertEqual(result['status'], 'breakpoint', result.get('fault'))
                        self.assertEqual(s.regs['pc'], 0x60c84901)
                        self.assertEqual(s.read(0xa069b7b8, 1), bytes([(axis - 1) % 3]))

    def test_grain_delete_is_consumed_by_common_dispatcher(self):
        controller, event, viewer = 0x19110000, 0x19111000, 0x19112000
        for profile in (1, 2, 3):
            with self.subTest(profile=profile):
                s = fixture(self.graph.base, replace(self.graph.editor, image=self.graph.image))
                mode(s, 53 + profile)
                current(s, profile, (0, 0, 0))
                actuator(s, profile, 12)
                s.ram('controller', controller, struct.pack('<2I', ACTUATOR, viewer), aliases=False)
                s.ram('controller_global', 0x6161b810, struct.pack('<I', controller))
                s.ram('screen', 0x6161b81c, struct.pack('<H', 897))
                s.ram('event', event, b'\x02\x02', aliases=False)
                for address in (0x61618eb0, 0x6161ad04, 0x6161bf84):
                    s.ram(hex(address), address, bytes(4))
                before = s.read(ACTIVE, WORDS * 8)
                reenter(s, 0x60bcba4d, 0, 0,
                        dict(PRESERVED, a0=event, d0=0x9016, d1=0x1234, a1=0x4321))
                result = s.run({CALLER + 7, 0x60bcbbc7}, limit=100000)
                self.assertEqual(result['status'], 'breakpoint', result.get('fault'))
                self.assertEqual(s.regs['pc'], CALLER + 7)
                self.assertEqual(s.regs['sp'], INITIAL_SP)
                self.assertEqual(s.regs['d0'], 0)
                self.assertTrue(all(s.regs[k] == v for k, v in PRESERVED.items()))
                self.assertEqual(s.read(ACTUATOR + 194, 2), struct.pack('<H', 12))
                self.assertEqual(s.read(ACTIVE, WORDS * 8), before)
