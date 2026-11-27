#!/usr/bin/env python3
"""Install isolated, resource-guarded native workers on inventory-verified hosts."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
from distributed import secret

HERE=Path(__file__).resolve().parent
HOSTS={'fun-bedbug':'fun-bedbug.maas','chief-horse':'chief-horse.maas'}

REMOTE=r'''
import base64,ctypes,hashlib,io,json,os,pathlib,pwd,shutil,subprocess,sys,tarfile,time,urllib.request
p=json.load(sys.stdin);root=pathlib.Path('/opt/waffles-worker');data=pathlib.Path('/var/lib/waffles-worker')
os.umask(0o077)
root.mkdir(parents=True,exist_ok=True)
if (root/'worker.py').exists():
 backup=root/('backup-'+str(int(time.time())));backup.mkdir()
 for name in ['worker.py','native_guard.py','requirements.txt']:
  if (root/name).exists():shutil.copy2(root/name,backup/name)
try:account=pwd.getpwnam('waffles-worker')
except KeyError:
 subprocess.run(['useradd','--system','--home-dir',str(data),'--shell','/usr/sbin/nologin','waffles-worker'],check=True)
 account=pwd.getpwnam('waffles-worker')
data.mkdir(exist_ok=True);os.chown(data,account.pw_uid,account.pw_gid)
def download(url,digest):
 with urllib.request.urlopen(url,timeout=120) as response:content=response.read()
 if hashlib.sha256(content).hexdigest()!=digest:raise RuntimeError('Archive digest mismatch')
 return content
uv=root/'uv'
if not uv.exists():
 with tarfile.open(fileobj=io.BytesIO(download(p['lock']['uv_url'],p['lock']['uv_sha256']))) as tar:
  member=next(m for m in tar.getmembers() if m.name.endswith('/uv') and m.isfile())
  uv.write_bytes(tar.extractfile(member).read());uv.chmod(0o755)
app=root/'upstream/app'
if not app.exists():
 with tarfile.open(fileobj=io.BytesIO(download(p['upstream']['url'],p['upstream']['sha256']))) as tar:
  for member in tar.getmembers():
   parts=pathlib.PurePosixPath(member.name).parts
   if len(parts)<2 or parts[1]!='app' or '..' in parts:continue
   target=root/'upstream'/pathlib.Path(*parts[1:])
   if member.isdir():target.mkdir(parents=True,exist_ok=True)
   elif member.isfile():
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(tar.extractfile(member).read());target.chmod(0o644)
requirements=p['requirements'].replace('torch==2.7.0\n','torch==2.7.0+cpu\n').replace('torchvision==0.22.0\n','torchvision==0.22.0+cpu\n')
(root/'requirements.txt').write_text(requirements)
env={**os.environ,'UV_PYTHON_INSTALL_DIR':str(root/'python'),'UV_CACHE_DIR':'/var/cache/waffles-worker'}
if not (root/'venv/bin/python').exists():
 subprocess.run([str(uv),'venv','--python',p['lock']['python'],str(root/'venv')],env=env,check=True)
subprocess.run([str(uv),'pip','install','--python',str(root/'venv/bin/python'),'--extra-index-url','https://download.pytorch.org/whl/cpu','--index-strategy','unsafe-best-match','-r',str(root/'requirements.txt')],env=env,check=True)
# Use the headless OpenCV build with the same exact version; the model worker
# never opens a GUI. This avoids adding graphics libraries to the hypervisor.
version=subprocess.check_output([str(root/'venv/bin/python'),'-c','import importlib.metadata;print(importlib.metadata.version("opencv-python"))'],text=True).strip()
subprocess.run([str(uv),'pip','uninstall','--python',str(root/'venv/bin/python'),'opencv-python'],env=env,check=True)
subprocess.run([str(uv),'pip','install','--python',str(root/'venv/bin/python'),'--no-deps','--reinstall','opencv-python-headless=='+version],env=env,check=True)
for name,content in p['files'].items():(root/name).write_text(content)
# Only this service account can read its queue token, not an Immich key.
credential=data/'worker-token';credential.write_text(p['token']);credential.chmod(0o600);os.chown(credential,account.pw_uid,account.pw_gid)
root.chmod(0o755)
for directory in [root/'python',root/'venv',root/'upstream']:
 for path in [directory,*directory.rglob('*')]:
  if path.is_symlink():continue
  path.chmod(0o755 if path.is_dir() or os.access(path,os.X_OK) else 0o644)
for name in ['worker.py','native_guard.py']:(root/name).chmod(0o644)
unit=p['unit'].replace('@WORKER@',p['worker']).replace('@CPU@','50%' if p['worker']=='fun-bedbug' else '100%')
pathlib.Path('/etc/systemd/system/waffles-worker.service').write_text(unit)
pathlib.Path('/etc/systemd/system/waffles-worker.timer').write_text(p['timer'])
subprocess.run(['systemctl','daemon-reload'],check=True)
print('Prepared isolated native worker:',p['worker'])
'''

UNIT='''[Unit]
Description=Waffles native pet classification worker
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0
[Service]
Type=simple
User=waffles-worker
Group=waffles-worker
WorkingDirectory=/var/lib/waffles-worker
ExecCondition=/opt/waffles-worker/venv/bin/python /opt/waffles-worker/native_guard.py
ExecStart=/opt/waffles-worker/venv/bin/python -B /opt/waffles-worker/worker.py
Restart=always
RestartSec=60
TimeoutStopSec=30
Environment=QUEUE_URL=https://pets-queue.app.home.panderosystems.com
Environment=WORKER_NAME=@WORKER@
Environment=WORKER_TOKEN_FILE=/var/lib/waffles-worker/worker-token
Environment=UPSTREAM_APP=/opt/waffles-worker/upstream/app
Environment=DATA_DIR=/var/lib/waffles-worker
Environment=HOME=/var/lib/waffles-worker
Environment=NATIVE_CAPACITY_GUARD=true
Environment=MODEL_WORKERS=1
Environment=SCAN_WORKERS=1
Environment=OMP_NUM_THREADS=1
Environment=MKL_NUM_THREADS=1
Environment=OPENBLAS_NUM_THREADS=1
CPUQuota=@CPU@
CPUWeight=10
Nice=10
MemoryHigh=1400M
MemoryMax=1536M
MemorySwapMax=0
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
ReadWritePaths=/var/lib/waffles-worker
[Install]
WantedBy=multi-user.target
'''
TIMER='''[Unit]
Description=Recheck native Waffles worker capacity
[Timer]
OnBootSec=2min
OnUnitInactiveSec=60s
Unit=waffles-worker.service
[Install]
WantedBy=timers.target
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('worker',choices=HOSTS)
    parser.add_argument('action',choices=['prepare','start','status','stop'])
    args=parser.parse_args()
    ssh=['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10','root@'+HOSTS[args.worker]]
    if args.action=='prepare':
        payload={'worker':args.worker,'lock':json.loads((HERE/'native-lock.json').read_text()),'upstream':json.loads((HERE/'upstream-lock.json').read_text()),
                 'requirements':(HERE/'mac-requirements.txt').read_text(),'token':secret('worker-token'),
                 'files':{'worker.py':(HERE/'distributed-worker.py').read_text(),'native_guard.py':(HERE/'native_guard.py').read_text()},'unit':UNIT,'timer':TIMER}
        import shlex
        subprocess.run(ssh+['/usr/bin/python3 -c '+shlex.quote(REMOTE)],input=json.dumps(payload),text=True,check=True)
    else:
        commands={'start':'systemctl enable --now waffles-worker.timer; systemctl start waffles-worker.service',
                  'stop':'systemctl disable --now waffles-worker.timer; systemctl stop waffles-worker.service',
                  'status':'systemctl show waffles-worker.service -p ActiveState -p SubState -p Result -p MemoryCurrent -p CPUUsageNSec; journalctl -u waffles-worker.service -n 6 --no-pager'}
        subprocess.run(ssh+[commands[args.action]],check=True)


if __name__=='__main__':main()
