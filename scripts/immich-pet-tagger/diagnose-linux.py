#!/usr/bin/env python3
"""Read Linux resource/error/pressure counters twice, without modifying workloads."""
from datetime import datetime,timezone
import json
from pathlib import Path
import time

def snapshot():
    paths=['/proc/stat','/proc/meminfo','/proc/vmstat','/proc/diskstats','/proc/net/dev','/proc/net/snmp',
           '/proc/pressure/cpu','/proc/pressure/memory','/proc/pressure/io',
           '/sys/fs/cgroup/cpu.stat','/sys/fs/cgroup/cpu.max','/sys/fs/cgroup/cpu.pressure',
           '/sys/fs/cgroup/memory.current','/sys/fs/cgroup/memory.max','/sys/fs/cgroup/memory.events','/sys/fs/cgroup/memory.pressure']
    result={'at':datetime.now(timezone.utc).isoformat(),'monotonic':time.monotonic()}
    for name in paths:
        try:result[name]=Path(name).read_text()
        except (FileNotFoundError,PermissionError):result[name]=None
    return result
before=snapshot();time.sleep(20);after=snapshot()
print(json.dumps({'before':before,'after':after},indent=2))
