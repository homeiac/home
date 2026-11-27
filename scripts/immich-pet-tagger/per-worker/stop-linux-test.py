#!/usr/bin/env python3
"""Stop only a named failed diagnostic in the existing container; retain evidence."""
import argparse,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--label',required=True);a=p.parse_args()
assert a.label.replace('-','').isalnum()
code="""import os,signal,time
from pathlib import Path
label=LABEL
p=Path('/tmp/waffles-per-worker-20261127')/label
pid=int((p/'pid').read_text());args=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\\0')
assert b'/tmp/waffles-per-worker-20261127/worker.py' in args and label.encode() in args
os.kill(pid,signal.SIGTERM);p.rename(p.with_name('failed-'+label+'-'+str(int(time.time()))));print('Stopped failed diagnostic only')
""".replace('LABEL',repr(a.label))
subprocess.run(KUBE+['-n','immich-pilot','exec','deployment/immich-pet-tagger','--','python','-c',code],check=True,timeout=30)
