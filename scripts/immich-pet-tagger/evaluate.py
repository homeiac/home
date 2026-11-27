#!/usr/bin/env python3
"""Run the reproducible, non-writing classifier check on a private held-out set."""
import argparse
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('examples', type=Path)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
source = Path(__file__).with_name('evaluate-in-pod.py').read_text()
with args.examples.open('rb') as input_file, args.output.open('wb') as output_file:
    args.output.chmod(0o600)
    result = subprocess.run(['kubectl', '--kubeconfig', os.path.expanduser('~/kubeconfig'),
        '-n', 'immich-pilot', 'exec', '-i', 'deployment/immich-pet-tagger', '--',
        'python', '-c', source], stdin=input_file, stdout=output_file, stderr=subprocess.STDOUT)
if result.returncode:
    raise SystemExit(f'Evaluation failed; inspect the private log at {args.output}')
print(f'Evaluation complete: {args.output}')
