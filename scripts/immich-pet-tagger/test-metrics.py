#!/usr/bin/env python3
"""Regression tests for honest status, privacy and source failure handling."""
import unittest
from metrics import Collector, measurements, sample


class MetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manual = {'status': 'running', 'started_at': '2026-11-27T03:53:09Z',
                       'current_date': '2000-03-07',
                       'counts': {'fetched': 78900, 'added': 2, 'unknown': 164, 'low_confidence': 0}}
        self.poll = {'status': 'running'}
        self.pets = {'pets': [{'name': 'Waffles', 'ref_count': 23, 'person_id': 'PRIVATE_PERSON'}]}
        self.negatives = {'count': 42, 'assets': ['PRIVATE_ASSET']}

    def render(self) -> str:
        return '\n'.join(measurements(self.manual, self.poll, self.pets, self.negatives))

    def test_running_omits_unavailable_review_and_missing_counts(self) -> None:
        value = self.render()
        self.assertIn('outcome="added"} 2', value)
        self.assertNotIn('review_assets', value)
        self.assertNotIn('outcome="failed"', value)
        self.assertNotIn('PRIVATE', value)

    def test_review_only_after_completed_manual_scan(self) -> None:
        self.manual.update(status='idle', counts={'low_confidence': 7})
        self.assertIn('review_assets 7', self.render())
        for state in ('stopped', 'error', 'none'):
            self.manual['status'] = state
            self.assertNotIn('review_assets', self.render())

    def test_new_scan_can_reset_gauges(self) -> None:
        self.manual['counts']['added'] = 0
        self.assertIn('outcome="added"} 0', self.render())

    def test_unknown_status_is_not_success(self) -> None:
        self.manual['status'] = 'unexpected'
        self.assertIn('scan_state{scope="manual"} 5', self.render())

    def test_timestamp_precision_preserves_freshness(self) -> None:
        now = 1795751589.855964
        self.assertEqual(float(sample('last_success_timestamp_seconds', now).split()[-1]), now)

    def test_failure_drops_stale_measurements_and_keeps_success_time(self) -> None:
        responses = iter([self.manual, self.poll, self.pets, self.negatives])
        collector = Collector(lambda path: next(responses), lambda: 100)
        collector.collect()
        self.assertIn('source_up 1', collector.output)
        collector.collect()  # Exhausted input simulates a failed HTTP request.
        self.assertIn('source_up 0', collector.output)
        self.assertIn('last_success_timestamp_seconds 100', collector.output)
        self.assertNotIn('outcome="added"', collector.output)

    def test_bad_measurements_fail_closed(self) -> None:
        for bad in (-1, float('nan'), '2', True):
            self.manual['counts']['added'] = bad
            with self.assertRaises(ValueError):
                self.render()


if __name__ == '__main__':
    unittest.main()
