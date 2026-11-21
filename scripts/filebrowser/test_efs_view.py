"""Test bounded streaming, seeks, failures, and source traversal rejection."""
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('efs_view', Path(__file__).with_name('efs-view.py'))
view = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(view)


class FakeProcess:
    def __init__(self, data):
        self.stdout = io.BytesIO(data)
        self.stdin = io.BytesIO()
        self.code = None

    def poll(self): return self.code
    def terminate(self): self.code = -15
    def wait(self, timeout=None): return self.code


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.data = bytes(range(256)) * 16
        self.processes = []
        def start(*args, **kwargs):
            self.assertEqual(args[0][:4], [view.DECRYPTOR, '-f', '-q', '-k'])
            self.assertTrue(kwargs['start_new_session'])
            process = FakeProcess(self.data)
            self.processes.append(process)
            return process
        self.patches = [patch.object(view, 'require_readonly'),
                        patch.object(view, 'WINDOW', 128),
                        patch.object(view.subprocess, 'Popen', side_effect=start),
                        patch.object(view.select, 'select', side_effect=lambda streams, *_: (streams, [], []))]
        for item in self.patches: item.start()
        self.stream = view.DecryptedStream('/file', len(self.data), b'synthetic-test-only')

    def tearDown(self):
        self.stream.close()
        for item in reversed(self.patches): item.stop()

    def test_sequential_and_cached_reads(self):
        self.assertEqual(self.stream.read(70, 0), self.data[:70])
        self.assertEqual(self.stream.read(100, 0), self.data[:100])
        self.assertEqual(self.stream.read(300, 100), self.data[100:400])
        self.assertEqual(len(self.processes), 1)
        self.assertLessEqual(len(self.stream.window), 128)

    def test_forward_and_backward_seeking(self):
        self.assertEqual(self.stream.read(200, 3000), self.data[3000:3200])
        self.assertEqual(self.stream.read(512, 0), self.data[:512])
        self.assertEqual(len(self.processes), 2)
        self.assertEqual(self.processes[0].code, -15)

    def test_eof_and_short_final_read(self):
        self.assertEqual(self.stream.read(1000, 4000), self.data[4000:])
        self.assertEqual(self.stream.read(1, 4096), b'')

    def test_truncated_decryption_fails(self):
        self.stream.size += 1
        with self.assertRaises(OSError): self.stream.read(4097, 0)

    def test_timeout_stops_process(self):
        with patch.object(view.select, 'select', return_value=([], [], [])):
            with self.assertRaises(OSError): self.stream.read(1, 0)
        self.assertIsNone(self.stream.process)


class PathTests(unittest.TestCase):
    def test_traversal_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(view, 'SOURCE', Path(directory)):
            self.assertEqual(view.source_path('/normal'), Path(directory) / 'normal')
            with self.assertRaises(OSError): view.source_path('/../outside')
            os.symlink('/etc', Path(directory) / 'link')
            with self.assertRaises(OSError): view.source_path('/link/passwd')

    def test_writable_mapper_rejected(self):
        with patch.object(view.subprocess, 'check_output', return_value='0\n'):
            with self.assertRaises(OSError): view.require_readonly()


if __name__ == '__main__': unittest.main()
