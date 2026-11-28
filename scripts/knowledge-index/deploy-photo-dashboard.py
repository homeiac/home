#!/usr/bin/env python3
"""Inspect or publish the photo dashboard with a guarded copy of the live GUI release."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

NAMES = ['photo_enrichment/'+name for name in (
    'server.py', 'telemetry.py', 'static/index.html', 'static/app.js', 'static/style.css',
    'static/context.html', 'static/context.js', 'static/context.css', 'static/cricket.html')]
REMOTE = r'''
import hashlib,json,os,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
os.umask(0o077)
v=json.load(sys.stdin);root=Path('/opt/photo-enrichment');link=root/'gui';live=link.resolve()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
unit=Path('/etc/systemd/system/photo-enrichment-gui.service')
if v['mode']=='inspect':
 files={n:(live/n).read_text() if (live/n).exists() else None for n in v['names']}
 print(json.dumps(dict(release=str(live),unit_hash=digest(unit),files=files,hashes={n:digest(live/n) for n in v['names']})))
else:
 if str(live)!=v['release'] or digest(unit)!=v['unit_hash']:raise RuntimeError('Live release changed; inspect again')
 for name,expected in v['hashes'].items():
  if digest(live/name)!=expected:raise RuntimeError('Live file changed: '+name)
 stamp=str(time.time_ns());backup=root/'backups'/('dashboard-'+stamp);backup.mkdir(parents=True)
 (backup/'previous-release.txt').write_text(str(live));shutil.copy2(unit,backup/unit.name)
 release=root/'releases'/('dashboard-'+stamp)
 shutil.copytree(live,release,symlinks=True,ignore=shutil.ignore_patterns('venv','__pycache__'))
 (release/'venv').symlink_to(live/'venv')
 for name,content in v['files'].items():
  target=release/name
  if not target.resolve().is_relative_to(release):raise ValueError('Invalid release path')
  target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
 subprocess.run([str(release/'venv/bin/python'),'-m','compileall','-q',str(release/'photo_enrichment')],check=True,timeout=30)
 try:
  temporary=root/'gui.dashboard-new';temporary.unlink(missing_ok=True);temporary.symlink_to(release);temporary.replace(link)
  subprocess.run(['systemctl','restart',unit.name],check=True,timeout=120)
  for attempt in range(30):
   try:
    with urllib.request.urlopen('http://127.0.0.1:8765/',timeout=3) as r:assert b'<title>Photo dashboard</title>' in r.read()
    with urllib.request.urlopen('http://127.0.0.1:8765/context',timeout=3) as r:assert b'<title>Event notes' in r.read()
    with urllib.request.urlopen('http://127.0.0.1:8765/api/status',timeout=3) as r:assert json.load(r)['backend']=='postgres'
    with urllib.request.urlopen('http://127.0.0.1:8765/api/config',timeout=3) as r:config=json.load(r)
    if config.get('cricket'):
     with urllib.request.urlopen('http://127.0.0.1:8765/cricket',timeout=3) as r:assert r.status==200
    break
   except (OSError,ValueError,AssertionError):time.sleep(1)
  else:raise RuntimeError('Dashboard readiness checks failed')
 except BaseException:
  temporary=root/'gui.dashboard-rollback';temporary.unlink(missing_ok=True);temporary.symlink_to(live);temporary.replace(link)
  subprocess.run(['systemctl','restart',unit.name],check=True,timeout=120)
  raise
 print(json.dumps(dict(release=str(release),backup=str(backup),status='healthy')))
'''


def remote(host: str, payload: dict) -> str:
    """Pass code and JSON through stdin without credentials or shell interpolation."""
    import shlex
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host,
                             'python3 -c '+shlex.quote(REMOTE)], input=json.dumps(payload),
                            capture_output=True, text=True, timeout=240)
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    return result.stdout


def main() -> None:
    """Prepare a merged payload for review before applying the exact saved files."""
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['inspect','prepare','apply'])
    p.add_argument('--host',required=True)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--payload',type=Path)
    p.add_argument('--base',default='e35ca5dccdaad85e27935829d13f2a69ac713a19')
    a=p.parse_args()
    if a.mode=='inspect':
        result=remote(a.host,dict(mode='inspect',names=NAMES))
        a.snapshot.write_text(result);a.snapshot.chmod(0o600)
        print(json.dumps({'release':json.loads(result)['release']}));return
    if not a.payload:p.error('--payload is required')
    if a.mode=='apply':
        print(remote(a.host,json.loads(a.payload.read_text())),end='');return
    value=json.loads(a.snapshot.read_text());files={}
    here=Path(__file__).resolve().parent
    # Replace the landing page intentionally, while retaining concurrently deployed
    # server fixes and the cricket app through a three-way merge.
    for name in NAMES:
        ours=(here/name).read_text()
        if name in ('photo_enrichment/server.py','photo_enrichment/telemetry.py','photo_enrichment/static/cricket.html'):
            base=subprocess.check_output(['git','show',a.base+':scripts/knowledge-index/'+name],text=True)
            with tempfile.TemporaryDirectory() as folder:
                paths=[Path(folder)/n for n in ('live','base','ours')]
                for path,content in zip(paths,[value['files'][name],base,ours]):path.write_text(content)
                result=subprocess.run(['git','merge-file','-p',*[str(path) for path in paths]],capture_output=True,text=True)
                if result.returncode:raise RuntimeError('Review merge conflict: '+name)
                ours=result.stdout
        files[name]=ours
    value.update(mode='apply',files=files)
    a.payload.write_text(json.dumps(value));a.payload.chmod(0o600)
    print(json.dumps({'prepared_files':list(files),'release':value['release']}))


if __name__=='__main__':main()
