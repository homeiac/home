#!/usr/bin/env python3
"""Append a timestamped operator observation without changing any running trial."""
import argparse
import experiment

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('note')
args=parser.parse_args()
experiment.JOURNAL=experiment.ROOT/'docs/experiments/waffles/2026-11-26-continuous-production.jsonl'
experiment.record('operator_note',note=args.note)
