#!/usr/bin/env python3
"""Read-only Mac worker/system counters and native stack samples; no tuning."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import time
import psutil
from mac_observation import observe

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);args=parser.parse_args()
os.umask(0o077);args.directory.mkdir(parents=True,exist_ok=True)
root=Path.home()/'Library/Application Support/immich-pet-tagger'
def snapshot():
    processes={}
    for p in psutil.process_iter(['pid','name','cpu_times','memory_info']):
        try:
            info=p.info;times=info['cpu_times'];m=info['memory_info']
            if times is None or m is None:continue
            processes[str(p.pid)]={'name':info['name'],'cpu_seconds':times.user+times.system,'rss':m.rss}
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    return {'at':datetime.now(timezone.utc).isoformat(),'monotonic':time.monotonic(),'host':observe(),
            'cpu_times':psutil.cpu_times()._asdict(),'disk':psutil.disk_io_counters()._asdict(),
            'network':{k:v._asdict() for k,v in psutil.net_io_counters(pernic=True).items()},
            'vm_stat':subprocess.check_output(['vm_stat'],text=True),'processes':processes}
workers={}
for p in psutil.process_iter(['pid','cmdline','name']):
    try:
        argv=p.info['cmdline'] or []
        if p.info['name'].startswith('python'):
            if str(root/'worker.py') in argv:workers['metal']=p.pid
            if str(root/'burst/burst-worker.py') in argv:workers['cpu-'+str(p.pid)]=p.pid
    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
before=snapshot();stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
def sample(item):
    name,pid=item;path=args.directory/f'{stamp}-{name}-{pid}.sample.txt'
    result=subprocess.run(['/usr/bin/sample',str(pid),'10','10','-file',str(path)],capture_output=True,text=True,timeout=30)
    return {'worker':name,'pid':pid,'ok':result.returncode==0,'path':str(path)}
with ThreadPoolExecutor(max_workers=3) as pool:
    samples=list(pool.map(sample,list(workers.items())[:3]))
remaining=20-(time.monotonic()-before['monotonic'])
if remaining>0:time.sleep(remaining)
after=snapshot();elapsed=after['monotonic']-before['monotonic']
deltas=[]
for pid,a in after['processes'].items():
    if pid in before['processes']:
        deltas.append({'pid':int(pid),'name':a['name'],'cpu_percent_of_one_core':round(100*(a['cpu_seconds']-before['processes'][pid]['cpu_seconds'])/elapsed,2),'rss_gib':round(a['rss']/1024**3,2)})
report={'before':before,'after':after,'workers':workers,'samples':samples,'elapsed':elapsed,'top_cpu':sorted(deltas,key=lambda x:x['cpu_percent_of_one_core'],reverse=True)[:12]}
path=args.directory/f'{stamp}-mac-counters.json';path.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'report':str(path),'workers':workers,'samples':samples,'elapsed':elapsed,'host_before':before['host'],'host_after':after['host'],'top_cpu':report['top_cpu']},indent=2))
