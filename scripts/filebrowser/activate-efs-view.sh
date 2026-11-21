#!/usr/bin/env bash
# Switch FileBrowser's BitLocker source to the tested on-demand view, still ro.
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
host=${1:-pumped-piglet.maas}
remote_dir=$(ssh -o BatchMode=yes "root@$host" 'mktemp -d /root/efs-activate.XXXXXX')
COPYFILE_DISABLE=1 tar -C "$SCRIPT_DIR" -cf - unlock-bitlocker-host.sh wait-efs-view-host.sh filebrowser-efs.service |
    ssh -o BatchMode=yes "root@$host" "tar -xf - -C '$remote_dir'"
ssh -o BatchMode=yes "root@$host" "bash -s -- '$remote_dir'" <<'REMOTE'
set -euo pipefail
[[ $(hostname -s) == pumped-piglet && $EUID == 0 ]]
[[ $(blockdev --getro /dev/mapper/filebrowser-bitlocker) == 1 ]]
python3 /usr/local/sbin/filebrowser-efs-view.py status | python3 -c 'import json,sys; assert json.load(sys.stdin)["unlocked"]'
python3 - <<'PY'
from pathlib import Path
import errno
root=Path('/mnt/filebrowser/BitLocker-Decrypted')
sample=root/'linuxfour_backup/iso_backup/vlc-record-2020-04-13-15h06m25s-MOVI0033.avi-.avi'
with sample.open('rb') as stream:
    head=stream.read(12)
assert head[:4] == b'RIFF' and head[8:12] == b'AVI '
try:
    with (root/'.efs-readonly-probe').open('xb'): pass
except OSError as error:
    assert error.errno == errno.EROFS, error
else:
    (root/'.efs-readonly-probe').unlink()
    raise SystemExit('EFS view unexpectedly writable')
print('Decrypted AVI header valid; writes rejected by kernel.')
PY
backup=/root/filebrowser-backups/efs-activate-$(date +%Y%m%dT%H%M%S)
install -d -m 700 "$backup"
cp /etc/pve/lxc/104.conf "$backup/104.conf"
cp /usr/local/sbin/filebrowser-unlock-bitlocker "$backup/"
cp /etc/systemd/system/filebrowser-efs.service "$backup/"
install -m 700 "$1/wait-efs-view-host.sh" /usr/local/sbin/filebrowser-wait-efs-view
install -m 700 "$1/unlock-bitlocker-host.sh" /usr/local/sbin/filebrowser-unlock-bitlocker
install -m 644 "$1/filebrowser-efs.service" /etc/systemd/system/filebrowser-efs.service
install -d /etc/systemd/system/pve-container@104.service.d
[[ ! -f /etc/systemd/system/pve-container@104.service.d/efs-view.conf ]] || cp /etc/systemd/system/pve-container@104.service.d/efs-view.conf "$backup/"
cat > /etc/systemd/system/pve-container@104.service.d/efs-view.conf <<'UNIT'
[Unit]
Requires=filebrowser-efs.service
After=filebrowser-efs.service
UNIT
systemctl daemon-reload
pct shutdown 104 --timeout 30
pct set 104 -mp2 /mnt/filebrowser/BitLocker-Decrypted,mp=/srv/files/BitLocker,ro=1,backup=0
pct start 104
for attempt in {1..30}; do
    if curl -fsS --max-time 3 http://localhost:8088/ -o /dev/null; then
        echo 'FileBrowser now uses the read-only EFS view under its existing BitLocker link.'
        exit 0
    fi
    sleep 2
done
echo 'FileBrowser failed its readiness check; inspect service status.' >&2
exit 1
REMOTE
