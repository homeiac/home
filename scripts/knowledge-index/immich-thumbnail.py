#!/usr/bin/env python3
"""Diagnose or regenerate a specific Immich thumbnail via the API (#217).

Credentials come from the private pilot credential file, never command arguments.
Default mode only reads status. --regenerate queues derived images, not originals.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import urllib.error
import urllib.request
import uuid

spec = importlib.util.spec_from_file_location('pilot', Path(__file__).with_name('immich-pilot.py'))
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def inspect(asset: str, regenerate: bool = False) -> None:
    """Compare grid, preview and original HTTP results without printing photo data."""
    asset = str(uuid.UUID(asset))
    token = pilot.login()
    info = pilot.request('/assets/'+asset,token=token)
    print(json.dumps({k:info.get(k) for k in ('id','type','isOffline','isExternal','resized','hasMetadata','thumbhash')}))
    for label,suffix in [('thumbnail','/thumbnail?size=thumbnail'),('preview','/thumbnail?size=preview'),('original','/original')]:
        req = urllib.request.Request(pilot.BASE+'/assets/'+asset+suffix,headers={'Authorization':'Bearer '+token})
        try:
            with urllib.request.urlopen(req,timeout=120) as response:
                print(json.dumps(dict(kind=label,status=response.status,content_type=response.headers.get('Content-Type'),bytes=response.headers.get('Content-Length'))))
        except urllib.error.HTTPError as error:
            print(json.dumps(dict(kind=label,status=error.code,error=error.read().decode()[:300])))
    if regenerate:
        pilot.request('/assets/jobs','POST',dict(assetIds=[asset],name='regenerate-thumbnail'),token)
        print('Thumbnail regeneration queued')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('asset')
    parser.add_argument('--regenerate',action='store_true')
    args = parser.parse_args()
    inspect(args.asset,args.regenerate)
