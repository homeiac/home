"""Checks for rolling concurrency and draining after an uncertain request."""
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import worker


class DispatchTest(unittest.TestCase):
    def test_fills_slot_while_the_other_request_is_running(self):
        third_started = threading.Event()

        def process(_, item):
            if item == 1:
                self.assertTrue(third_started.wait(3))
            if item == 3:
                third_started.set()
            return {"state": "ok", "id": item}

        results = []
        with patch.object(worker, "process", process), ThreadPoolExecutor(2) as pool:
            self.assertFalse(worker.dispatch(pool, [1, 2, 3], "batch", results, 2))
        self.assertEqual(sorted(result["id"] for result in results), [1, 2, 3])

    def test_ambiguous_request_drains_active_work_without_admitting_more(self):
        results = []
        with patch.object(worker, "process", return_value={"state": "unknown"}), ThreadPoolExecutor(2) as pool:
            self.assertTrue(worker.dispatch(pool, [1, 2, 3, 4], "batch", results, 2))
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
