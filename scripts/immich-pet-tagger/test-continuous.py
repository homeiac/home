#!/usr/bin/env python3
"""Check repeated quality eligibility and the simpler-within-five-percent rule."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('continuous',Path(__file__).with_name('continuous-experiment.py'))
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)

def trial(slots,seconds,valid=True):
    return dict(worker='mac',slots=slots,device='cpu',cores=None,valid=valid,photos=100,wall_seconds=seconds,photos_per_minute=6000/seconds)

class Selection(unittest.TestCase):
    def test_requires_two_valid_passes(self):
        chosen,_=experiment.choose([trial(1,60),trial(1,60),trial(3,10),trial(3,10,False)])
        self.assertEqual(chosen['slots'],1)
    def test_prefers_fewer_within_five_percent(self):
        chosen,_=experiment.choose([trial(1,61),trial(1,61),trial(3,60),trial(3,60)])
        self.assertEqual(chosen['slots'],1)
    def test_pools_elapsed_time(self):
        chosen,_=experiment.choose([trial(1,30),trial(1,90),trial(3,50),trial(3,50)])
        self.assertEqual(chosen['slots'],3)
        self.assertEqual(chosen['photos_per_minute'],120)
    def test_incomplete_cannot_win(self):
        with self.assertRaises(RuntimeError):experiment.choose([trial(1,1)])

if __name__=='__main__':unittest.main()
