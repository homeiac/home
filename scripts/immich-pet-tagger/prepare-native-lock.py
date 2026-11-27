#!/usr/bin/env python3
"""Verify an official versioned uv archive and save its public checksum for native IaC."""
import hashlib
import json
from pathlib import Path
import urllib.request

version='0.12.19'
url=f'https://github.com/astral-sh/uv/releases/download/{version}/uv-x86_64-unknown-linux-gnu.tar.gz'
with urllib.request.urlopen(url+'.sha256',timeout=60) as response:
    digest=response.read().decode().split()[0]
with urllib.request.urlopen(url,timeout=60) as response:
    archive=response.read()
assert hashlib.sha256(archive).hexdigest()==digest
Path(__file__).with_name('native-lock.json').write_text(json.dumps({'uv_version':version,'uv_url':url,'uv_sha256':digest,'python':'3.12.14'},indent=2)+'\n')
print('Verified official uv archive and recorded pinned checksum')
