#!/usr/bin/env python3
"""Back up and reload the installed supervisor after active Mac requests finish."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

from runtime import ROOT
from supervisor import keep_awake


def main():
    label = f'gui/{os.getuid()}/com.panderosystems.knowledge-index-bonsai'
    target = ROOT / 'supervisor.py'
    source = Path(__file__).with_name('supervisor.py')
    # Bridge the old supervisor's lifetime until the new one owns its assertion.
    pid = int(subprocess.check_output(['lsof', '-tiTCP:19476', '-sTCP:LISTEN'], text=True).strip())
    bridge = keep_awake(type('Model', (), {'pid': pid})())
    request = urllib.request.Request('http://127.0.0.1:19476/slots', headers={
        'Authorization': 'Bearer ' + (ROOT / 'server.key').read_text().strip()})
    try:
        deadline = time.monotonic() + 120
        while True:
            with urllib.request.urlopen(request, timeout=5) as response:
                slots = json.load(response)
            if not any(slot['is_processing'] for slot in slots):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('No idle interval; installed supervisor was not changed')
            time.sleep(0.5)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        target.with_name('supervisor.py.backup-' + stamp).write_bytes(target.read_bytes())
        temporary = target.with_suffix('.new')
        temporary.write_bytes(source.read_bytes())
        temporary.replace(target)
        subprocess.run(['launchctl', 'kill', 'SIGTERM', label], check=True)
        print('Installed supervisor; launchd will restart it automatically.')
    except BaseException:
        bridge.terminate()
        raise
    # caffeinate exits with the old model PID, including after this updater exits.


if __name__ == '__main__':
    main()
