#!/usr/bin/env python3
"""Reversible Immich pilot migration using public APIs and a private ledger (#217).

Targets only the isolated pilot. Existing PostgreSQL, originals and the Photos
route are never changed. Credentials and photo exports remain outside Git.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import tarfile
import urllib.error
import urllib.request
import uuid

BASE = 'https://immich.app.home.panderosystems.com/api'
ROOT = Path('/private/tmp/immich-pilot')


def save(name: str, data: dict) -> None:
    """Atomically save private credentials/progress, including after each upload."""
    temporary = ROOT/(name+'.tmp')
    temporary.write_text(json.dumps(data, indent=2))
    temporary.chmod(0o600)
    temporary.replace(ROOT/name)


def request(path: str, method: str = 'GET', body=None, token: str | None = None,
            content_type: str = 'application/json'):
    """Call only the private pilot; do not log credentials or private payloads."""
    headers = {'Content-Type': content_type}
    if token:
        headers['Authorization'] = 'Bearer '+token
    data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE+path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        # The pilot returns validation details; never include request credentials.
        raise RuntimeError(f'{method} {path}: HTTP {error.code}: {error.read().decode()[:1000]}') from None


def login() -> str:
    """Use the locally saved pilot administrator account."""
    credentials = json.loads((ROOT/'credentials.json').read_text())
    return request('/auth/login', 'POST', {k:credentials[k] for k in ('email','password')})['accessToken']


def initialize() -> None:
    """Create the isolated pilot admin once, saving the password before the call."""
    target = ROOT/'credentials.json'
    if not target.exists():
        save('credentials.json', dict(email='photos-pilot@home.panderosystems.com',
                                      name='Photo migration pilot', password=secrets.token_urlsafe(30)))
        request('/auth/admin-sign-up','POST',json.loads(target.read_text()))
    login()
    print('Pilot administrator ready; credentials stored privately at '+str(target))


def export() -> None:
    """Copy a read-only PostgreSQL snapshot and source files from the known host."""
    host = os.environ['CB_HOST']
    script = (Path(__file__).parent/'host/export-immich-pilot.py').read_text()
    subprocess.run(['ssh','-o','BatchMode=yes',host,
                    '/opt/photo-enrichment/gui/venv/bin/python -c '+shlex.quote(script)], check=True)
    subprocess.run(['scp','-q',host+':/local-3TB-backup/photo-enrichment/migrations/immich-pilot.tar',str(ROOT/'sample.tar')],check=True)
    with tarfile.open(ROOT/'sample.tar') as archive:
        archive.extractall(ROOT/'sample', filter='data')
    print('Private sample copied; production data unchanged')


def multipart(fields: dict, filename: str, content: bytes) -> tuple[bytes,str]:
    """Build the small pilot upload without exposing authentication to a subprocess."""
    boundary = 'immich-'+uuid.uuid4().hex
    chunks = []
    for key,value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    # Use a controlled filename. Original path/name are kept in private provenance.
    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="assetData"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+content+b'\r\n')
    chunks.append(f'--{boundary}--\r\n'.encode())
    return b''.join(chunks), 'multipart/form-data; boundary='+boundary


def sample_and_ledger() -> tuple[list,dict]:
    """Read an immutable source export and resumable target-ID ledger."""
    records = json.loads((ROOT/'sample/manifest.json').read_text())['records']
    ledger = json.loads((ROOT/'ledger.json').read_text()) if (ROOT/'ledger.json').exists() else dict(assets={},people={},faces={},albums={})
    return records, ledger


def upload() -> None:
    """Upload unchanged bytes into Immich-managed storage; preserve all source metadata."""
    token = login()
    records,ledger = sample_and_ledger()
    for record in records:
        key = record['key']
        if key in ledger['assets']:
            continue
        photo = ROOT/'sample'/record['filename']
        content = photo.read_bytes()
        if hashlib.sha256(content).hexdigest()!=record['sha256']:
            raise RuntimeError('Export checksum changed')
        metadata = record['metadata'] or {}
        timestamp = metadata.get('capture_ts') or photo.stat().st_mtime
        stamp = dt.datetime.fromtimestamp(timestamp,dt.timezone.utc).isoformat()
        body,content_type = multipart(dict(fileCreatedAt=stamp,fileModifiedAt=stamp),record['filename'],content)
        result = request('/assets','POST',body,token,content_type)
        ledger['assets'][key] = result['id']
        save('ledger.json',ledger)
    print(json.dumps(dict(uploaded_assets=len(ledger['assets']))))


def normalized_face(face: dict) -> list[float]:
    """Convert Immich's own inference-image coordinates into normalized coordinates."""
    return [face['boundingBoxX1']/face['imageWidth'],face['boundingBoxY1']/face['imageHeight'],
            face['boundingBoxX2']/face['imageWidth'],face['boundingBoxY2']/face['imageHeight']]


