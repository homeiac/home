"""Reuse the homelab Mac experiment's read-only Apple GPU and pressure probes."""
import re
import subprocess
import psutil

def observe(interval=None):
    result={'cpu_percent':psutil.cpu_percent(interval=interval),'swap_bytes':psutil.swap_memory().used,'available_bytes':psutil.virtual_memory().available}
    result['pressure']=int(subprocess.check_output(['sysctl','-n','kern.memorystatus_vm_pressure_level'],text=True))
    raw=subprocess.check_output(['ioreg','-r','-d','1','-c','AGXAccelerator','-w','0'])
    match=re.search(rb'"Device Utilization %"\s*=\s*(\d+)',raw)
    if match:result['gpu_percent']=int(match[1])
    return result

if __name__=='__main__':
    import json
    print(json.dumps(observe(.2)))
