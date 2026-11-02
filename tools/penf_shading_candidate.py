"""Gentler signed creative-shading steps for the PEN-F 3101 capture path.

The native callback uses one coordinate-scale table for both signs. Scale the
squared radial coordinate in fifths of the old magnitude-one value; this is a
geometry calibration, not a claim of linear perceived opacity or ISP pixels.
"""
import struct

from penf_landmarks import BASE

TABLE = 0x605fc45e
STOCK = (928, 952, 976, 1000, 1024)
SUBTLE = (415, 587, 719, 830, 928)


def apply_shading(image):
    """Return a patched copy, rejecting an absent or already modified table."""
    offset = TABLE - BASE
    expected = struct.pack('<5H', *STOCK)
    if image[offset:offset + len(expected)] != expected:
        raise ValueError('Unexpected PEN-F creative shading table')
    patched = bytearray(image)
    patched[offset:offset + len(expected)] = struct.pack('<5H', *SUBTLE)
    return bytes(patched)


def calibration():
    """Describe actual integer-division geometry relative to stock +/-1."""
    reference = 1048576 // STOCK[0]
    return dict(table_address=hex(TABLE), stock_words=list(STOCK),
                candidate_words=list(SUBTLE), signs='both',
                target_relative_radial_amount=[level / 5 for level in range(1, 6)],
                actual_relative_radial_amount=[
                    (reference / (1048576 // word)) ** 2 for word in SUBTLE],
                scope='capture coordinate scaling; live view and RAW metadata unchanged; '
                      'physical appearance unverified')
