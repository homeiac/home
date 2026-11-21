#!/usr/bin/env bash
# Run on piglet. Preserve existing USB backup writers; expose read-only bind views.
# The cloud-backup lock prevents changing mounts during a mirror run.
set -euo pipefail
[[ $(hostname -s) == pumped-piglet && $EUID == 0 ]] || exit 1
exec 9>/run/cloud-backup-mirror.lock
flock -n 9 || { echo 'A USB backup is running; retry after it finishes.' >&2; exit 1; }
for uuid in EBFF-FC78 1860-6D8F; do
    [[ $(blkid -s TYPE -o value "/dev/disk/by-uuid/$uuid") == exfat ]] || exit 1
done
backup_dir=/root/filebrowser-backups/$(date +%Y%m%dT%H%M%S)-mounts
install -d -m 700 "$backup_dir"
cp /etc/fstab "$backup_dir/fstab"
restart_container=0
if [[ -f /etc/pve/lxc/104.conf ]]; then
    grep -q '^hostname: filebrowser$' /etc/pve/lxc/104.conf
    cp /etc/pve/lxc/104.conf "$backup_dir/104.conf"
    if pct status 104 | grep -q running; then
        pct shutdown 104 --timeout 30
        restart_container=1
    fi
fi
python3 - <<'PY'
from pathlib import Path
fstab = Path('/etc/fstab')
identities = {'UUID=EBFF-FC78', 'UUID=1860-6D8F'}
targets = {'/mnt/filebrowser/SSK', '/mnt/filebrowser/RASPBMC', '/mnt/ssk-cloud', '/mnt/wd25-cloud'}
lines = []
for line in fstab.read_text().splitlines():
    fields = line.split()
    if fields and not fields[0].startswith('#') and (fields[0] in identities or (len(fields) > 1 and fields[1] in targets)):
        continue
    lines.append(line)
for uuid, label, primary in [('EBFF-FC78', 'SSK', '/mnt/ssk-cloud'), ('1860-6D8F', 'RASPBMC', '/mnt/wd25-cloud')]:
    lines.append(f'UUID={uuid} {primary} exfat rw,nosuid,nodev,noexec,noatime,nofail,x-systemd.device-timeout=10s,uid=100000,gid=100000,fmask=0133,dmask=0022 0 0')
    lines.append(f'{primary} /mnt/filebrowser/{label} none bind,ro,nosuid,nodev,noexec,nofail,x-systemd.requires={primary} 0 0')
fstab.write_text('\n'.join(lines) + '\n')
PY
systemctl daemon-reload
for entry in EBFF-FC78:SSK:/mnt/ssk-cloud 1860-6D8F:RASPBMC:/mnt/wd25-cloud; do
    IFS=: read -r uuid label primary <<< "$entry"
    view=/mnt/filebrowser/$label
    mkdir -p "$primary" "$view"
    if mountpoint -q "$view"; then umount "$view"; fi
    if mountpoint -q "$primary"; then
        [[ $(findmnt -rn -M "$primary" -o UUID) == "$uuid" ]] || exit 1
        findmnt -rn -M "$primary" -o OPTIONS | grep -Eq '(^|,)rw(,|$)' || exit 1
    else
        mount "$primary"
    fi
    mount "$view"
    [[ $(findmnt -rn -M "$view" -o UUID) == "$uuid" ]]
    findmnt -rn -M "$view" -o OPTIONS | grep -Eq '(^|,)ro(,|$)'
    findmnt -rn -M "$primary" -o OPTIONS | grep -Eq '(^|,)rw(,|$)'
    # Only create/remove our own temporary probe, never modify an existing file.
    probe=$(mktemp "$primary/.filebrowser-backup-probe.XXXXXX")
    rm -- "$probe"
    echo "$label: backup path writable; FileBrowser view read-only"
done
if [[ $restart_container == 1 ]]; then pct start 104; fi
echo "Configuration backup: $backup_dir"
