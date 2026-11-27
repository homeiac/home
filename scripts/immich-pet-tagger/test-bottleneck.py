#!/usr/bin/env python3
"""Verify diagnostic arithmetic and prevent zero-row probes masquerading as gains."""
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('report',Path(__file__).with_name('bottleneck-report.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class ReportTests(unittest.TestCase):
    def test_processing_residual_is_estimate(self):
        queue={'base_cycles':[{'worker':'mac','intervals':10,'completion_cycle_mean':'2.5','processing_mean':.4}],'recent':[]}
        value=r.calculate(queue,{'version':'indexed-fifo'}, {'current_urllib':{'median_seconds':.02}})
        self.assertAlmostEqual(value['baseline_cycles'][0]['estimated_nonprocessing_seconds'],2.1)
        self.assertAlmostEqual(value['baseline_cycles'][0]['estimated_processing_fraction'],.16)
        self.assertEqual(value['control_get_median_ms'],20)
    def test_empty_candidate_cannot_claim_lookup_gain(self):
        queue={'base_cycles':[],'recent':[]}
        claim={'version':'indexed-fifo','ready':[{'Execution Time':.001,'Plan':{'Actual Rows':0}}]}
        value=r.calculate(queue,claim,{'current_urllib':{'median_seconds':.02}})
        self.assertFalse(value['candidate_plans']['ready']['comparable_ready_lookup'])
        report={'label':'empty','at':'test','calculated':value}
        self.assertIn('do not compare',r.markdown(report))

if __name__=='__main__':unittest.main()
