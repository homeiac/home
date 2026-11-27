#!/usr/bin/env python3
"""Snapshot actual diagnostic and co-running host CPU/memory state; no process changes."""
import argparse,json,time,subprocess,sys
from pathlib import Path
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mac_observation import observe
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--label',required=True);a=p.parse_args()
def snap():
 procs={}
 for process in psutil.process_iter(['pid','name','cpu_times','memory_info']):
  try:
   r=process.info;t=r['cpu_times'];m=r['memory_info'];procs[str(r['pid'])]={'name':r['name'],'cpu':t.user+t.system,'rss':m.rss}
  except (psutil.Error,AttributeError):pass
 return {'at':time.time(),'host':observe(),'processes':procs}
before=snap();print('START resource observation',flush=True);time.sleep(10);after=snap();dt=after['at']-before['at'];top=[]
for pid,r in after['processes'].items():
 if pid in before['processes']:top.append({'pid':pid,'name':r['name'],'core_percent':100*(r['cpu']-before['processes'][pid]['cpu'])/dt,'rss':r['rss']})
result={'before':before,'after':after,'top_cpu':sorted(top,key=lambda r:r['core_percent'],reverse=True)[:15]}
(a.directory/(a.label+'-resources.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'before':before['host'],'after':after['host'],'top_cpu':result['top_cpu']},indent=2))
