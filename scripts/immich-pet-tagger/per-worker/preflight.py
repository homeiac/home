#!/usr/bin/env python3
"""Read inventory-backed host/VM and runtime state for the matched-photo experiment."""
import json,subprocess,shlex
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from distributed import KUBE
code="import json,os,platform,shutil;from pathlib import Path;print(json.dumps({'cpu':platform.processor(),'cpu_count':os.cpu_count(),'affinity':list(os.sched_getaffinity(0)),'strace':shutil.which('strace'),'files':{p:Path(p).read_text() if Path(p).exists() else None for p in ['/proc/cpuinfo','/proc/meminfo','/proc/pressure/cpu','/proc/pressure/memory','/proc/pressure/io','/sys/fs/cgroup/cpu.max','/sys/fs/cgroup/cpu.stat','/sys/fs/cgroup/memory.events']}}))"
r=subprocess.run(KUBE+['-n','immich-pilot','exec','deployment/immich-pet-tagger','--','python','-c',code],capture_output=True,text=True,timeout=30)
print('POD',r.returncode,r.stdout,r.stderr)
remote="hostname; lscpu; free -m; cat /proc/pressure/cpu /proc/pressure/memory /proc/pressure/io; command -v bpftrace strace; qm status 108"
r=subprocess.run(['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','HostName=192.168.4.17','-o','HostKeyAlias=still-fawn.maas','root@still-fawn.maas',remote],capture_output=True,text=True,timeout=30)
print('HOST',r.returncode,r.stdout,r.stderr)
