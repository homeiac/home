#!/usr/bin/env python3
"""Read preserved ingestion versions on the inventoried backup host for damaged media."""
import argparse
import base64
import json
import os
from pathlib import Path
import shlex
import socket
import re
import subprocess
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
parents=json.loads((a.directory/'motion-parents.json').read_text());meta=json.loads((a.directory/'original-metadata.json').read_text())
names=[m['originalFileName'] for m in meta if m['type']=='IMAGE']+[m['name'] for m in parents]
code='''import base64,json,os,pathlib,subprocess,sys
names=set(json.loads(base64.b64decode(sys.argv[1])))
root=pathlib.Path(subprocess.check_output(['zfs','get','-H','-o','value','mountpoint','local-3TB-backup/gphotos'],text=True).strip())
versions=root/'.versions';out=[];count=0
if versions.is_dir():
 for directory,_,files in os.walk(versions):
  for name in files:
   count+=1
   if name in names:
    path=pathlib.Path(directory)/name;out.append({'path':str(path),'name':name,'bytes':path.stat().st_size})
print(json.dumps({'version_files_checked':count,'candidates':out}))
'''
print('START: checking preserved ingestion versions read-only on pumped-piglet',flush=True)
command='python3 -c '+shlex.quote(code)+' '+shlex.quote(base64.b64encode(json.dumps(names).encode()).decode())
ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10']
try:socket.getaddrinfo('pumped-piglet.maas',22)
except socket.gaierror:
    inventory=(Path(__file__).parents[2]/'proxmox/inventory.txt').read_text()
    address=re.search(r'^([0-9.]+)\s+# pumped-piglet\s*$',inventory,re.M).group(1)
    ssh+=['-o','HostName='+address,'-o','HostKeyAlias=pumped-piglet.maas']
    print('DNS unavailable; using the checked inventory address with hostname key verification',flush=True)
r=subprocess.run(ssh+['root@pumped-piglet.maas',command],capture_output=True,text=True,timeout=180)
if r.returncode:raise SystemExit(r.stderr[-1000:])
data=json.loads(r.stdout);(a.directory/'version-copies.json').write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps({'version_files_checked':data['version_files_checked'],'candidate_count':len(data['candidates'])}))