def overlap(a: list, b: list) -> float:
    """Intersection-over-union of normalized boxes; no image identity inference."""
    area = max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-area
    return area/union if union>0 else 0


def annotate() -> None:
    """Transfer captions/groups and only explicitly human-confirmed face assignments."""
    token = login()
    records,ledger = sample_and_ledger()
    for record in records:
        asset = ledger['assets'][record['key']]
        metadata = record['metadata'] or {}
        fields = {}
        if metadata.get('summary'):
            fields['description'] = metadata['summary']
        if metadata.get('latitude') is not None and metadata.get('longitude') is not None:
            fields.update(latitude=metadata['latitude'],longitude=metadata['longitude'])
        if metadata.get('capture_ts'):
            fields['dateTimeOriginal'] = dt.datetime.fromtimestamp(metadata['capture_ts'],dt.timezone.utc).isoformat()
        if fields:
            request('/assets/'+asset,'PUT',fields,token)
        provenance = {k:v for k,v in record.items() if k not in ('filename','faces')}
        # Preserve provenance without pretending legacy embeddings are Immich embeddings.
        provenance['faces'] = [{k:v for k,v in f.items() if k!='embedding'} for f in record['faces']]
        request('/assets/'+asset+'/metadata','PUT',dict(items=[dict(key='home.photo-enrichment.v1',value=provenance)]),token)
        detected = request('/faces?id='+asset,token=token)
        used = {f['face'] for f in ledger['faces'].values() if f['asset']==asset}
        for old in record['faces']:
            if old.get('label_source')!='user' or not old.get('person'):
                continue
            if old['id'] in ledger['faces']:
                continue
            candidates = sorted([(overlap(old['box'],normalized_face(f)),f) for f in detected if f['id'] not in used],key=lambda pair:pair[0],reverse=True)
            # Require one unambiguous spatial match; manual boxes are a separate review step.
            if not candidates or candidates[0][0]<0.5 or (len(candidates)>1 and candidates[0][0]-candidates[1][0]<0.2):
                continue
            name = old['person']
            if name not in ledger['people']:
                ledger['people'][name] = request('/people','POST',dict(name=name),token)['id']
                save('ledger.json',ledger)
            face = candidates[0][1]
            request('/faces/'+ledger['people'][name],'PUT',dict(id=face['id']),token)
            ledger['faces'][old['id']] = dict(face=face['id'],person=ledger['people'][name],asset=asset,iou=candidates[0][0])
            used.add(face['id'])
            save('ledger.json',ledger)
    if 'pilot' not in ledger['albums']:
        album = request('/albums','POST',dict(albumName='Migration pilot — copied photos',
            description='Copies for validating captions, GPS and confirmed face migration. Original library remains unchanged.',
            assetIds=list(ledger['assets'].values())),token)
        ledger['albums']['pilot'] = album['id']
        save('ledger.json',ledger)
    groups = {g['id']:g for r in records for g in r['groups']}
    for key,group in groups.items():
        if key in ledger['albums']:
            continue
        members = [ledger['assets'][r['key']] for r in records if any(g['id']==key for g in r['groups'])]
        album = request('/albums','POST',dict(albumName=group.get('event') or 'Imported group',
            description=' · '.join(str(group[k]) for k in ('location','venue','notes') if group.get(k)),assetIds=members),token)
        ledger['albums'][key]=album['id']
        save('ledger.json',ledger)
    print(json.dumps(dict(assets=len(ledger['assets']),confirmed_faces_transferred=len(ledger['faces']),people=len(ledger['people']),albums=len(ledger['albums']))))


def verify() -> None:
    """Read back exact captions, coordinates, provenance and face labels."""
    token = login()
    records,ledger = sample_and_ledger()
    failures=[]
    for record in records:
        asset = ledger['assets'][record['key']]
        actual = request('/assets/'+asset,token=token)
        old = record['metadata'] or {}
        exif = actual.get('exifInfo') or {}
        if old.get('summary') and exif.get('description')!=old['summary']:
            failures.append(dict(asset=asset,field='description'))
        if old.get('latitude') is not None and abs((exif.get('latitude') or 0)-old['latitude'])>0.000001:
            failures.append(dict(asset=asset,field='latitude'))
        if old.get('longitude') is not None and abs((exif.get('longitude') or 0)-old['longitude'])>0.000001:
            failures.append(dict(asset=asset,field='longitude'))
        provenance=request('/assets/'+asset+'/metadata',token=token)
        if not any(x['key']=='home.photo-enrichment.v1' and x['value']['sha256']==record['sha256'] for x in provenance):
            failures.append(dict(asset=asset,field='provenance'))
        actual_faces={f['id']:f for f in request('/faces?id='+asset,token=token)}
        for face in ledger['faces'].values():
            if face['asset']==asset and (actual_faces.get(face['face'],{}).get('person') or {}).get('id')!=face['person']:
                failures.append(dict(asset=asset,field='person'))
    expected = [f['id'] for r in records for f in r['faces'] if f.get('label_source')=='user' and f.get('person')]
    pending = [identifier for identifier in expected if identifier not in ledger['faces']]
    result=dict(assets=len(records),confirmed_faces=len(ledger['faces']),
                expected_confirmed_faces=len(expected),pending_confirmed_faces=pending,failures=failures)
    save('verification.json',result)
    print(json.dumps(result))
    if failures:
        raise SystemExit(1)


