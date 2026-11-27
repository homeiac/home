#!/usr/bin/env python3
"""Exercise extra-worker 0→1→3→0 tuning while a separate baseline stays alive."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

policy={'slots':0,'mode':'benchmark','cpu_cores':1,'device':'mps'};paths=[];heartbeats=[]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        paths.append(self.path);self.send_response(200);self.end_headers()
        self.wfile.write(json.dumps({'workers':{'mac':policy},'limits':{'mac':3}}).encode())
    def do_POST(self):
        paths.append(self.path);heartbeats.append(json.loads(self.rfile.read(int(self.headers.get('Content-Length',0)))))
        self.send_response(200);self.end_headers();self.wfile.write(b'{}')
def wait(predicate):
    deadline=time.monotonic()+35
    while not predicate():
        if time.monotonic()>deadline:raise AssertionError('Burst process state failed to converge')
        time.sleep(.1)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'token').write_text('test-only')
    shutil.copy2(Path(__file__).with_name('burst-supervisor.py'),root/'burst-supervisor.py')
    (root/'burst_guard.py').write_text('def can_run(starting=False):return True\n')
    (root/'burst-worker.py').write_text('''import os,signal,time
from pathlib import Path
root=Path(__file__).parent;name=os.environ['WAFFLES_INSTANCE'];stopping=False
def stop(*args):
 global stopping
 stopping=True
signal.signal(signal.SIGTERM,stop)
(root/(name+'.started')).touch()
(root/(name+'.device')).write_text(os.environ['BURST_DEVICE'])
ready=Path(os.environ['BURST_READY_DIR']);ready.mkdir(exist_ok=True);(ready/name).touch()
while not stopping:time.sleep(.05)
time.sleep(.25);(root/(name+'.finished')).touch()
''')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    baseline=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])
    supervisor=subprocess.Popen([sys.executable,str(root/'burst-supervisor.py')],env={**os.environ,'QUEUE_URL':f'http://127.0.0.1:{server.server_port}','WORKER_NAME':'mac','WORKER_TOKEN_FILE':str(root/'token'),'BURST_READY_DIR':str(root/'ready')},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        policy['slots']=1;wait(lambda:len(list(root.glob('*.started')))==1)
        policy['slots']=3;wait(lambda:len(list(root.glob('*.started')))==3)
        policy['device']='cpu';wait(lambda:len(list(root.glob('*.started')))==6)
        assert len([p for p in root.glob('*.device') if p.read_text()=='cpu'])==3
        policy['slots']=0;wait(lambda:len(list(root.glob('*.finished')))==6)
        assert baseline.poll() is None and supervisor.poll() is None
        assert set(paths)<={'/api/burst','/api/heartbeat'}
        assert heartbeats and all(h['pool']=='burst' for h in heartbeats)
    finally:
        supervisor.terminate();supervisor.wait(timeout=10);baseline.terminate();baseline.wait();server.shutdown()
print('Extra workers scaled 0→1→3, switched Metal→CPU, drained to 0; baseline stayed alive; no production-control calls')
