#!/usr/bin/env python3
"""Register/inspect the existing canonical Google Photos library in Immich (#217).

Uses the private credentials created by immich-pilot.py. Originals remain mounted
read-only. Import only year folders: album copies, Trash and Locked Folder are
not accidentally exposed. This does not migrate legacy annotations.
"""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess

spec = importlib.util.spec_from_file_location('immich_pilot', Path(__file__).with_name('immich-pilot.py'))
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
NAME = 'Existing Google Photos'
KUBE = ['kubectl', '--kubeconfig', str(Path.home()/'kubeconfig'), '-n', 'immich-pilot']


def import_paths() -> list[str]:
    """Discover actual year folders through the server's read-only mount."""
    script = '''const fs=require("fs");const root="/external/gphotos/Google Photos";
const mount=fs.readFileSync("/proc/self/mountinfo","utf8").split("\\n").find(x=>x.includes(" /external/gphotos "));
if(!mount || !mount.split(" ")[5].split(",").includes("ro"))throw Error("Expected read-only originals");
console.log(JSON.stringify(fs.readdirSync(root,{withFileTypes:true}).filter(x=>x.isDirectory()&&/^Photos from [0-9]{4}$/.test(x.name)).map(x=>root+"/"+x.name).sort()));'''
    paths = json.loads(subprocess.check_output(KUBE+['exec', 'deployment/immich-server', '--', 'node', '-e', script], text=True))
    if not paths or len(paths)>128:
        raise RuntimeError('Unexpected year-folder inventory')
    return paths


def backup() -> None:
    """Save a consistent logical DB backup before creating application records."""
    directory = pilot.ROOT/'library-registration'
    directory.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = directory/(stamp+'.dump')
    with target.open('xb') as output:
        subprocess.run(KUBE+['exec','deployment/immich-postgres','--','pg_dump','-U','immich','-d','immich','-Fc'], stdout=output, check=True)


def run(action: str) -> None:
    """Inspect or idempotently register and scan the existing year folders."""
    token = pilot.login()
    libraries = pilot.request('/libraries', token=token)
    if action == 'register':
        paths = import_paths()
        owner = pilot.request('/users/me', token=token)['id']
        matched = [x for x in libraries if x['name']==NAME and x['ownerId']==owner]
        if len(matched)>1:
            raise RuntimeError('Multiple matching libraries; inspect before changing')
        if matched:
            library = matched[0]
            if sorted(library['importPaths'])!=paths:
                raise RuntimeError('Existing import scope differs; refusing to offline existing assets')
        else:
            if any(set(x.get('importPaths',[])) & set(paths) for x in libraries):
                raise RuntimeError('Year folders already registered in another library')
            backup()
            library = pilot.request('/libraries','POST',dict(name=NAME,ownerId=owner,importPaths=paths,exclusionPatterns=[]),token)
        validation = pilot.request('/libraries/'+library['id']+'/validate','POST',dict(importPaths=paths,exclusionPatterns=[]),token)
        results = validation.get('importPaths',[])
        if len(results)!=len(paths) or any(x.get('isValid') is not True for x in results):
            pilot.save('library-validation.json',validation)
            raise RuntimeError('Import paths failed validation; scan not started')
        pilot.save('external-library.json',dict(id=library['id'],ownerId=owner,importPaths=paths))
        pilot.request('/libraries/'+library['id']+'/scan','POST',token=token)
        print(json.dumps(dict(scan_queued=True,year_folders=len(paths))))
        libraries = pilot.request('/libraries',token=token)
    for library in libraries:
        stats = pilot.request('/libraries/'+library['id']+'/statistics',token=token)
        print(json.dumps(dict(name=library['name'],id=library['id'],folders=len(library['importPaths']),statistics=stats)))
    print(json.dumps(dict(account_assets=pilot.request('/assets/statistics',token=token))))


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['status','register'])
    run(parser.parse_args().action)
