"""Ensure enrollment mode never starts the automatic scanner, including restarts."""
import os
from pathlib import Path
import runpy
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


class StartupTest(unittest.TestCase):
    def run_startup(self, enabled: str):
        fake_main = ModuleType('main')
        original = Mock()
        fake_main.polling_loop = original
        fake_main.app = object()
        fake_uvicorn = ModuleType('uvicorn')
        fake_uvicorn.run = Mock()
        with patch.dict(sys.modules, {'main': fake_main, 'uvicorn': fake_uvicorn}), \
             patch.dict(os.environ, {'AUTOMATIC_SCANS': enabled}):
            runpy.run_path(str(Path(__file__).with_name('startup.py')))
        fake_uvicorn.run.assert_called_once_with(fake_main.app, host='0.0.0.0',
                                                port=8000, timeout_keep_alive=120)
        return fake_main.polling_loop, original

    def test_disabled_scanner_is_not_registered(self):
        actual, original = self.run_startup('false')
        self.assertIsNot(actual, original)
        original.assert_not_called()

    def test_enabled_scanner_uses_upstream_loop(self):
        actual, original = self.run_startup('true')
        self.assertIs(actual, original)

    def test_invalid_value_fails_closed(self):
        actual, original = self.run_startup('yes')
        self.assertIsNot(actual, original)


if __name__ == '__main__':
    unittest.main()
