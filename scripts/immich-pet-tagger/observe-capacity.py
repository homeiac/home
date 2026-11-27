#!/usr/bin/env python3
"""Read Mac accelerator/CPU pressure and still-fawn host capacity without changing it."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from distributed import BASE,KUBE

HERE=Path(__file__).resolve().parent
REMOTE='''import json,os,time
from pathlib import Path
mem=dict(l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines())
temps=[]
for name in Path('/sys/class/hwmon').glob('hwmon*/name'):
 if name.read_text().strip() in ('coretemp','k10temp'):
  temps.extend(float(p.read_text())/1000 for p in name.parent.glob('temp*_input'))
cpu=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
print(json.dumps({'available_bytes':int(mem['MemAvailable'].split()[0])*1024,'temperature_c':max(temps) if temps else None,
 'cpu_ticks':sum(cpu[:8]),'idle_ticks':cpu[3]+cpu[4],'load_average':os.getloadavg(),
 'swap_used_bytes':(int(mem['SwapTotal'].split()[0])-int(mem['SwapFree'].split()[0]))*1024,
 'pressure':{n:Path('/proc/pressure/'+n).read_text().strip() for n in ['cpu','memory','io']}}))
'''
def mac():
    python=Path.home()/'Library/Application Support/immich-pet-tagger/venv/bin/python'
    return json.loads(subprocess.check_output([str(python),str(HERE/'mac_observation.py')],text=True,timeout=10))
def host():
    assert '# still-fawn\n' in (HERE.parents[1]/'proxmox/inventory.txt').read_text()
    return json.loads(subprocess.check_output(['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=5','root@still-fawn.maas','python3','-'],input=REMOTE,text=True,timeout=10))
def pods():
    data=json.loads(subprocess.check_output(KUBE+['get','pods','-A','--field-selector','spec.nodeName=k3s-vm-still-fawn','-o','json'],text=True,timeout=10))
    running=[p for p in data['items'] if p['status']['phase'] not in ('Succeeded','Failed')]
    healthy=lambda p:any(c['type']=='Ready' and c['status']=='True' for c in p['status'].get('conditions',[]))
    return {'unready':sum(not healthy(p) for p in running),
            'unready_workloads':[p['metadata']['namespace']+'/'+p['metadata']['name'] for p in running if not healthy(p)],
            'healthy_restarts':{p['metadata']['namespace']+'/'+p['metadata']['name']:sum(c['restartCount'] for c in p['status'].get('containerStatuses',[])) for p in running if healthy(p)},
            'restarts':sum(c['restartCount'] for p in running for c in p['status'].get('containerStatuses',[]))}
def observe():
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending={name:pool.submit(fn) for name,fn in [('mac',mac),('still-fawn',host),('other_pods',pods)]}
        result={name:future.result() for name,future in pending.items()}
    started=time.monotonic()
    with urllib.request.urlopen(BASE+'/healthz',timeout=5) as response:
        result['queue_healthy']=response.status==200 and json.load(response)['ready']
    result['queue_health_seconds']=time.monotonic()-started
    return result
if __name__=='__main__':print(json.dumps(observe(),indent=2))
