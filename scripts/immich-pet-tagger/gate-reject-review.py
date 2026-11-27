#!/usr/bin/env python3
"""Gate frontier review on complete blinded holdouts and incremental recovery."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE

spec = importlib.util.spec_from_file_location('frontier', Path(__file__).with_name('frontier-review.py'))
frontier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frontier)


def evaluate(records: list, truth: dict, local: dict, errors: int) -> dict:
    """Fail closed on missing, duplicate, mislabeled or failed evaluation inputs."""
    expected = {asset: label for label in ('positive', 'negative') for asset in truth[label]}
    ids = [r['asset_id'] for r in records]
    complete = (len(expected) == 26 and len(truth['positive']) == 13
                and len(truth['negative']) == 13 and len(ids) == 26
                and set(ids) == set(expected) and set(local) == set(expected)
                and all(r['expected'] == expected[r['asset_id']] for r in records)
                and errors == 0)
    accepted = {r['asset_id'] for r in records if frontier.accept(r)}
    tp = len(accepted & set(truth['positive']))
    fp = len(accepted & set(truth['negative']))
    incremental = len({asset for asset in accepted & set(truth['positive']) if local.get(asset) is False})
    return {'evaluated': len(ids), 'complete': complete, 'true_positive': tp,
            'false_positive': fp, 'false_negative': 13-tp, 'true_negative': 13-fp,
            'additional_local_misses_recovered': incremental,
            'eligible_for_fallback': complete and fp == 0 and incremental > 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage',choices=['v2','v3-single'],default='v2')
    parser.add_argument('--models',nargs='+',choices=['luna','sol'],default=['luna','sol'])
    args = parser.parse_args()
    os.umask(0o077)
    baseline = args.directory/'local-holdout.json'
    if not baseline.exists():
        code = """import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();console.log(JSON.stringify((await db.query(
"SELECT asset_id,result FROM waffles.jobs WHERE run_id='holdout-still-fawn' AND status='complete'"
)).rows));await db.end();"""
        data = subprocess.check_output(KUBE+['-n','immich-pilot','exec','-i',
            'deployment/waffles-queue','--','node','--input-type=module','-'], input=code, text=True)
        baseline.write_text(json.dumps(json.loads(data), indent=2)+'\n')
    local = {r['asset_id']: bool(r['result']['matches']) for r in json.loads(baseline.read_text())}
    truth = json.loads((args.directory.parent/'owner-confirmed-holdout.json').read_text())
    report = {'at': datetime.now(timezone.utc).isoformat(), 'protocol_version': 3 if args.stage=='v3-single' else 2,
              'reference_images': 6, 'eligible_models': [], 'models': {}}
    for model in args.models:
        directory = args.directory/f'eval-{model}-{args.stage}'
        records = json.loads((directory/'records.json').read_text())
        summary = json.loads((directory/'summary.json').read_text())
        result = evaluate(records, truth, local, summary['error_batches'])
        result.update(model=frontier.MODELS[model],
                      protocol_sha256=hashlib.sha256((directory/'protocol.json').read_bytes()).hexdigest(),
                      input_tokens=summary['input_tokens'], output_tokens=summary['output_tokens'])
        report['models'][model] = result
        if result['eligible_for_fallback']: report['eligible_models'].append(model)
    report['limits'] = '13 negative controls; high confidence is categorical, not a calibrated probability. All proposed recoveries require independent visual review.'
    encoded = json.dumps(report, indent=2)+'\n'
    (args.directory/('evaluation-gate-v3-single.json' if args.stage=='v3-single' else 'evaluation-gate.json')).write_text(encoded)
    args.output.write_text(encoded)
    print(encoded)


if __name__ == '__main__': main()
