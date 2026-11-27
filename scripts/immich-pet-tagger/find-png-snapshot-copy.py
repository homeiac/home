#!/usr/bin/env python3
"""Check bounded existing ZFS snapshots for an intact PNG; never restore over originals."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
meta=[m for m in json.loads((a.directory/'original-metadata.json').read_text()) if m['type']=='IMAGE'];assert len(meta)==1
relative=meta[0]['originalPath'].removeprefix('/external/gphotos/');assert relative!=meta[0]['originalPath']
code='''import base64,json,pathlib,struct,subprocess,sys,zlib
root=pathlib.Path(subprocess.check_output(['zfs','get','-H','-o','value','mountpoint','local-3TB-backup/gphotos'],text=True).strip())
r=subprocess.run(['zfs','list','-H','-t','snapshot','-o','name','-s','creation','-r','local-3TB-backup/gphotos'],capture_output=True,text=True,check=True)
names=[n.split('@',1)[1] for n in r.stdout.splitlines() if n.startswith('local-3TB-backup/gphotos@')]
selected=list(dict.fromkeys(names[:2]+names[-6:]));checks=[];candidate=None
for name in selected:
 p=root/'.zfs/snapshot'/name/'library'/sys.argv[1]
 if not p.is_file():checks.append({'snapshot':name,'exists':False});continue
 b=p.read_bytes();position=8;data=[];valid=b[:8]==b'\\x89PNG\\r\\n\\x1a\\n';last=None
 try:
  while position+12<=len(b):
   length=struct.unpack_from('>I',b,position)[0];end=position+12+length
   if end>len(b) or zlib.crc32(b[position+4:end-4])!=struct.unpack_from('>I',b,end-4)[0]:valid=False;break
   last=b[position+4:position+8]
   if last==b'IDAT':data.append(b[position+8:end-4])
   position=end
  valid=valid and position==len(b) and last==b'IEND'
  if valid:zlib.decompress(b''.join(data))
 except (zlib.error,struct.error):valid=False
 checks.append({'snapshot':name,'exists':True,'strict_integrity':valid})
 if valid:candidate=base64.b64encode(b).decode();break
print(json.dumps({'available_snapshots':len(names),'checks':checks,'candidate':candidate}))
'''
# Correct bytes literals in the transported Python source (no shell interpolation).
ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10']
try:socket.getaddrinfo('pumped-piglet.maas',22)
except socket.gaierror:
    inventory=(Path(__file__).parents[2]/'proxmox/inventory.txt').read_text();address=re.search(r'^([0-9.]+)\s+# pumped-piglet\s*$',inventory,re.M).group(1)
    ssh+=['-o','HostName='+address,'-o','HostKeyAlias=pumped-piglet.maas']
command='python3 -c '+shlex.quote(code)+' '+shlex.quote(relative)
print('START: read-only PNG check in up to eight existing snapshots',flush=True)
r=subprocess.run(ssh+['root@pumped-piglet.maas',command],capture_output=True,text=True,timeout=120)
if r.returncode:raise SystemExit(r.stderr[-1000:])
data=json.loads(r.stdout);candidate=data.pop('candidate',None)
if candidate:(a.directory/'snapshot-original.png').write_bytes(base64.b64decode(candidate))
data['recovered']=candidate is not None
(a.directory/'snapshot-check.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data,indent=2))
