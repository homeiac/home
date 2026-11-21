#!/usr/bin/env bash
# Update the FUSE daemon, refreshing the LXC bind if it already uses the view.
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
host=${1:-pumped-piglet.maas}
remote_dir=$(ssh -o BatchMode=yes "root@$host" 'mktemp -d /root/efs-view-update.XXXXXX')
COPYFILE_DISABLE=1 tar -C "$SCRIPT_DIR" -cf - efs-view.py test_efs_view.py wait-efs-view-host.sh filebrowser-efs.service |
    ssh -o BatchMode=yes "root@$host" "tar -xf - -C '$remote_dir'"
ssh -o BatchMode=yes "root@$host" "bash -s -- '$remote_dir'" <<'REMOTE'
set -euo pipefail
[[ $(hostname -s) == pumped-piglet && $EUID == 0 ]]
test -x /usr/local/sbin/filebrowser-ntfsdecrypt
python3 "$1/test_efs_view.py"
backup=/root/filebrowser-backups/efs-update-$(date +%Y%m%dT%H%M%S)
install -d -m 700 "$backup"
cp /usr/local/sbin/filebrowser-efs-view.py /etc/systemd/system/filebrowser-efs.service "$backup/"
cp /etc/pve/lxc/104.conf "$backup/104.conf"
restart_ct=0
if pct config 104 | grep -q '^mp2: /mnt/filebrowser/BitLocker-Decrypted,'; then
    if pct status 104 | grep -q running; then
        pct shutdown 104 --timeout 30
        restart_ct=1
    fi
fi
systemctl stop filebrowser-efs
if mountpoint -q /mnt/filebrowser/BitLocker-Decrypted; then
    echo 'EFS mount still busy; refusing replacement.' >&2; exit 1
fi
install -m 700 "$1/efs-view.py" /usr/local/sbin/filebrowser-efs-view.py
install -m 700 "$1/wait-efs-view-host.sh" /usr/local/sbin/filebrowser-wait-efs-view
install -m 644 "$1/filebrowser-efs.service" /etc/systemd/system/filebrowser-efs.service
systemctl daemon-reload
systemctl start filebrowser-efs
[[ $restart_ct == 0 ]] || pct start 104
python3 /usr/local/sbin/filebrowser-efs-view.py status
echo 'Updated; enter the PFX password again using unlock-efs.sh in your private terminal.'
REMOTE
