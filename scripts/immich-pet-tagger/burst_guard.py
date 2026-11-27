"""Protect the permanent baseline by refusing extra workers under memory pressure."""
from pathlib import Path
import subprocess
import sys
import time

warning_since=None

def can_run(starting=False):
    global warning_since
    if sys.platform=='darwin':
        try:level=int(subprocess.check_output(['sysctl','-n','kern.memorystatus_vm_pressure_level'],text=True))
        except Exception:return False
        if level==1:warning_since=None;return True
        if starting or level>=4:return False
        if warning_since is None:warning_since=time.monotonic()
        return time.monotonic()-warning_since<6
    try:
        memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        if int(memory['MemAvailable'].split()[0])<(1800 if starting else 512)*1024:return False
        limit=Path('/sys/fs/cgroup/memory.max').read_text().strip()
        current=int(Path('/sys/fs/cgroup/memory.current').read_text())
        return limit=='max' or int(limit)-current>(1500 if starting else 128)*1024**2
    except Exception:return False
