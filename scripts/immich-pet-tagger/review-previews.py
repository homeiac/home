#!/usr/bin/env python3
"""Fetch selected higher-resolution previews from a private candidate manifest."""
import argparse
import json
from pathlib import Path
import urllib.request
from immich_client import BASE, key

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('manifest', type=Path)
parser.add_argument('indices', nargs='+', type=int)
args = parser.parse_args()
items = json.loads(args.manifest.read_text())
for index in args.indices:
    asset = items[index]['id']
    req = urllib.request.Request(BASE+'/api/assets/'+asset+'/thumbnail?size=preview',
                                 headers={'x-api-key': key()})
    with urllib.request.urlopen(req, timeout=60) as response:
        content = response.read()
    target = args.manifest.parent/f'preview-{index:03d}.jpg'
    target.write_bytes(content)
    print(target)
