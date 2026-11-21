"""Bootstrap the Git-managed still-fawn runner and its restricted link to Piglet."""

import argparse
import ipaddress
import re
import shlex
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = '/opt/knowledge-index/luna-backfill'
STATE = '/var/lib/ki-luna'
TAG = 'rust-v0.169.0'
ASSET = 'codex-package-x86_64-unknown-linux-musl.tar.gz'
SHA256 = '3b8ed091149cc63a59046b9f094bcfa21cdb4dda15ede441ce369bcee4a71ba0'


def ssh(host, command, data=None):
    return subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
         '-o', 'ConnectTimeout=8', f'root@{host}', command],
        input=data, stdout=subprocess.PIPE, check=True,
    ).stdout


def install(host, destination, data, mode='0644', owner='root'):
    command = (
        f'set -eu; umask 077; p=$(mktemp {shlex.quote(destination)}.XXXXXX); '
        'trap \'rm -f "$p"\' EXIT; cat > "$p"; '
        f'chown {owner}:{owner} "$p"; chmod {mode} "$p"; mv "$p" {shlex.quote(destination)}'
    )
    ssh(host, command, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', required=True, type=ipaddress.IPv4Address)
    parser.add_argument('--piglet', required=True, type=ipaddress.IPv4Address)
    args = parser.parse_args()
    runner, piglet = args.runner, args.piglet

    version = ssh(runner, f"""set -eu
test "$(hostname -s)" = still-fawn
test "$(uname -m)" = x86_64
getent passwd ki-luna >/dev/null ||
    useradd --system --user-group --home-dir {STATE} --shell /usr/sbin/nologin ki-luna
install -d -m 0700 -o ki-luna -g ki-luna {STATE}
install -d -m 0755 {BASE}/bin
if ! test -x {BASE}/bin/codex || ! {BASE}/bin/codex --version | grep -Fx 'codex-cli 0.169.0' >/dev/null; then
    d=$(mktemp -d)
    trap 'rm -rf "$d"' EXIT
    curl --fail --silent --show-error --location --retry 2 --max-time 180 \
        https://github.com/openai/codex/releases/download/{TAG}/{ASSET} -o "$d/package"
    echo '{SHA256}  '"$d/package" | sha256sum -c >&2
    tar -xzf "$d/package" -C "$d"
    binary=$(find "$d" -type f -name codex -print -quit)
    test -n "$binary"
    cp -R "$(dirname "$binary")"/. {BASE}/bin/
fi
if ! test -f {STATE}/piglet_ed25519; then
    runuser -u ki-luna -- ssh-keygen -q -t ed25519 -N '' -C knowledge-index-luna-still-fawn -f {STATE}/piglet_ed25519
fi
{BASE}/bin/codex --version
""")
    print(version.decode().strip(), flush=True)
    key = ssh(runner, f'ssh-keygen -y -f {STATE}/piglet_ed25519').decode().strip()
    if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+ knowledge-index-luna-still-fawn', key):
        raise ValueError('Unexpected runner public key format')
    host_key = ssh(piglet, 'cat /etc/ssh/ssh_host_ed25519_key.pub').decode().strip()
    if not host_key.startswith('ssh-ed25519 '):
        raise ValueError('Unexpected Piglet host key format')

    ssh(piglet, f"""set -eu
test "$(hostname -s)" = pumped-piglet
getent passwd ki-luna-bridge >/dev/null ||
    useradd --system --user-group --home-dir /var/lib/ki-luna-bridge --shell /bin/sh ki-luna-bridge
install -d -m 0700 -o ki-luna-bridge -g ki-luna-bridge /var/lib/ki-luna-bridge /var/lib/ki-luna-bridge/.ssh
test -f {BASE}/host.py
""")
    install(piglet, f'{BASE}/bridge', (HERE/'bridge').read_bytes(), '0750')
    sudo_rule = f'ki-luna-bridge ALL=(root) NOPASSWD: {BASE}/bridge ""\n'.encode()
    ssh(piglet, 'visudo -cf -', sudo_rule)
    install(piglet, '/etc/sudoers.d/ki-luna-bridge', sudo_rule, '0440')
    authorized = f'from="{runner}",restrict,command="/usr/bin/sudo -n {BASE}/bridge" {key}\n'
    install(piglet, '/var/lib/ki-luna-bridge/.ssh/authorized_keys', authorized.encode(), '0600', 'ki-luna-bridge')
    install(runner, f'{STATE}/piglet_known_hosts', f'{piglet} {host_key}\n'.encode(), '0600', 'ki-luna')
    install(runner, '/etc/knowledge-index-luna.conf', f'CB_HOST=ki-luna-bridge@{piglet}\n'.encode())
    install(runner, f'{BASE}/worker.py', (HERE/'worker.py').read_bytes())
    for name in ('knowledge-index-luna.service','knowledge-index-luna.timer'):
        install(runner, f'/etc/systemd/system/{name}', (HERE/name).read_bytes())
    cmd = (f'runuser -u ki-luna -- ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes '
           f'-o UserKnownHostsFile={STATE}/piglet_known_hosts -o IdentitiesOnly=yes '
           f'-i {STATE}/piglet_ed25519 ki-luna-bridge@{piglet}')
    result = ssh(runner, cmd, b'{"op":"status"}')
    print('Restricted ledger connection:', result.decode().strip())
    ssh(runner, 'systemd-analyze verify knowledge-index-luna.service knowledge-index-luna.timer && '
        'systemctl daemon-reload && systemctl enable --now knowledge-index-luna.timer')


if __name__ == '__main__':
    main()
