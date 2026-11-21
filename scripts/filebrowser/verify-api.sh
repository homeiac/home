#!/usr/bin/env bash
# Verify authentication/listing without exposing login credentials or filenames.
set -euo pipefail
host=${1:-pumped-piglet.maas}
mode=${2:-backend}
[[ $mode == backend || $mode == https ]] || exit 2
ssh -o BatchMode=yes "root@$host" "python3 - '$mode'" <<'PY'
import http.cookiejar
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

base = 'https://files.app.home.panderosystems.com' if sys.argv[1] == 'https' else 'http://pumped-piglet.maas:8088'
login = subprocess.check_output(['pct', 'exec', '104', '--', 'cat', '/root/filebrowser-login.env'], text=True)
password = login.strip().split('=', 1)[1]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
try:
    opener.open(base + '/api/resources?source=SSK&path=/', timeout=15)
    raise SystemExit('FAIL: anonymous file listing was accepted')
except urllib.error.HTTPError as error:
    assert error.code in (401, 403), error.code
    print('Anonymous file listing denied:', error.code)
request = urllib.request.Request(base + '/api/auth/login?username=admin', data=b'',
                                 headers={'X-Password': urllib.parse.quote(password, safe='')}, method='POST')
with opener.open(request, timeout=15) as response:
    assert response.status == 200
    token = response.read().decode().strip().strip('"')
print('Authenticated login: PASS')
request = urllib.request.Request(base + '/api/users?username=self', headers={'X-Auth': token})
with opener.open(request, timeout=15) as response:
    user = json.load(response)
    visible = {link.get('sourceName') for link in user.get('sidebarLinks', []) if link.get('category', '').startswith('source')}
    assert {'SSK', 'RASPBMC', 'BitLocker'} <= visible, 'Missing disk links in sidebar'
    print('All three disk links present in sidebar: PASS')
for source in ('SSK', 'RASPBMC', 'BitLocker'):
    query = urllib.parse.urlencode({'source': source, 'path': '/'})
    request = urllib.request.Request(base + '/api/resources?' + query, headers={'X-Auth': token})
    with opener.open(request, timeout=30) as response:
        data = json.load(response)
        print(source + ': authenticated directory listing PASS (' + str(len(data.get('files', []))) + ' files, ' + str(len(data.get('folders', []))) + ' folders)')
        candidates = [item for item in data.get('files', []) if item.get('size', 0) > 0]
        if candidates:
            item = min(candidates, key=lambda value: value['size'])
            path = item.get('path') or '/' + item['name']
            root = Path('/mnt/filebrowser') / source
            local_path = (root / path.lstrip('/')).resolve()
            assert local_path.is_relative_to(root.resolve())
            query = urllib.parse.urlencode({'source': source, 'file': path})
            request = urllib.request.Request(base + '/api/resources/download?' + query,
                headers={'X-Auth': token, 'Range': 'bytes=0-1023'})
            with opener.open(request, timeout=30) as response, local_path.open('rb') as local_file:
                assert response.status in (200, 206)
                assert response.read(1024) == local_file.read(1024), 'Downloaded bytes differ'
                print(source + ': sample download bytes match the disk')
print('Verified endpoint:', base)
PY