def tags() -> None:
    """Make existing caption tags and group search terms searchable in Immich."""
    token=login()
    records,ledger=sample_and_ledger()
    for record in records:
        names=set((record['metadata'] or {}).get('summary_tags') or [])
        for group in record['groups']:
            names.update(group.get('tags') or [])
            names.update(group[k] for k in ('event','location','venue') if group.get(k))
        if not names:
            continue
        created=request('/tags','PUT',dict(tags=sorted(names)),token)
        request('/tags/assets','PUT',dict(assetIds=[ledger['assets'][record['key']]],
                                        tagIds=[t['id'] for t in created]),token)
    print('Existing search tags transferred')


def health() -> None:
    """Inspect pilot health and save native metrics for diagnosis/dashboard queries."""
    kube=['kubectl','--kubeconfig',str(Path.home()/'kubeconfig'),'-n','immich-pilot']
    subprocess.run(kube+['get','pods,helmrelease,servicemonitor'],check=True)
    print(request('/server/ping'))
    for port in (8081,8082):
        source=f'fetch("http://127.0.0.1:{port}/metrics",{{headers:{{Accept:"text/plain; version=0.0.4"}}}}).then(async r=>{{if(!r.ok)throw Error(r.status+" "+await r.text());return r.text()}}).then(t=>console.log(t))'
        metrics=subprocess.check_output(kube+['exec','deployment/immich-server','--','node','-e',source],text=True)
        (ROOT/f'metrics-{port}.txt').write_text(metrics)
        print(port, [line for line in metrics.splitlines() if line.startswith('# HELP') and any(w in line.lower() for w in ('job','request','queue','duration'))][:30])


def preserve_missing() -> None:
    """Copy known human-confirmed boxes where Immich detected no overlapping face.

    This preserves an existing annotation, not a new identity prediction. These
    manual faces intentionally have no Immich embedding and remain distinguishable.
    """
    token=login()
    records,ledger=sample_and_ledger()
    for record in records:
        asset=ledger['assets'][record['key']]
        for old in record['faces']:
            if old.get('label_source')!='user' or not old.get('person') or old['id'] in ledger['faces']:
                continue
            current=request('/faces?id='+asset,token=token)
            if any(overlap(old['box'],normalized_face(f))>=0.1 for f in current):
                continue  # Ambiguous matches stay pending, never create overlapping duplicates.
            name=old['person']
            if name not in ledger['people']:
                ledger['people'][name]=request('/people','POST',dict(name=name),token)['id']
                save('ledger.json',ledger)
            width,height=record['oriented_size']
            x1,y1,x2,y2=old['box']
            x,y=round(x1*width),round(y1*height)
            request('/faces','POST',dict(assetId=asset,personId=ledger['people'][name],
                imageWidth=width,imageHeight=height,x=x,y=y,
                width=round(x2*width)-x,height=round(y2*height)-y),token)
            after=request('/faces?id='+asset,token=token)
            candidates=[f for f in after if (f.get('person') or {}).get('id')==ledger['people'][name]
                        and overlap(old['box'],normalized_face(f))>0.95]
            if len(candidates)!=1:
                raise RuntimeError('Could not unambiguously verify imported manual face')
            ledger['faces'][old['id']]=dict(face=candidates[0]['id'],person=ledger['people'][name],
                asset=asset,source='preserved-manual',iou=overlap(old['box'],normalized_face(candidates[0])))
            save('ledger.json',ledger)
    verify()


def main() -> None:
    """Perform one explicit, resumable pilot step."""
    os.umask(0o077)
    ROOT.mkdir(mode=0o700,exist_ok=True)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['initialize','export','upload','annotate','verify','preserve-missing','tags','health'])
    action=parser.parse_args().action
    globals()[action.replace('-','_')]()


if __name__=='__main__':
    main()
