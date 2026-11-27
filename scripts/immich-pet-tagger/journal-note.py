#!/usr/bin/env python3
"""Append a timestamped operator observation without changing any running trial."""
import argparse
import experiment

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('note');parser.add_argument('--journal',choices=['continuous-production','fifo-capacity'],default='continuous-production')
args=parser.parse_args()
experiment.JOURNAL=experiment.ROOT/f'docs/experiments/waffles/2026-11-26-{args.journal}.jsonl'
experiment.record('operator_note',note=args.note)
