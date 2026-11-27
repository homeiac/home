#!/usr/bin/env python3
"""Report aggregate progress, explicitly separating invalidated batch trials."""
import argparse
from collections import Counter
import json
from pathlib import Path


def read_records(directory: Path) -> tuple:
    batches = [json.loads(p.read_text()) for p in sorted(directory.glob('batch-*/settled.json'))]
    return batches, [r for b in batches for r in b.get('records', [])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--prepare-sol',action='store_true')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if args.prepare_sol:
        raise ValueError('Batched triage invalidated: review the full cohort using v3-single')
    nine = {r['asset_id'] for r in json.loads((args.directory/'nine-misses.json').read_text())}
    report = {}
    for model in ('luna','sol','sol-single'):
        batches, records = read_records(args.directory/('review-sol-v3-single' if model=='sol-single' else f'review-{model}-v2'))
        report[model] = {'settled_batches':len(batches),'evaluated':len(records),
            'production_valid':model=='sol-single',
            'protocol_note':'Single target per request; visual verification required' if model=='sol-single' else 'Invalidated batched protocol; never use these decisions for tagging',
            'errors':sum(b['status']!='complete' for b in batches),
            'decisions':dict(Counter(r['answer']['verdict']+'/'+r['answer']['confidence'] for r in records)),
            'original_nine':dict(Counter(r['answer']['verdict']+'/'+r['answer']['confidence'] for r in records if r['asset_id'] in nine))}
    if args.output: args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
