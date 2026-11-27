#!/usr/bin/env python3
"""Exercise live scale-up/down using real child processes and a local test API."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

tuning={'slots':1}
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'workers':{'mac':tuning},'limits':{'mac':4}}).encode())
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length',0)));self.send_response(200);self.end_headers();self.wfile.write(b'{}')

def wait(predicate):
    deadline=time.monotonic()+15
    while not predicate():
        if time.monotonic()>deadline:raise AssertionError('Process state did not converge')
        time.sleep(.1)

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'token').write_text('test-only')
    shutil.copy2(Path(__file__).with_name('supervisor.py'),root/'supervisor.py')
    (root/'worker.py').write_text('''import os,signal,time
from pathlib import Path
root=Path(__file__).parent;name=os.environ['WAFFLES_INSTANCE'];stopping=False
def stop(*args):
 global stopping
 stopping=True
signal.signal(signal.SIGTERM,stop)
(root/(name+'.started')).touch()
while not stopping:time.sleep(.05)
time.sleep(.25)
(root/(name+'.finished')).touch()
''')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    process=subprocess.Popen([sys.executable,str(root/'supervisor.py')],env={**os.environ,'QUEUE_URL':f'http://127.0.0.1:{server.server_port}','WORKER_NAME':'mac','WORKER_TOKEN_FILE':str(root/'token')},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        wait(lambda:len(list(root.glob('*.started')))==1)
        tuning['slots']=2;wait(lambda:len(list(root.glob('*.started')))==2)
        tuning['slots']=0;wait(lambda:len(list(root.glob('*.finished')))==2)
        assert process.poll() is None,'Live tuning must not restart the supervisor'
    finally:
        process.terminate();process.wait(timeout=10);server.shutdown()
print('Live supervisor 1→2→0 scaling and graceful drain passed without supervisor restart')
