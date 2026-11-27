#!/usr/bin/env python3
"""Operate the private tagger using reviewed local JSON inputs, never secrets in Git."""
import argparse
import json
import os
from pathlib import Path
import urllib.request

BASE = os.environ.get('PET_TAGGER_URL', 'https://pets.app.home.panderosystems.com')


def request(path: str, body=None):
    """Read status or submit a deliberately selected operation."""
    req = urllib.request.Request(BASE+'/api'+path,
        headers={'Content-Type': 'application/json'},
        data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.load(response)


def main() -> None:
    """Use explicit modes so inspection cannot accidentally trigger a scan."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    enroll = commands.add_parser('enroll')
    enroll.add_argument('--selection', type=Path, required=True,
        help='Private JSON containing references and negatives arrays of asset UUIDs')
    scan = commands.add_parser('scan')
    scan.add_argument('--since', required=True)
    scan.add_argument('--until', required=True)
    commands.add_parser('stop')
    args = parser.parse_args()
    if args.command == 'status':
        for path in ['/version', '/pets', '/negatives', '/poll-status', '/scan/result']:
            result = request(path)
            if path == '/negatives':
                result = {'count': result['count']}
            print(json.dumps({'path': path, 'result': result}))
    elif args.command == 'enroll':
        selection = json.loads(args.selection.read_text())
        if len(selection['references']) < 10 or len(selection['negatives']) < 10:
            raise SystemExit('Select at least 10 reviewed positive and negative examples first')
        pets = request('/pets')['pets']
        if not any(p['name'] == 'Waffles' for p in pets):
            request('/pets', {'name': 'Waffles', 'description': 'tan dog upright ears'})
        # References replace the set upstream: combine with existing entries on reruns.
        current = request('/pets/Waffles/assets')
        refs = list(dict.fromkeys([a['id'] for a in current['assets']] + selection['references']))
        print(json.dumps(request('/negatives', {'asset_ids': selection['negatives']})))
        print(json.dumps(request('/pets/Waffles/assets', {'asset_ids': refs})))
    elif args.command == 'scan':
        print(json.dumps(request('/scan', {'scan_since': args.since, 'scan_until': args.until})))
    elif args.command == 'stop':
        print(json.dumps(request('/scan/stop', {})))


if __name__ == '__main__':
    main()
