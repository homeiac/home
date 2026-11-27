#!/usr/bin/env python3
"""Capture non-secret hardware/runtime provenance for the experiment journal."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
from distributed import KUBE
from experiment import ROOT,record

destination=ROOT/'docs/experiments/waffles/2026-11-26-live-tuning-environment.json'
if destination.exists():raise SystemExit('Environment record already exists; retain it rather than overwriting evidence')
inventory=(ROOT/'proxmox/inventory.txt').read_text()
hosts=['still-fawn','pve','fun-bedbug','chief-horse']
assert all('# '+h+'\n' in inventory for h in hosts)
remote='''import json,os,platform
from pathlib import Path
cpu=Path('/proc/cpuinfo').read_text();mem=Path('/proc/meminfo').read_text()
model=next((l.split(':',1)[1].strip() for l in cpu.splitlines() if l.startswith('model name')),'unknown')
total=int(next(l.split()[1] for l in mem.splitlines() if l.startswith('MemTotal:')))*1024
print(json.dumps(dict(cpu_model=model,logical_cpus=os.cpu_count(),memory_bytes=total,kernel=platform.release())))
'''
def host_info(host):
    result=subprocess.run(['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10','root@'+host+'.maas','python3','-'],input=remote,text=True,capture_output=True)
    if result.returncode:
        return host,{'observation_error':'SSH observation unavailable','exit_code':result.returncode}
    return host,json.loads(result.stdout)
with ThreadPoolExecutor(max_workers=4) as pool:hypervisors=dict(pool.map(host_info,hosts))
keys=['machdep.cpu.brand_string','hw.physicalcpu','hw.logicalcpu','hw.memsize']
mac={k:subprocess.check_output(['sysctl','-n',k],text=True).strip() for k in keys}
mac['os_version']=subprocess.check_output(['sw_vers','-productVersion'],text=True).strip()
python=Path.home()/'Library/Application Support/immich-pet-tagger/venv/bin/python'
code="import importlib.metadata as m,json,platform;print(json.dumps({'python':platform.python_version(),**{n:m.version(n) for n in ['torch','ultralytics','scikit-learn','open_clip_torch','numpy']}}))"
mac['runtime']=json.loads(subprocess.check_output([str(python),'-c',code],text=True))
raw=json.loads(subprocess.check_output(KUBE+['get','nodes','-o','json'],text=True))
nodes={r['metadata']['name']:{'capacity':r['status']['capacity'],'allocatable':r['status']['allocatable'],
        'runtime':{k:r['status']['nodeInfo'][k] for k in ['architecture','kernelVersion','kubeletVersion','containerRuntimeVersion']}}
       for r in raw['items'] if r['metadata']['name'] in ('k3s-vm-pve','k3s-vm-still-fawn')}
data={'observed_at':datetime.now(timezone.utc).isoformat(),'mac':mac,'hypervisors':hypervisors,'kubernetes_nodes':nodes,
      'note':'Read-only provenance observation captured during the experiment. Resource envelopes were fixed by the preregistered protocol; this observation made no configuration changes.'}
destination.write_text(json.dumps(data,indent=2)+'\n')
record('environment_captured',file=destination.name)
print(json.dumps(data,indent=2))
