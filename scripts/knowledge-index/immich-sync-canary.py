#!/usr/bin/env python3
"""Verify owned metadata on one matched external asset, preserving all native fields."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import urllib.request

BASE='https://immich.app.home.panderosystems.com/api'
KEY='home.knowledge-index.canary.v1'

def run(root,mode):
    token=Path('/private/tmp/immich-sync-api-key').read_text().strip()
    def api(path,method='GET',data=None):
        request=urllib.request.Request(BASE+path,method=method,headers={'x-api-key':token,'Content-Type':'application/json'},data=None if data is None else json.dumps(data).encode())
        with urllib.request.urlopen(request,timeout=45) as response:
            raw=response.read();return json.loads(raw) if raw else None
    def native(asset):
        exif=asset.get('exifInfo') or {}
        return {k:exif.get(k) for k in ['description','latitude','longitude','dateTimeOriginal']}
    saved=root/'canary.json'
    if mode=='write':
        if saved.exists():raise RuntimeError('Canary record exists; use verify')
        source={x['path']:x for x in map(json.loads,(root/'source.jsonl').read_text().splitlines())}
        candidates=[x for x in map(json.loads,(root/'target.jsonl').read_text().splitlines()) if x['is_external'] and not x['is_deleted'] and not x['is_offline'] and x['original_path'].startswith('/external/gphotos/')]
        candidate=next(x for x in candidates if (s:=source.get(x['original_path'].removeprefix('/external/gphotos/'))) and s.get('summary') and x['size_bytes']==s['size_bytes'])
        asset_id=candidate['id'];asset=api('/assets/'+asset_id);metadata=api('/assets/'+asset_id+'/metadata')
        if any(x['key']==KEY for x in metadata):raise RuntimeError('Canary key already exists')
        payload={'schemaVersion':1,'purpose':'read-only external-library persistence test','sourcePath':candidate['original_path'].removeprefix('/external/gphotos/'),'summary':source[candidate['original_path'].removeprefix('/external/gphotos/')]['summary']}
        record={'assetId':asset_id,'baselineNative':native(asset),'baselineMetadata':metadata,'expected':payload,'createdAt':dt.datetime.now(dt.timezone.utc).isoformat()}
        saved.write_text(json.dumps(record,indent=2));saved.chmod(0o600)
        api('/assets/'+asset_id+'/metadata','PUT',{'items':[{'key':KEY,'value':payload}]})
    record=json.loads(saved.read_text());asset_id=record['assetId']
    actual=api('/assets/'+asset_id+'/metadata')
    assert next(x['value'] for x in actual if x['key']==KEY)==record['expected'],'Metadata did not round trip'
    assert native(api('/assets/'+asset_id))==record['baselineNative'],'Native fields changed'
    print(json.dumps({'metadata_readback':'passed','native_description_gps_date':'unchanged','asset_url':'https://immich.app.home.panderosystems.com/photos/'+asset_id}))
    if mode=='cleanup':
        api('/assets/'+asset_id+'/metadata/'+KEY,'DELETE')
        assert not any(x['key']==KEY for x in api('/assets/'+asset_id+'/metadata'))
        print('Canary key removed; original metadata retained.')

if __name__=='__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['write','verify','cleanup']);p.add_argument('--audit',type=Path,required=True)
    args=p.parse_args();run(args.audit,args.mode)
