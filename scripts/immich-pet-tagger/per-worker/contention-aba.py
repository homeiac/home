#!/usr/bin/env python3
"""Owner-approved bounded pause/resume ABA of competing Mac llama-server processes.

Run with the existing worker venv (psutil). Independent watchdog resumes only
processes this experiment stopped, even if its controller exits unexpectedly.
Exact PID/create-time identity is checked before every signal. No service is
restarted, unloaded or reconfigured. Private state records every transition.
"""
import argparse,json,os,signal,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mac_observation import observe


def identity(process):
 return {'pid':process.pid,'created':process.create_time(),'name':process.name()}


def same(row):
 try:
  process=psutil.Process(row['pid'])
  return process if process.create_time()==row['created'] and process.name()=='llama-server' and process.uids().real==os.getuid() else None
 except psutil.Error:return None


def resume(directory):
 path=directory/'stopped.json'
 rows=json.loads(path.read_text()) if path.exists() else []
 result=[]
 for row in rows:
  process=same(row)
  if process:
   os.kill(process.pid,signal.SIGCONT)
   result.append({**row,'resumed':True})
  else:result.append({**row,'resumed':False,'reason':'original process exited; no replacement signalled'})
 return result


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--watchdog',action='store_true');p.add_argument('--session',default='aba');a=p.parse_args();os.umask(0o077)
 if a.watchdog:
  deadline=time.monotonic()+90
  while time.monotonic()<deadline:
   if (a.directory/'done').exists():return
   time.sleep(.2)
  result=resume(a.directory);(a.directory/'watchdog-resume.json').write_text(json.dumps(result,indent=2)+'\n');return
 root=a.directory.resolve();assert a.session.replace('-','').isalnum()
 study=root/('contention-'+a.session);study.mkdir(exist_ok=False)
 def write(name,data):(study/name).write_text(json.dumps(data,indent=2)+'\n')
 def servers():
  result=[]
  for process in psutil.process_iter(['name']):
   try:
    if process.info['name']=='llama-server' and process.uids().real==os.getuid():
     result.append({**identity(process),'status':process.status(),'cpu_seconds':sum(process.cpu_times()[:2]),'rss':process.memory_info().rss})
   except psutil.Error:pass
  return result
 def snap(name):
  value={'at':datetime.now(timezone.utc).isoformat(),'host':observe(.2),'servers':servers()};write(name+'.json',value);return value
 def trial(phase,backend,hybrid=False):
  label=a.session+'-'+phase+'-'+('hybrid' if hybrid else backend)
  command=[sys.executable,str(Path(__file__).with_name('run.py')),str(root),backend,'--label',label]
  if hybrid:command+=['--cpu-detector']
  print('START',phase,label,flush=True)
  with (study/(label+'.log')).open('w') as log:
   child=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
   deadline=time.monotonic()+(35 if phase=='paused' else 180)
   try:
    while child.poll() is None:
     if time.monotonic()>deadline:raise TimeoutError('Bounded trial deadline')
     if phase=='paused' and time.monotonic()-pause_start>72:raise TimeoutError('Pause budget exceeded')
     time.sleep(.25)
    if child.returncode:raise RuntimeError('Trial failed; see private log '+label)
   except BaseException:
    if child.poll() is None:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=8)
    raise
  print('COMPLETE',label,flush=True)
 def phase(name):
  snap(name+'-start')
  for backend,hybrid in [('mac-mps',False),('mac-cpu',False),('mac-mps',True)]:trial(name,backend,hybrid)
  return snap(name+'-end')
 write('protocol.json',{'at':datetime.now(timezone.utc).isoformat(),'order':['before','paused','resumed'],'variants':['serial Metal','serial CPU','CPU YOLO + Metal CLIP'],'pause_limit_seconds':90,'owner_authorization':'yes, pause them briefly, run the comparison, then resume them','other_services_reconfigured':False})
 initial=servers();assert initial,'No competing llama-server process exists to pause'
 assert all(r['status']!=psutil.STATUS_STOPPED for r in initial),'Pre-stopped process; do not change its state'
 print('START ABA: observed',len(initial),'same-user llama-server processes; preparing baseline',flush=True)
 phase('before')
 targets=servers();assert targets and all(r['status']!=psutil.STATUS_STOPPED for r in targets)
 write('targets.json',targets);write('stopped.json',[])
 watchdog=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),str(study),'--watchdog'],start_new_session=True,stdout=(study/'watchdog.log').open('w'),stderr=subprocess.STDOUT)
 stopped=[];pause_start=time.monotonic();restored=[]
 def interrupted(*_):raise KeyboardInterrupt('Interrupted; restoring paused processes')
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
 try:
  for row in targets:
   process=same(row);assert process,'Target changed before pause'
   # Save identity first so the independent watchdog covers interruption gaps.
   stopped.append(row);write('stopped.json',stopped);os.kill(process.pid,signal.SIGSTOP)
  time.sleep(2)
  assert all(same(row) and same(row).status()==psutil.STATUS_STOPPED for row in stopped)
  write('pause-start.json',{'at':datetime.now(timezone.utc).isoformat(),'count':len(stopped)})
  print('PAUSED',len(stopped),'servers; automatic resume deadline90s',flush=True)
  paused_end=phase('paused')
  assert all(same(row) and same(row).status()==psutil.STATUS_STOPPED for row in stopped),'A paused server changed state'
 finally:
  restored=resume(study);write('resume.json',restored)
  write('pause-duration.json',{'seconds':time.monotonic()-pause_start})
  (study/'done').touch();watchdog.wait(timeout=5)
  print('RESUMED',sum(r['resumed'] for r in restored),'of',len(stopped),'original servers',flush=True)
 assert len(restored)==len(stopped) and all(r['resumed'] for r in restored)
 time.sleep(2)
 assert all(same(row) and same(row).status()!=psutil.STATUS_STOPPED for row in stopped)
 phase('resumed')
 summary={'at':datetime.now(timezone.utc).isoformat(),'state':'complete','stopped':len(stopped),'resumed':sum(r['resumed'] for r in restored),'same_original_processes':all(same(row) is not None for row in stopped),'pause_seconds':json.loads((study/'pause-duration.json').read_text())['seconds'],'watchdog_fired':(study/'watchdog-resume.json').exists(),'server_count_before':len(initial),'server_count_paused':len(paused_end['servers'])}
 write('verified.json',summary);print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
