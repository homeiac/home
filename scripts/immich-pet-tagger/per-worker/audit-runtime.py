#!/usr/bin/env python3
"""Audit source/package/hardware identities on both existing runtimes without models."""
import argparse,json,subprocess,sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from distributed import KUBE
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
code='''import importlib.metadata,hashlib,json,sys,platform
from pathlib import Path
app=Path(sys.argv[1]);print(json.dumps({'python':platform.python_version(),'machine':platform.machine(),'versions':{n:importlib.metadata.version(n) for n in ['torch','torchvision','open_clip_torch','ultralytics','scikit-learn','Pillow']},'source_hashes':{n:hashlib.sha256((app/(n+'.py')).read_bytes()).hexdigest() for n in ['embedder','detector','classifier','device']}}))'''
runtime=Path.home()/'Library/Application Support/immich-pet-tagger'
mac=json.loads(subprocess.check_output([str(runtime/'venv/bin/python'),'-c',code,(runtime/'upstream-app.txt').read_text().strip()],text=True,timeout=30))
linux=json.loads(subprocess.check_output(KUBE+['-n','immich-pilot','exec','deployment/immich-pet-tagger','--','python','-c',code,'/app'],text=True,timeout=30))
hardware=subprocess.check_output(['system_profiler','SPHardwareDataType'],text=True,timeout=20)
# Keep serial number and hardware UUID out of even aggregate output.
hardware='\n'.join(line.strip() for line in hardware.splitlines() if any(field in line for field in ['Model Name:','Chip:','Total Number of Cores:','Memory:']))
result={'mac':mac,'still_fawn':linux,'same_source':mac['source_hashes']==linux['source_hashes'],'mac_hardware':hardware}
(a.directory/'runtime-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
