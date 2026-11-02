"""Table isolation, geometry calibration, and optional native request checks."""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from penf_shading_candidate import BASE, TABLE, STOCK, SUBTLE, apply_shading
from penf_emulator import ENGINE, IMAGE


class ShadingCandidateTests(unittest.TestCase):
    def test_only_the_five_scale_words_change(self):
        offset = TABLE - BASE
        image = bytearray(b'\xa5' * (offset + 32))
        struct.pack_into('<5H', image, offset, *STOCK)
        original = bytes(image)
        patched = apply_shading(image)
        self.assertEqual(image, original)
        self.assertEqual(len(patched), len(original))
        self.assertEqual(patched[:offset], original[:offset])
        self.assertEqual(patched[offset + 10:], original[offset + 10:])
        self.assertEqual(struct.unpack_from('<5H', patched, offset), SUBTLE)
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            apply_shading(patched)
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            apply_shading(original[:offset + 9])
        image[offset] ^= 1
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            apply_shading(image)

    def test_radial_steps_are_fifths_of_old_level_one(self):
        reference = 1048576 // STOCK[0]
        previous = 0
        for level, word in enumerate(SUBTLE, 1):
            relative = (reference / (1048576 // word)) ** 2
            self.assertAlmostEqual(relative, level / 5, delta=0.001)
            self.assertGreater(relative, previous)
            self.assertLessEqual(word, STOCK[0])
            previous = relative
        self.assertEqual(SUBTLE[-1], STOCK[0])

    @unittest.skipUnless(ENGINE.is_file() and IMAGE.is_file(),
                         'Requires the PEN-F stock image and MN103 harness')
    def test_native_signed_levels_zero_invalid_and_coordinate_scaling(self):
        from penf_emulator import firmware
        from penf_shading_probe import probe, coordinate_probe
        image = apply_shading(firmware())
        for kind in (0, 3):
            for level in (-128, -6, *range(-5, 6), 6, 127):
                with self.subTest(kind=kind, level=level):
                    result = probe(image, SUBTLE, level, kind)
                    self.assertTrue(result['full_request_matches'])
                    self.assertTrue(result['job_unchanged'])
        for word in SUBTLE:
            for x, y in ((4096, 4096), (100, 133)):
                coordinate_probe(1048576 // word, x, y)


if __name__ == '__main__':
    unittest.main()
