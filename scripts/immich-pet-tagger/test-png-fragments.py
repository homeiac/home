#!/usr/bin/env python3
"""Require byte-exact PNG recovery and reject pixel corruption without checksum evidence."""
import importlib.util
from pathlib import Path
import random
import struct
import unittest
import zlib
spec=importlib.util.spec_from_file_location('repair',Path(__file__).with_name('repair-png-fragments.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def chunk(kind,data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))

class RecoveryTest(unittest.TestCase):
    def fixture(self):
        rng=random.Random(244);pixels=b''.join(b'\0'+rng.randbytes(32*4) for _ in range(32));stream=zlib.compress(pixels)
        parts=[stream[i:i+256] for i in range(0,len(stream),256)]
        prefix=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',32,32,8,6,0,0,0))
        original=prefix+b''.join(chunk(b'IDAT',p) for p in parts)+chunk(b'IEND',b'')
        fragment=parts[3][80:97];short=parts[3][:80]+parts[3][97:]
        damaged=prefix
        for i,part in enumerate(parts):
            if i==3:damaged+=struct.pack('>I',len(part))+b'IDAT'+short+struct.pack('>I',zlib.crc32(b'IDAT'+part))
            else:damaged+=chunk(b'IDAT',part)
            if i in (0,5):damaged+=fragment
        damaged+=chunk(b'IEND',b'')
        return original,damaged
    def test_displaced_fragment_is_exactly_recovered(self):
        original,damaged=self.fixture();fixed,report=module.repair(damaged)
        self.assertEqual(fixed,original);self.assertTrue(report['zlib_checksum_valid'])
    def test_missing_fragment_is_rejected(self):
        _,damaged=self.fixture();bad=bytearray(damaged);bad[50]^=1
        with self.assertRaises(ValueError):module.repair(bytes(bad))
    def test_non_png_is_rejected(self):
        with self.assertRaises(ValueError):module.repair(b'not PNG')

if __name__=='__main__':unittest.main()
