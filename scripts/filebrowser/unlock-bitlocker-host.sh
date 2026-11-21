#!/usr/bin/env bash
# Run on piglet. Reads the BitLocker password privately from the terminal.
# No key is stored, no header is changed, and both mapping and mount are read-only.
set -euo pipefail
[[ $(hostname -s) == pumped-piglet && $EUID == 0 ]] || exit 1
device=/dev/disk/by-partuuid/00024711-01
mapper=/dev/mapper/filebrowser-bitlocker
target=/mnt/filebrowser/BitLocker
[[ $(blkid -s TYPE -o value "$device") == BitLocker ]] || {
    echo 'Expected BitLocker partition was not found; refusing to proceed.' >&2; exit 1;
}
if [[ ! -b "$mapper" ]]; then
    echo 'Enter the BitLocker password or recovery key. Input is hidden; five attempts are allowed.'
    if ! cryptsetup open --type bitlk --readonly --tries 5 "$device" filebrowser-bitlocker; then
        echo 'The disk remains locked. Rerun this script to try again.' >&2
        exit 1
    fi
fi
[[ $(blockdev --getro "$mapper") == 1 ]] || {
    echo 'Existing mapping is not read-only; refusing to mount it.' >&2; exit 1;
}
mkdir -p "$target"
if ! mountpoint -q "$target"; then
    mount -t ntfs-3g -o ro,nosuid,nodev,noexec,uid=100000,gid=100000,fmask=0133,dmask=0022 "$mapper" "$target"
fi
findmnt -rn -M "$target" -o OPTIONS | grep -Eq '(^|,)ro(,|$)'
if [[ -f /etc/pve/lxc/104.conf ]]; then
    grep -q '^hostname: filebrowser$' /etc/pve/lxc/104.conf
    backup_dir=/root/filebrowser-backups/$(date +%Y%m%dT%H%M%S)
    mkdir -p "$backup_dir"
    cp /etc/pve/lxc/104.conf "$backup_dir/104.conf"
    pct set 104 -mp2 "$target,mp=/srv/files/BitLocker,ro=1,backup=0"
    # Refresh the bind mount even if the container previously saw an empty directory.
    pct shutdown 104 --timeout 30
    pct start 104
fi
echo 'BitLocker is unlocked and mounted read-only. Refresh FileBrowser after it restarts.'
