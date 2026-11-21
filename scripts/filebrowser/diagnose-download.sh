#!/usr/bin/env bash
# Reproduce a selected file download over backend HTTP and public HTTP/1.1+HTTP/2.
# Credentials stay in a temporary root-only curl config; file data is discarded.
set -euo pipefail
ssh -o BatchMode=yes "root@${1:-pumped-piglet.maas}" 'python3 -' <<'PY'
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.parse
import urllib.request

path = '/linuxfour_backup/iso_backup/vlc-record-2020-04-13-15h06m25s-MOVI0033.avi-.avi'
file = Path('/mnt/filebrowser/BitLocker') / path.lstrip('/')
print('File bytes:', file.stat().st_size, flush=True)
base = 'http://pumped-piglet.maas:8088'
login = subprocess.check_output(['pct', 'exec', '104', '--', 'cat', '/root/filebrowser-login.env'], text=True)
password = login.strip().split('=', 1)[1]
cookies = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies))
request = urllib.request.Request(base + '/api/auth/login?username=admin', data=b'',
    headers={'X-Password': urllib.parse.quote(password, safe='')}, method='POST')
with opener.open(request, timeout=15) as response:
    token = response.read().decode().strip().strip('"')
query = urllib.parse.urlencode({'file': path, 'source': 'BitLocker', 'algo': 'tar.gz'})
os.umask(0o077)
with tempfile.TemporaryDirectory(prefix='filebrowser-download-', dir='/run') as tmp:
    config = Path(tmp) / 'curl.conf'
    config.write_text('header = "Cookie: ' + '; '.join(cookie.name + '=' + cookie.value for cookie in cookies) + '"\n')
    for name, endpoint, protocol in [('backend', base, '--http1.1'), ('https-h1', 'https://files.app.home.panderosystems.com', '--http1.1'), ('https-h2', 'https://files.app.home.panderosystems.com', '--http2')]:
        print('\n=== ' + name + ' ===', flush=True)
        headers = Path(tmp) / 'headers'
        result = subprocess.run(['curl', '-sS', '--noproxy', '*', protocol, '--max-time', '30', '-K', str(config),
            '-D', str(headers), '-o', '/dev/null', '-w', 'status=%{http_code} protocol=%{http_version} bytes=%{size_download} seconds=%{time_total}\n', endpoint + '/api/resources/download?' + query], capture_output=True, text=True)
        print(result.stdout, result.stderr, 'exit=', result.returncode, flush=True)
        if headers.exists():
            print('\n'.join(line for line in headers.read_text().splitlines() if not line.lower().startswith(('set-cookie:', 'authorization:'))), flush=True)
PY
