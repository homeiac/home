#!/usr/bin/env python3
"""Attach bounded eBPF syscall timing to the actual still-fawn baseline worker.

Uses Proxmox guest-exec as root; never SSHes into a K3s VM. No model/test jobs.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);args=p.parse_args()
assert '# still-fawn\n' in (HERE.parents[1]/'proxmox/inventory.txt').read_text()
os.umask(0o077);args.directory.mkdir(parents=True,exist_ok=True)
remote=r'''import json,os,subprocess,time
from pathlib import Path
workers=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  argv=p.read_bytes().split(b'\x00')
  if b'/code/distributed-worker.py' in argv:workers.append(int(p.parent.name))
 except (OSError,ValueError):pass
assert len(workers)==1,workers
pid=workers[0]
def snapshot():
 result={'at':time.time(),'process':Path(f'/proc/{pid}/stat').read_text(),'io':Path(f'/proc/{pid}/io').read_text(),'status':Path(f'/proc/{pid}/status').read_text(),'threads':{}}
 for task in Path(f'/proc/{pid}/task').iterdir():
  try:result['threads'][task.name]={'stat':(task/'stat').read_text(),'wchan':(task/'wchan').read_text()}
  except OSError:pass
 return result
before=snapshot()
groups=['*read*','*write*','*recv*','*send*','*poll*','*futex*','*nanosleep*','connect']
entries=','.join('tracepoint:syscalls:sys_enter_'+g for g in groups)
returns=','.join('tracepoint:syscalls:sys_exit_'+g for g in groups)
program=f'BEGIN {{ printf("main_thread_pid={pid} duration=20s\\n"); }} {entries} /pid == {pid} && tid == {pid}/ {{ @start[tid] = nsecs; }} {returns} /pid == {pid} && tid == {pid} && @start[tid]/ {{ @nanoseconds[probe] = sum(nsecs-@start[tid]); @calls[probe] = count(); delete(@start[tid]); }} interval:s:20 {{ exit(); }} END {{ clear(@start); }}'
try:
 result=subprocess.run(['bpftrace','-e',program],text=True,capture_output=True,timeout=30)
 output={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
except subprocess.TimeoutExpired as error:output={'error':'timeout'}
after=snapshot()
print(json.dumps({'pid':pid,'clock_ticks':os.sysconf('SC_CLK_TCK'),'before':before,'after':after,'trace':output}))
'''
command=shlex.join(['qm','guest','exec','108','--','python3','-c',remote])
raw=subprocess.check_output(['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10','root@still-fawn.maas',command],text=True,timeout=50)
outer=json.loads(raw)
if outer.get('exitcode')!=0:raise RuntimeError(outer.get('err-data','Guest trace did not finish'))
report=json.loads(outer['out-data']);path=args.directory/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-still-fawn-live.json')
path.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'path':str(path),'pid':report['pid'],'trace':report['trace']},indent=2))
