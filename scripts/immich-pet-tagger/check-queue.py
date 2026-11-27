#!/usr/bin/env python3
"""Read-only live checks of queue authentication and worker access boundaries."""
import json
import urllib.error
import urllib.request
from distributed import BASE, secret, request


def status(path, token=None, body=None):
    req=urllib.request.Request(BASE+path,headers={} if token is None else {'Authorization':'Bearer '+token},
                               data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req,timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


assert status('/healthz')==200
assert status('/api/config')==401
worker=secret('worker-token')
assert status('/api/config',worker)==200
assert status('/admin/status',worker)==403
assert status('/api/tuning',worker)==200
assert status('/api/burst',worker)==200
assert status('/admin/tuning',worker,{'worker':'mac','slots':4})==403
assert status('/admin/tuning',secret('admin-token'),{'worker':'mac','slots':5})==400
assert status('/admin/tuning',secret('admin-token'),{'worker':'mac','slots':0})==400
assert status('/admin/burst',worker,{'worker':'mac','slots':1,'mode':'production'})==403
assert status('/admin/burst',secret('admin-token'),{'worker':'mac','slots':16,'mode':'production'})==400
assert status('/admin/burst',secret('admin-token'),{'worker':'mac','slots':1,'mode':'production','cpu_threads':17})==400
assert status('/immich/api/assets/00000000-0000-4000-8000-000000000000/thumbnail',worker)==404
assert status('/immich/api/users/me',worker)==404
data=request('/admin/status')
assert {'mac','pve','still-fawn'} <= {w['name'] for w in data['workers']} <= {'mac','pve','still-fawn','fun-bedbug','chief-horse'}
print('Queue health, authentication, tuning bounds, admin isolation and thumbnail allowlist checks passed')
