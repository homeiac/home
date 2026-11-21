#!/usr/bin/env bash
# Verify full authenticated HTTPS download and seeking without storing a copy.
set -euo pipefail
ssh -o BatchMode=yes "root@${1:-pumped-piglet.maas}" 'python3 -' <<'PY'
import errno
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

base='https://files.app.home.panderosystems.com'
relative='/linuxfour_backup/iso_backup/vlc-record-2020-04-13-15h06m25s-MOVI0033.avi-.avi'
original=Path('/mnt/filebrowser/BitLocker'+relative)
view=Path('/mnt/filebrowser/BitLocker-Decrypted'+relative)
size=original.stat().st_size
assert subprocess.check_output(['blockdev','--getro','/dev/mapper/filebrowser-bitlocker'],text=True).strip()=='1'
assert int.from_bytes(os.getxattr(original,'system.ntfs_attrib'),'little') & 0x4000
try:
    with original.open('rb') as stream: stream.read(1)
except PermissionError: pass
else: raise AssertionError('Expected original EFS content to stay encrypted')
local_hash=hashlib.sha256()
with view.open('rb') as stream:
    while chunk:=stream.read(1024*1024): local_hash.update(chunk)
print('Original retains EFS encryption; read-only mapping confirmed.')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
query=urllib.parse.urlencode({'file':relative,'source':'BitLocker','algo':'tar.gz'})
url=base+'/api/resources/download?'+query
try:
    opener.open(url,timeout=15)
except urllib.error.HTTPError as error: assert error.code in (401,403)
else: raise AssertionError('Unauthenticated download unexpectedly allowed')
login=subprocess.check_output(['pct','exec','104','--','cat','/root/filebrowser-login.env'],text=True)
password=login.strip().split('=',1)[1]
request=urllib.request.Request(base+'/api/auth/login?username=admin',data=b'',
    headers={'X-Password':urllib.parse.quote(password,safe='')},method='POST')
with opener.open(request,timeout=15) as response: assert response.status==200
password=login=None
count=0
digest=hashlib.sha256()
with opener.open(url,timeout=90) as response:
    assert response.status==200
    while chunk:=response.read(1024*1024):
        digest.update(chunk); count+=len(chunk)
assert count==size,(count,size)
assert digest.digest()==local_hash.digest(),'HTTPS download differs from the decrypted filesystem view'
print('Complete authenticated HTTPS download matches decrypted view:',count,'bytes')
start=min(10000000,size-1024)
request=urllib.request.Request(url,headers={'Range':f'bytes={start}-{start+1023}'})
with opener.open(request,timeout=90) as response,view.open('rb') as stream:
    assert response.status==206
    stream.seek(start)
    assert response.read()==stream.read(1024)
print('HTTP range download and forward seek: PASS')
with view.open('rb') as stream:
    stream.seek(start); stream.read(1024); stream.seek(0)
    head=stream.read(12)
    assert head[:4]==b'RIFF' and head[8:12]==b'AVI '
print('Backward seek: PASS')
subprocess.run(['pct','exec','104','--','python3','-c',
    "import os,errno; p='/srv/files/BitLocker/.efs-readonly-probe'; "
    "\ntry: fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)"
    "\nexcept OSError as e: assert e.errno==errno.EROFS; print('Container write rejected: EROFS')"
    "\nelse: os.close(fd); os.unlink(p); raise AssertionError('Writable source')"],check=True)
print('EFS download verification complete; no decrypted copy saved.')
PY
