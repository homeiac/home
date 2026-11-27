#!/usr/bin/env python3
"""Manage only extra workers; baseline supervisors and processes stay untouched."""
import json
import logging
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from burst_guard import can_run

def main():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    base=os.environ['QUEUE_URL'].rstrip('/');worker=os.environ['WORKER_NAME']
    token=Path(os.environ['WORKER_TOKEN_FILE']).read_text().strip()
    ready=Path(os.environ.get('BURST_READY_DIR','/tmp/waffles-burst-ready'));ready.mkdir(parents=True,exist_ok=True)
    children=[];stopping=False;target=0;last_heartbeat=0;cores=0;device='mps' if sys.platform=='darwin' else 'cpu';threads=2
    allowed=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else []
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    def request(path,body=None):
        req=urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},data=None if body is None else json.dumps(body).encode())
        with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)
    try:
        while not stopping:
            for item in children:
                code=item['process'].poll()
                if code is not None:
                    (ready/item['instance']).unlink(missing_ok=True)
                    logging.info('Burst process exited: code=%s drain=%s',code,item['draining'])
                    try:request('/api/heartbeat',{'worker':worker,'pool':'burst','instance':item['instance'],'device':'stopped','ready':False,'draining':item['draining'],'exit_code':code})
                    except Exception:pass
            children=[item for item in children if item['process'].poll() is None]
            try:
                tuning=request('/api/burst');value=int(tuning['workers'][worker]['slots'])
                if not 0<=value<=int(tuning['limits'][worker]):raise ValueError('Invalid burst target')
                requested_cores=int(tuning['workers'][worker].get('cpu_cores',0))
                if allowed and not 1<=requested_cores<=len(allowed):raise ValueError('Invalid CPU affinity count')
                requested_device=tuning['workers'][worker].get('device',device)
                if requested_device not in ('cpu','mps'):raise ValueError('Invalid compute device')
                requested_threads=int(tuning['workers'][worker].get('cpu_threads',2))
                if not 1<=requested_threads<=16:raise ValueError('Invalid thread count')
                target=value;cores=requested_cores;device=requested_device;threads=requested_threads
            except Exception:logging.warning('Burst policy unavailable; retaining target')
            for item in children:
                if (item['device']!=device or item['threads']!=threads) and not item['draining']:
                    item['draining']=True;item['process'].terminate()
            if allowed and cores:
                for item in children:
                    for task in Path('/proc/'+str(item['process'].pid)+'/task').glob('*'):
                        try:os.sched_setaffinity(int(task.name),allowed[:cores])
                        except ProcessLookupError:pass
            active=[item for item in children if not item['draining']]
            for item in active[target:]:
                item['draining']=True;item['process'].terminate()
            # Load one model process at a time. A large target must not bypass
            # pressure guards by launching all allocations before they appear.
            if len(children)<target and all((ready/i['instance']).exists() for i in children) and can_run(starting=True):
                instance=worker+'-burst-'+uuid.uuid4().hex[:12]
                process=subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('burst-worker.py'))],env={**os.environ,'WAFFLES_INSTANCE':instance,'BURST_READY_DIR':str(ready),'BURST_CPU_CORES':str(cores),'BURST_DEVICE':device,'OMP_NUM_THREADS':str(threads),'MKL_NUM_THREADS':str(threads),'OPENBLAS_NUM_THREADS':str(threads)},preexec_fn=lambda:os.nice(10))
                children.append({'process':process,'draining':False,'instance':instance,'device':device,'threads':threads})
                logging.info('Started extra %s process; target=%d',worker,target)
            if time.monotonic()-last_heartbeat>=15:
                body={'worker':worker,'pool':'burst','instance':worker+'-burst-supervisor-'+socket.gethostname(),'role':'supervisor','device':'standby','ready':False}
                if sys.platform=='darwin':
                    try:
                        from mac_observation import observe
                        body['host_observation']=observe()
                    except Exception:logging.warning('Mac host observation unavailable')
                try:request('/api/heartbeat',body)
                except Exception:pass
                last_heartbeat=time.monotonic()
            time.sleep(3)
    finally:
        for item in children:
            if item['process'].poll() is None:item['process'].terminate()
        deadline=time.monotonic()+60
        for item in children:
            try:item['process'].wait(timeout=max(.1,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:item['process'].kill()

if __name__=='__main__':main()
