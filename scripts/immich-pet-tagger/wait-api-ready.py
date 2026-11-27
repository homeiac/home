#!/usr/bin/env python3
"""Bounded read-only Kubernetes readiness wait with visible progress."""
import argparse
import subprocess
import time
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=int,default=120);a=p.parse_args()
print('START: waiting for Kubernetes API readiness; no service changes',flush=True)
end=time.monotonic()+a.seconds
while time.monotonic()<end:
    r=subprocess.run(KUBE+['get','--raw','/readyz','--request-timeout=10s'],capture_output=True,text=True,timeout=15)
    if r.returncode==0 and r.stdout.strip()=='ok':print('READY: Kubernetes API',flush=True);break
    print('WAIT: API not ready; retrying in 10 seconds',flush=True)
    time.sleep(10)
else:raise SystemExit('API did not become ready within the bounded wait')
