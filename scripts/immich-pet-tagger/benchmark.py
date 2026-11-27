#!/usr/bin/env python3
"""Run matched, reversed-order CPU versus distributed benchmarks without Immich writes."""
import argparse
import json
import logging
from pathlib import Path
import time
from distributed import request


def run(identifier: str, assets: list, workers: list) -> list:
    """Resume a named sample and stop on any failed inference."""
    rows = [r for r in request('/admin/status')['runs'] if r['id'] == identifier]
    if not rows:
        request('/admin/run', dict(id=identifier, mode='benchmark', workers=workers, assets=assets))
        request('/admin/state', dict(id=identifier, state='running'))
    while True:
        rows = [r for r in request('/admin/status')['runs'] if r['id'] == identifier]
        completed = sum(r['jobs'] for r in rows if r['status'] == 'complete')
        logging.info('%s: %d/%d complete', identifier, completed, len(assets))
        if any(r['status'] == 'failed' for r in rows):
            request('/admin/state', dict(id=identifier, state='paused'))
            raise RuntimeError('Benchmark failed; inspect worker health before continuing')
        if completed == len(assets):
            return rows
        time.sleep(15)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sample', type=Path)
    parser.add_argument('--warmup-only', action='store_true')
    args = parser.parse_args()
    assets = json.loads(args.sample.read_text())
    workers = ['mac', 'pve', 'still-fawn']
    while True:
        ready = {w['name'] for w in request('/admin/status')['workers'] if w['ready']}
        if set(workers) <= ready:
            break
        logging.info('Waiting for models: %s', ', '.join(set(workers) - ready))
        time.sleep(15)
    for worker in workers:
        run('warmup-' + worker, assets[:3], [worker])
    if args.warmup_only:
        return
    # ABBA order and reversed samples reduce order and warmed-cache bias.
    for name, sample, pool in [('before-1', assets, ['still-fawn']), ('after-1', assets, workers),
                               ('after-2', list(reversed(assets)), workers),
                               ('before-2', list(reversed(assets)), ['still-fawn'])]:
        run(name, sample, pool)


if __name__ == '__main__':
    main()
