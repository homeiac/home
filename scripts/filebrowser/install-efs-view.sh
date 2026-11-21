#!/usr/bin/env bash
# Install and test the on-demand reader without changing FileBrowser's live mount.
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
host=${1:-pumped-piglet.maas}
if ! ssh -o BatchMode=yes "root@$host" test -x /usr/local/sbin/filebrowser-ntfsdecrypt; then
    bash "$SCRIPT_DIR/build-ntfsdecrypt-fixed.sh" "$host"
fi
remote_dir=$(ssh -o BatchMode=yes "root@$host" 'mktemp -d /root/efs-view-deploy.XXXXXX')
COPYFILE_DISABLE=1 tar -C "$SCRIPT_DIR" -cf - efs-view.py test_efs_view.py filebrowser-efs.service wait-efs-view-host.sh |
    ssh -o BatchMode=yes "root@$host" "tar -xf - -C '$remote_dir'"
ssh -o BatchMode=yes "root@$host" "bash -s -- '$remote_dir'" <<'REMOTE'
set -euo pipefail
[[ $(hostname -s) == pumped-piglet && $EUID == 0 ]]
[[ $(blockdev --getro /dev/mapper/filebrowser-bitlocker) == 1 ]]
directory=$1
python3 "$directory/test_efs_view.py"
# Refuse to replace a mounted view: restarting it needs an LXC rebind as well.
if mountpoint -q /mnt/filebrowser/BitLocker-Decrypted; then
    echo 'EFS view already mounted; stop and rebind the LXC for an update.' >&2
    exit 1
fi
backup=/root/filebrowser-backups/efs-$(date +%Y%m%dT%H%M%S)
install -d -m 700 "$backup"
cp /etc/pve/lxc/104.conf "$backup/104.conf"
for path in /usr/local/sbin/filebrowser-efs-view.py /etc/systemd/system/filebrowser-efs.service; do
    [[ ! -f $path ]] || cp "$path" "$backup/"
done
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-fusepy
python3 -c 'from fusepy import FUSE, Operations; from cryptography.hazmat.primitives.serialization import pkcs12'
install -m 700 "$directory/efs-view.py" /usr/local/sbin/filebrowser-efs-view.py
install -m 700 "$directory/wait-efs-view-host.sh" /usr/local/sbin/filebrowser-wait-efs-view
install -m 644 "$directory/filebrowser-efs.service" /etc/systemd/system/filebrowser-efs.service
install -d -m 755 /mnt/filebrowser/BitLocker-Decrypted
systemctl daemon-reload
systemctl enable --now filebrowser-efs
for attempt in {1..20}; do
    if mountpoint -q /mnt/filebrowser/BitLocker-Decrypted && test -S /run/filebrowser-efs/unlock.sock; then break; fi
    sleep 1
done
systemctl is-active --quiet filebrowser-efs
findmnt -rn -M /mnt/filebrowser/BitLocker-Decrypted -o OPTIONS | grep -Eq '(^|,)ro(,|$)'
python3 /usr/local/sbin/filebrowser-efs-view.py status
echo 'On-demand mount installed. FileBrowser still uses its original mount until activation.'
REMOTE
