#!/usr/bin/env python3
"""Trace only the isolated matched-photo still-fawn process via Proxmox guest-exec."""
import subprocess,shlex,json,argparse,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--label',required=True);p.add_argument('--collect',action='store_true');a=p.parse_args()
remote=r'''import subprocess,time,json,os
from pathlib import Path
label=LABEL
pid=None;deadline=time.monotonic()+180
while time.monotonic()<deadline:
 for f in Path('/proc').glob('[0-9]*/cmdline'):
  try:
   args=f.read_bytes().split(b'\0')
   if b'/tmp/waffles-per-worker-20261127/worker.py' in args and label.encode() in args:
    candidate=int(f.parent.name)
    ready=Path(f'/proc/{candidate}/root/tmp/waffles-per-worker-20261127/{label}/rows.jsonl')
    if ready.exists():pid=candidate;break
  except (OSError,ValueError):pass
 if pid:break
 time.sleep(.25)
assert pid,'No measuring worker found'
program=f'BEGIN {{ printf("worker_pid={pid} duration=20s\\n"); }} tracepoint:syscalls:sys_enter_futex,tracepoint:syscalls:sys_enter_read,tracepoint:syscalls:sys_enter_write,tracepoint:syscalls:sys_enter_poll,tracepoint:syscalls:sys_enter_clock_nanosleep /pid == {pid}/ {{ @start[tid] = nsecs; }} tracepoint:syscalls:sys_exit_futex,tracepoint:syscalls:sys_exit_read,tracepoint:syscalls:sys_exit_write,tracepoint:syscalls:sys_exit_poll,tracepoint:syscalls:sys_exit_clock_nanosleep /pid == {pid} && @start[tid]/ {{ @ns[tid,probe] = sum(nsecs-@start[tid]); @calls[tid,probe] = count(); delete(@start[tid]); }} interval:s:20 {{ exit(); }} END {{ clear(@start); }}'
r=subprocess.run(['bpftrace','-e',program],text=True,capture_output=True,timeout=30)
print(json.dumps({'pid':pid,'status':r.returncode,'stdout':r.stdout,'stderr':r.stderr}))
'''.replace('LABEL',repr(a.label))
command=shlex.join(['qm','guest','exec','108','--','python3','-c',remote])
print('START: waiting for measuring worker; bounded 20s eBPF syscall capture',flush=True)
ssh=['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','HostName=192.168.4.17','-o','HostKeyAlias=still-fawn.maas','root@still-fawn.maas']
if a.collect:
 outer=json.loads((a.directory/(a.label+'-ebpf-outer.json')).read_text())
else:
 r=subprocess.run(['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','HostName=192.168.4.17','-o','HostKeyAlias=still-fawn.maas','root@still-fawn.maas',command],capture_output=True,text=True,timeout=230)
 outer=json.loads(r.stdout)
 (a.directory/(a.label+'-ebpf-ssh.stderr')).write_text(r.stderr)
deadline=time.monotonic()+220
while 'pid' in outer and not outer.get('exited'):
 if time.monotonic()>deadline:raise RuntimeError('Guest trace deadline')
 time.sleep(2)
 r=subprocess.run(ssh+['qm guest exec-status 108 '+str(outer['pid'])],capture_output=True,text=True,timeout=20)
 polled=json.loads(r.stdout)
 if polled.get('exited'):outer=polled;break
(a.directory/(a.label+'-ebpf-outer.json')).write_text(json.dumps(outer,indent=2)+'\n')
print('COMPLETE',outer,flush=True)
