#!/usr/bin/env python3
"""Connect the Proxmox photo workers to Bonsai without a LAN inference route."""
import http.server
import json
import subprocess
import threading


GUEST_REQUEST = r'''
import json, subprocess, sys, urllib.error, urllib.request
method, path = sys.argv[1:]
ip = subprocess.check_output(['/usr/local/bin/k3s','kubectl','-n','immich-pilot',
    'get','svc','photo-bonsai','-o','jsonpath={.spec.clusterIP}'], text=True, timeout=8)
data = sys.stdin.buffer.read() if method == 'POST' else None
req = urllib.request.Request(f'http://{ip}:8080{path}', data, {'Content-Type':'application/json'}, method=method)
try:
    with urllib.request.urlopen(req, timeout=185) as response:
        print(json.dumps({'status': response.status, 'body': response.read().decode()}))
except urllib.error.HTTPError as error:
    print(json.dumps({'status': error.code, 'body': error.read().decode()}))
'''
SLOTS = threading.BoundedSemaphore(2)
MAX_REQUEST = 12 * 1024 * 1024


class Handler(http.server.BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_):
        pass

    def reply(self, status, body):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def forward(self, body=b''):
        if not SLOTS.acquire(blocking=False):
            self.reply(503, b'{"error":"Inference bridge busy"}')
            return
        try:
            response = subprocess.run(['qm','guest','exec','105','--timeout','195','--pass-stdin',
                                       '--','python3','-c',GUEST_REQUEST,self.command,self.path],
                                      input=body, capture_output=True, timeout=205, check=True)
            result = json.loads(response.stdout)
            if result.get('exitcode') != 0:
                raise ValueError('Guest inference failed')
            reply = json.loads(result['out-data'])
        except (subprocess.SubprocessError, ValueError, KeyError):
            self.reply(503, b'{"error":"Bonsai unavailable"}')
        else:
            self.reply(reply['status'], reply['body'].encode())
        finally:
            SLOTS.release()

    def do_GET(self):
        if self.path == '/health':
            self.forward()
        else:
            self.reply(404, b'{}')

    def do_POST(self):
        if self.path != '/v1/chat/completions':
            self.reply(404, b'{}')
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_REQUEST:
            self.reply(413, b'{"error":"Invalid request length"}')
            return
        self.forward(self.rfile.read(length))


if __name__ == '__main__':
    http.server.ThreadingHTTPServer(('127.0.0.1', 18082), Handler).serve_forever()
