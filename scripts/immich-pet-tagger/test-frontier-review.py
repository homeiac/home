#!/usr/bin/env python3
"""Exercise target alignment and fail-closed quality gates without external calls."""
import importlib.util
from pathlib import Path
import unittest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


review = load('frontier-review')
gate = load('gate-reject-review')
recovery = load('prepare-reviewed-recovery')


class ReviewTests(unittest.TestCase):
    def test_boxes_reject_ambiguous_animals(self):
        self.assertIsNone(recovery.choose_box([]))
        self.assertEqual(recovery.choose_box([[0,0,1,1]]),[0,0,1,1])
        self.assertEqual(recovery.choose_box([[0,0,1,1],[.01,.01,.99,.99]]),[0,0,1,1])
        self.assertIsNone(recovery.choose_box([[0,0,.4,.4],[.6,.6,1,1]]))
        for box in ([0,0,0,1],[-1,0,1,1],[0,0,float('nan'),1]):
            with self.assertRaises(ValueError): recovery.choose_box([box])

    def test_exact_alignment(self):
        row = {'verdict': 'same_dog', 'confidence': 'high', 'reason': 'Visible markings'}
        self.assertEqual(review.parse_answers({'target_0': row}, 1)[0]['target_index'], 0)
        for data in ({}, {'target_1':row}, {'target_0':row, 'target_1':row}):
            with self.assertRaises(ValueError): review.parse_answers(data, 1)
        with self.assertRaises(ValueError):
            review.parse_answers({'target_0':{**row, 'confidence':'certain'}},1)
        self.assertIn('exactly 4 targets',review.PROMPT.format(target_count=4,target_keys='target_0, target_1, target_2, target_3'))

    def test_gate_requires_incremental_complete_zero_fp(self):
        truth = {'positive':[f'p{i}' for i in range(13)], 'negative':[f'n{i}' for i in range(13)]}
        records = [{'asset_id':a, 'expected':label, 'answer':{'verdict':'different_dog','confidence':'high'}}
                   for label in truth for a in truth[label]]
        local = {r['asset_id']:False for r in records}
        self.assertFalse(gate.evaluate(records,truth,local,0)['eligible_for_fallback'])
        records[0]['answer']['verdict']='same_dog'
        self.assertTrue(gate.evaluate(records,truth,local,0)['eligible_for_fallback'])
        self.assertFalse(gate.evaluate(records[:-1],truth,local,0)['eligible_for_fallback'])
        self.assertFalse(gate.evaluate(records+[records[0]],truth,local,0)['eligible_for_fallback'])
        self.assertFalse(gate.evaluate(records,truth,local,1)['eligible_for_fallback'])
        self.assertFalse(gate.evaluate(records,truth,{**local,'p0':True},0)['eligible_for_fallback'])
        records[-1]['answer']['verdict']='same_dog'
        self.assertFalse(gate.evaluate(records,truth,local,0)['eligible_for_fallback'])


if __name__ == '__main__': unittest.main()
