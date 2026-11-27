#!/usr/bin/env python3
"""Resize inference processes from durable live tuning, draining work on scale-down."""
import json
import logging
import os
from pathlib import Path
import resource
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import uuid


def main() -> None:
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    base=os.environ['QUEUE_URL'].rstrip('/');worker=os.environ['WORKER_NAME']
    token=Path(os.environ['WORKER_TOKEN_FILE']).read_text().strip()
    children=[];stopping=False;target=0;last_heartbeat=0
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
                    logging.info('Inference process exited: code=%s planned_drain=%s',code,item['draining'])
                    try:request('/api/heartbeat',{'worker':worker,'instance':item['instance'],'device':'stopped','ready':False,'draining':item['draining'],'exit_code':code})
                    except Exception:pass
            children=[item for item in children if item['process'].poll() is None]
            try:
                tuning=request('/api/tuning')
                target=int(tuning['workers'][worker]['slots'])
                if not 0<=target<=int(tuning['limits'][worker]):raise ValueError('Invalid tuning')
            except Exception:
                logging.warning('Live tuning unavailable; retaining current process target')
            active=[item for item in children if not item['draining']]
            for item in active[target:]:
                item['draining']=True;item['process'].terminate()
                logging.info('Draining one %s process',worker)
            while len(children)<target:
                if os.environ.get('NATIVE_CAPACITY_GUARD')=='true':
                    from native_guard import can_run
                    if not can_run(starting=True):break
                instance=worker+'-'+uuid.uuid4().hex[:12]
                path=Path(__file__).with_name('distributed-worker.py')
                if not path.exists():path=Path(__file__).with_name('worker.py')
                process=subprocess.Popen([sys.executable,'-B',str(path)],env={**os.environ,'WAFFLES_INSTANCE':instance})
                children.append({'process':process,'draining':False,'instance':instance})
                logging.info('Started %s inference process; desired slots=%d',worker,target)
            if time.monotonic()-last_heartbeat>=15:
                rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                try:request('/api/heartbeat',{'worker':worker,'instance':worker+'-supervisor-'+socket.gethostname(),'role':'supervisor','device':'standby','ready':False,'rss_bytes':rss if sys.platform=='darwin' else rss*1024})
                except Exception:pass
                last_heartbeat=time.monotonic()
            time.sleep(3)
    finally:
        for item in children:
            if item['process'].poll() is None:item['process'].terminate()
        deadline=time.monotonic()+60
        for item in children:
            try:item['process'].wait(timeout=max(0.1,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:item['process'].kill()


if __name__=='__main__':main()
