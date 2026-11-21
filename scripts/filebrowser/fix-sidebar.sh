#!/usr/bin/env bash
# Inspect or repair the admin sidebar; preserves custom links and disk permissions.
# Credentials and a profile backup remain on piglet, outside Git.
set -euo pipefail
host=${1:-pumped-piglet.maas}
mode=${2:-inspect}
[[ $mode == inspect || $mode == fix ]] || exit 2
ssh -o BatchMode=yes "root@$host" "python3 - '$mode'" <<'PY'
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.parse
import urllib.request

base = 'http://pumped-piglet.maas:8088'
login = subprocess.check_output(['pct', 'exec', '104', '--', 'cat', '/root/filebrowser-login.env'], text=True)
password = login.strip().split('=', 1)[1]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
request = urllib.request.Request(base + '/api/auth/login?username=admin', data=b'',
    headers={'X-Password': urllib.parse.quote(password, safe='')}, method='POST')
with opener.open(request, timeout=15) as response:
    token = response.read().decode().strip().strip('"')
headers = {'X-Auth': token}
request = urllib.request.Request(base + '/api/users?username=self', headers=headers)
with opener.open(request, timeout=15) as response:
    user = json.load(response)
expected = ('SSK', 'RASPBMC', 'BitLocker')
print('Available sources:', ', '.join(scope['name'] for scope in user['scopes']))
links = user.get('sidebarLinks', [])
print('Sidebar sources:', ', '.join(link.get('sourceName', '') for link in links if link.get('category', '').startswith('source')))
if sys.argv[1] == 'fix':
    missing = [name for name in expected if not any(link.get('sourceName') == name and link.get('target') == '/' for link in links)]
    if missing:
        os.umask(0o077)
        backup = Path('/root/filebrowser-backups') / ('sidebar-' + time.strftime('%Y%m%dT%H%M%S') + '.json')
        backup.parent.mkdir(mode=0o700, exist_ok=True)
        backup.write_text(json.dumps(user, indent=2) + '\n')
        insert_at = next((i for i, link in enumerate(links) if link.get('category') == 'tool'), len(links))
        links[insert_at:insert_at] = [{'name': name, 'category': 'source-alt', 'target': '/', 'icon': '', 'sourceName': name} for name in missing]
        payload = {'which': ['sidebarLinks'], 'data': {'username': user['username'], 'sidebarLinks': links}}
        patch = urllib.request.Request(base + '/api/users?username=admin',
            data=json.dumps(payload).encode(), method='PATCH',
            headers={**headers, 'Content-Type': 'application/json'})
        with opener.open(patch, timeout=15) as response:
            assert response.status == 204
        print('Saved previous profile:', backup)
    with opener.open(request, timeout=15) as response:
        updated = json.load(response)
    visible = [link.get('sourceName') for link in updated.get('sidebarLinks', []) if link.get('category', '').startswith('source')]
    assert all(name in visible for name in expected), visible
    assert updated['scopes'] == user['scopes'], 'Source permissions changed unexpectedly'
    print('Verified sidebar:', ', '.join(visible))
PY
