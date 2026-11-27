#!/usr/bin/env python3
"""Install an isolated native MPS worker using the existing Mac launch-agent pattern."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tarfile
import time
import urllib.request
from distributed import secret

HERE = Path(__file__).resolve().parent
ROOT = Path.home() / 'Library/Application Support/immich-pet-tagger'
LABEL = 'com.panderosystems.waffles-worker'
PLIST = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'start', 'stop', 'status'])
    args = parser.parse_args()
    identity = f'gui/{os.getuid()}/{LABEL}'
    if args.mode == 'status':
        subprocess.run(['launchctl', 'print', identity], check=False)
        return
    if args.mode == 'stop':
        subprocess.run(['launchctl', 'bootout', identity], check=True)
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    if args.mode == 'prepare':
        # Lock the official versioned source archive on the first reviewed install.
        lock = json.loads((HERE / 'upstream-lock.json').read_text())
        archive = ROOT / 'upstream.tar.gz'
        if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != lock['sha256']:
            with urllib.request.urlopen(lock['url'], timeout=60) as response:
                content = response.read()
            if hashlib.sha256(content).hexdigest() != lock['sha256']:
                raise RuntimeError('Upstream archive digest mismatch')
            archive.write_bytes(content)
        with tarfile.open(archive) as bundle:
            bundle.extractall(ROOT / 'upstream', filter='data')
        app = next((ROOT / 'upstream').glob('*/app'))
        (ROOT / 'upstream-app.txt').write_text(str(app))
        subprocess.run(['uv', 'venv', '--python', '3.12', str(ROOT / 'venv')], check=True)
        subprocess.run(['uv', 'pip', 'install', '--python', str(ROOT / 'venv/bin/python'), '-r', str(HERE / 'mac-requirements.txt')], check=True)
        subprocess.run([str(ROOT / 'venv/bin/python'), '-c', 'import torch; assert torch.backends.mps.is_available(); print("MPS available")'], check=True)
        return
    if not (ROOT / 'venv/bin/python').exists():
        raise RuntimeError('Prepare the native runtime first')
    shutil.copy2(HERE / 'distributed-worker.py', ROOT / 'worker.py')
    shutil.copy2(HERE / 'supervisor.py', ROOT / 'supervisor.py')
    (ROOT / 'worker-token').write_text(secret('worker-token'))
    (ROOT / 'worker-token').chmod(0o600)
    data = ROOT / 'data'; data.mkdir(exist_ok=True)
    # Match the existing native-worker pattern: prevent system sleep on AC power
    # only while this dedicated worker is running; battery sleep remains allowed.
    config = {'Label': LABEL, 'ProgramArguments': ['/usr/bin/caffeinate', '-s', str(ROOT / 'venv/bin/python'), '-B', str(ROOT / 'supervisor.py')],
              'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 30,
              'WorkingDirectory': str(data), 'StandardOutPath': str(ROOT / 'worker.log'), 'StandardErrorPath': str(ROOT / 'worker.log'),
              'EnvironmentVariables': {'QUEUE_URL': 'https://pets-queue.app.home.panderosystems.com', 'WORKER_NAME': 'mac',
                  'WORKER_TOKEN_FILE': str(ROOT / 'worker-token'), 'UPSTREAM_APP': (ROOT / 'upstream-app.txt').read_text(),
                  'DATA_DIR': str(data), 'HOME': str(data), 'MODEL_WORKERS': '1', 'SCAN_WORKERS': '1',
                  'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2'}}
    if PLIST.exists():
        shutil.copy2(PLIST, ROOT / 'previous.plist')
        subprocess.run(['launchctl', 'bootout', identity], capture_output=True)
        # bootout can return before launchd has removed the service. An
        # immediate bootstrap then fails with EIO even though the plist is valid.
        deadline = time.monotonic() + 30
        while subprocess.run(['launchctl', 'print', identity], capture_output=True).returncode == 0:
            if time.monotonic() > deadline:
                raise RuntimeError('Previous Waffles agent is still stopping')
            time.sleep(0.25)
    PLIST.write_bytes(plistlib.dumps(config))
    subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(PLIST)], check=True)
    logging.info('Started isolated Waffles Mac worker; existing Mac/RTX workers unchanged')


if __name__ == '__main__':
    main()
