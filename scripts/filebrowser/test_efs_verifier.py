"""Check EFS metadata bounds and the mandatory read-only device guard."""
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'efs_verifier', Path(__file__).with_name('verify-efs-certificate.py'))
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def metadata(kind_offset=64):
    """Make a minimal synthetic EFS credential with a known fingerprint."""
    data = bytearray(168)
    for offset, value in [(0, 168), (kind_offset, 76), (76, 1),
                          (80, 88), (84, 20), (100, 68), (108, 3),
                          (112, 20), (116, 28), (128, 20), (132, 20)]:
        struct.pack_into('<I', data, offset, value)
    data[148:168] = bytes(range(20))
    return data


class MetadataTests(unittest.TestCase):
    def test_decryption_and_recovery(self):
        for offset, kind in [(64, 'decryption'), (68, 'recovery')]:
            with self.subTest(kind=kind):
                self.assertEqual(verifier.efs_thumbprints(metadata(offset)),
                                 [{'kind': kind, 'sha1': bytes(range(20)).hex().upper()}])

    def test_rejects_truncated_stream(self):
        with self.assertRaises(ValueError):
            verifier.efs_thumbprints(metadata()[:-1])

    def test_rejects_out_of_bounds_thumbprint(self):
        data = metadata()
        struct.pack_into('<I', data, 128, 10000)
        with self.assertRaises(ValueError):
            verifier.efs_thumbprints(data)

    def test_rejects_missing_certificates(self):
        data = metadata()
        struct.pack_into('<I', data, 64, 0)
        with self.assertRaises(ValueError):
            verifier.efs_thumbprints(data)

    def test_rejects_writable_device_before_reading(self):
        with patch.object(verifier.subprocess, 'check_output', return_value='0\n'), \
                patch.object(verifier.subprocess, 'run') as read:
            with self.assertRaises(RuntimeError):
                verifier.read_metadata()
            read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
