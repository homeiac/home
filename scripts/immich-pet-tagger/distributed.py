#!/usr/bin/env python3
"""Operate the fenced Waffles queue; private inventory and classifier stay outside Git."""
import argparse
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import subprocess
import urllib.request

HERE = Path(__file__).resolve().parent
BASE = os.environ.get('WAFFLES_QUEUE_URL', 'https://pets-queue.app.home.panderosystems.com')
KUBE = ['kubectl', '--kubeconfig', str(Path.home() / 'kubeconfig')]


def secret(key: str) -> str:
    """Read one scoped key into memory, never logs or command arguments."""
    raw = subprocess.check_output(KUBE + ['-n', 'immich-pilot', 'get', 'secret', 'waffles-queue', '-o', 'json'], text=True)
    return base64.b64decode(json.loads(raw)['data'][key]).decode()


def request(path: str, body=None):
    req = urllib.request.Request(BASE + path, headers={'Authorization': 'Bearer ' + secret('admin-token'), 'Content-Type': 'application/json'},
                                 data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.load(response)


def export_private(directory: Path) -> None:
    """Capture fitted classifier and owner-filtered inventory without redoing inference."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    export = subprocess.run(KUBE + ['-n', 'immich-pilot', 'exec', '-i', 'deployment/immich-pet-tagger', '--', 'python', '-'],
                            input=(HERE / 'export-classifier.py').read_text(), text=True, capture_output=True, check=True)
    classifier = json.loads(export.stdout)
    (directory / 'classifier.json').write_text(json.dumps(classifier))
    code = '''import json,sys
sys.path.insert(0,'/app')
import immich
assert immich.get_owner_id(), 'Owner identity required'
items=immich.fetch_assets_in_range('1900-01-01T00:00:00.000Z','2026-11-26T23:59:59.999Z')
print(json.dumps([{'id':a['id'],'date':a['fileCreatedAt'],'type':a['type']} for a in items]))
'''
    output = subprocess.run(KUBE + ['-n', 'immich-pilot', 'exec', '-i', 'deployment/immich-pet-tagger', '--', 'python', '-'],
                            input=code, text=True, capture_output=True, check=True)
    assets = json.loads(output.stdout)
    assert len({a['id'] for a in assets}) == len(assets)
    (directory / 'inventory.json').write_text(json.dumps(assets))
    # Evenly cover the whole chronology, plus a reproducible shuffle. Same inputs
    # are used for both profiles; no result cache is read by distributed workers.
    photos = [a for a in assets if a['type'] == 'IMAGE']
    selected = [photos[i * (len(photos) - 1) // 95] for i in range(96)]
    random.Random(244).shuffle(selected)
    (directory / 'benchmark.json').write_text(json.dumps(selected))
    logging.info('Captured private classifier, %d assets and %d matched benchmark photos', len(assets), len(selected))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export'); export.add_argument('directory', type=Path)
    config = commands.add_parser('config'); config.add_argument('file', type=Path)
    run = commands.add_parser('create'); run.add_argument('id'); run.add_argument('file', type=Path)
    run.add_argument('--mode', choices=['benchmark', 'production'], required=True)
    run.add_argument('--workers', nargs='+', required=True, choices=['mac', 'pve', 'still-fawn', 'fun-bedbug', 'chief-horse'])
    run.add_argument('--reverse', action='store_true')
    state = commands.add_parser('state'); state.add_argument('id'); state.add_argument('state', choices=['paused', 'running'])
    status = commands.add_parser('status'); status.add_argument('--compact', action='store_true')
    discovery = commands.add_parser('discovery'); discovery.add_argument('--since', required=True)
    discovery.add_argument('--disabled', action='store_true')
    workers = commands.add_parser('workers'); workers.add_argument('id')
    workers.add_argument('names', nargs='+', choices=['mac', 'pve', 'still-fawn', 'fun-bedbug', 'chief-horse'])
    tune=commands.add_parser('tune');tune.add_argument('worker',choices=['mac','pve','still-fawn','fun-bedbug','chief-horse'])
    tune.add_argument('slots',type=int);tune.add_argument('--note',default='Operator live tuning')
    burst=commands.add_parser('burst');burst.add_argument('worker',choices=['mac','pve','still-fawn','fun-bedbug','chief-horse'])
    burst.add_argument('slots',type=int);burst.add_argument('--mode',choices=['production','benchmark'],default='production');burst.add_argument('--note',default='Operator extra capacity')
    burst.add_argument('--cpu-cores',type=int,help='Linux extra-worker CPU affinity count; baseline affinity is unchanged')
    burst.add_argument('--device',choices=['cpu','mps'],help='Compute device for extra workers only; baseline device is unchanged')
    burst.add_argument('--threads',type=int,help='Mac CPU inference threads per extra process; drains/replaces extras, never baseline')
    commands.add_parser('tuning')
    args = parser.parse_args()
    if args.command == 'export':
        export_private(args.directory)
    elif args.command == 'config':
        logging.info('%s', request('/admin/config', json.loads(args.file.read_text())))
    elif args.command == 'create':
        assets = json.loads(args.file.read_text())
        if args.reverse:
            assets.reverse()
        logging.info('%s', request('/admin/run', {'id': args.id, 'mode': args.mode, 'workers': args.workers, 'assets': assets}))
    elif args.command == 'state':
        logging.info('%s', request('/admin/state', {'id': args.id, 'state': args.state}))
    elif args.command == 'discovery':
        logging.info('%s', request('/admin/discovery', {'enabled': not args.disabled, 'since': args.since}))
    elif args.command == 'workers':
        logging.info('%s', request('/admin/workers', {'id': args.id, 'workers': args.names}))
    elif args.command == 'tune':
        if args.slots<1:raise ValueError('Keep one baseline worker; use burst WORKER 0 to drain extra workers')
        logging.info('%s',request('/admin/burst',{'worker':args.worker,'slots':args.slots-1,'mode':'production','note':args.note}))
    elif args.command == 'burst':
        logging.info('%s',request('/admin/burst',{'worker':args.worker,'slots':args.slots,'mode':args.mode,'note':args.note,**({'cpu_cores':args.cpu_cores} if args.cpu_cores is not None else {}),**({'device':args.device} if args.device else {}),**({'cpu_threads':args.threads} if args.threads is not None else {})}))
    elif args.command == 'tuning':
        logging.info('%s',json.dumps({'baseline':request('/api/tuning'),'extra':request('/api/burst')},indent=2))
    else:
        data = request('/admin/status')
        if args.compact:
            grouped = {}
            for row in data['runs']:
                if row['mode'] != 'production':
                    continue
                item = grouped.setdefault(row['id'], {'state': row['state'], 'statuses': {}, 'processed_by_backend': {}})
                item['statuses'][row['status']] = item['statuses'].get(row['status'], 0) + row['jobs']
                if row['status'] == 'complete':
                    item['processed_by_backend'][row['worker']] = row['jobs']
            data = {'runs': grouped, 'workers': [{k: w[k] for k in ('name', 'ready', 'device', 'active_instances') if k in w} for w in data['workers']], 'discovery': data.get('discovery')}
        logging.info('%s', json.dumps(data, indent=2))


if __name__ == '__main__':
    main()
