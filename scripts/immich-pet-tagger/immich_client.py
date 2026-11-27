#!/usr/bin/env python3
"""Read Immich capabilities using environment or the existing cluster credential.

Never prints API keys. This is a read-only prerequisite check for pet tagging.
"""
import base64
from functools import lru_cache
import json
import os
import subprocess
import urllib.request

BASE = os.environ.get('IMMICH_URL', 'https://immich.app.home.panderosystems.com')


@lru_cache(maxsize=1)
def key() -> str:
    """Read an injected key or the existing sync secret without logging it."""
    if os.environ.get('IMMICH_API_KEY'):
        return os.environ['IMMICH_API_KEY']
    result = subprocess.run(['kubectl', '--kubeconfig', os.path.expanduser('~/kubeconfig'),
        '-n', 'immich-pilot', 'get', 'secret', 'immich-sync', '-o', 'json'],
        capture_output=True, check=True, text=True)
    return base64.b64decode(json.loads(result.stdout)['data']['api-key']).decode()


def api(path: str, method: str = 'GET', body=None):
    """Call the private API without logging request headers."""
    request = urllib.request.Request(BASE + '/api' + path, method=method,
        headers={'x-api-key': key(), 'Content-Type': 'application/json'},
        data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


if __name__ == '__main__':
    for path in ['/server/version', '/users/me', '/api-keys', '/people?withHidden=true']:
        try:
            result = api(path)
            if path == '/users/me':
                result = {k: result.get(k) for k in ['id', 'name', 'isAdmin']}
            if path == '/api-keys':
                result = [{k: item.get(k) for k in ['name', 'permissions']} for item in result]
            if path.startswith('/people'):
                result = {'total': result.get('total'), 'waffles': [p for p in result.get('people', []) if 'waff' in p.get('name', '').lower()]}
            print(json.dumps({'path': path, 'result': result}))
        except Exception as error:
            print(json.dumps({'path': path, 'error': str(error)}))
