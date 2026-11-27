#!/usr/bin/env python3
"""Read-only request probes; compare current urllib behavior with a reused TLS context.

Alternative clients exist only in this diagnostic process. No worker is patched.
Credentials remain in memory; response bodies and photo identifiers are not printed.
"""
import cProfile
from datetime import datetime,timezone
import io
import json
import os
from pathlib import Path
import pstats
import socket
import ssl
import statistics
import time
import urllib.request
from urllib.parse import urlsplit

base=os.environ.get('QUEUE_URL','https://pets-queue.app.home.panderosystems.com').rstrip('/')
token=Path(os.environ.get('WORKER_TOKEN_FILE',str(Path.home()/'Library/Application Support/immich-pet-tagger/worker-token'))).read_text().strip()
def query(context=None):
    req=urllib.request.Request(base+'/api/burst',headers={'Authorization':'Bearer '+token})
    start=time.perf_counter()
    with urllib.request.urlopen(req,timeout=15,context=context) as response:
        size=len(response.read());assert response.status==200
    return {'seconds':time.perf_counter()-start,'bytes':size}
report={'at':datetime.now(timezone.utc).isoformat(),'base':base}
start=time.perf_counter();addresses=socket.getaddrinfo(urlsplit(base).hostname,None);report['dns_seconds']=time.perf_counter()-start
profiler=cProfile.Profile();profiler.enable();rows=[query() for _ in range(8)];profiler.disable()
report['current_urllib']={'median_seconds':statistics.median(r['seconds'] for r in rows),'samples':rows}
stream=io.StringIO();pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(22);report['profile']=stream.getvalue()
if base.startswith('https:'):
    start=time.perf_counter();context=ssl.create_default_context();report['tls_context_creation_seconds']=time.perf_counter()-start
    rows=[query(context) for _ in range(8)]
    report['reused_context_probe']={'median_seconds':statistics.median(r['seconds'] for r in rows),'samples':rows}
print(json.dumps(report,indent=2))
