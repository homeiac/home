#!/usr/bin/env python3
"""Bootstrap the restricted host installer and SOPS key; Flux installs the worker.

Reuses the encrypted key on reruns. Only root's restricted deployment key and the
fixed installer change here. The worker code, service and settings arrive by Job.
"""
import base64
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SECRET = REPO / 'gitops/clusters/homelab/apps/photo-enrichment/caption-worker/credentials.sops.yaml'
REMOTE = '/opt/knowledge-index/caption-gitops/install.py'


def ssh(host: str, cmd: str, data: bytes | None = None) -> bytes:
    """Use the existing administrator login for this one-time scoped bootstrap."""
    return subprocess.check_output(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                                    '-o', 'ConnectTimeout=10', host, cmd], input=data)


def main() -> None:
    """Create no plaintext credential in the checkout or command output."""
    host = os.environ['CB_HOST']
    with tempfile.TemporaryDirectory(prefix='caption-bootstrap-') as td:
        directory = Path(td)
        key = directory / 'id_ed25519'
        if SECRET.exists():
            secret = yaml.safe_load(subprocess.check_output(['sops', '--decrypt', str(SECRET)]))
            key.write_bytes(base64.b64decode(secret['data']['id_ed25519']))
            key.chmod(0o600)
        else:
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'caption-worker-gitops', '-f', str(key)], check=True)
        public = subprocess.check_output(['ssh-keygen', '-y', '-f', str(key)]).decode().strip()
        host_key = ssh(host, 'cat /etc/ssh/ssh_host_ed25519_key.pub').decode().strip()
        known = 'pumped-piglet.maas ' + host_key + '\n'
        restricted = ('restrict,from="192.168.4.0/24,10.42.0.0/16",command="/usr/bin/python3 '
                      + REMOTE + '" ' + public + ' caption-worker-gitops\n')
        setup = '''set -eu
umask 077
install -d -m 0700 /root/.ssh
install -d -m 0755 /opt/knowledge-index/caption-gitops
if test -f /root/.ssh/authorized_keys; then
  cp -p /root/.ssh/authorized_keys /root/.ssh/authorized_keys.caption-backup-$(date -u +%Y%m%dT%H%M%S)
fi
python3 -c __EDIT__
'''
        edit = ('from pathlib import Path; p=Path("/root/.ssh/authorized_keys"); '
                'old=p.read_text() if p.exists() else ""; '
                'line=' + repr(restricted) + '; '
                'p.write_text(old + ("" if old.endswith("\\n") or not old else "\\n") + line) if line.strip() not in old.splitlines() else None; p.chmod(0o600)')
        ssh(host, setup.replace('__EDIT__', shlex.quote(edit)))
        installer = (HERE / 'install.py').read_bytes()
        ssh(host, 'if test -f ' + REMOTE + '; then cp -p ' + REMOTE + ' ' + REMOTE + '.previous; fi; install -m 0644 /dev/stdin ' + REMOTE, installer)
        if not SECRET.exists():
            obj = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'caption-worker-deploy', 'namespace': 'monitoring'},
                   'type': 'Opaque', 'data': {'id_ed25519': base64.b64encode(key.read_bytes()).decode(),
                                             'known_hosts': base64.b64encode(known.encode()).decode()}}
            plain = directory / 'credentials.yaml'
            plain.write_text(yaml.safe_dump(obj, sort_keys=False))
            plain.chmod(0o600)
            encrypted = subprocess.check_output(['sops', '--encrypt', '--filename-override', str(SECRET), str(plain)], cwd=REPO)
            SECRET.write_bytes(encrypted)
        print('Restricted installer bootstrapped; deployment key is SOPS-encrypted. Worker awaits Flux Job.')


if __name__ == '__main__':
    main()
