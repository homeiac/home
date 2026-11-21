#!/usr/bin/env bash
# Wait for the host FUSE mount before LXC captures it as a bind mount.
set -euo pipefail
for attempt in {1..30}; do
    if mountpoint -q /mnt/filebrowser/BitLocker-Decrypted && test -S /run/filebrowser-efs/unlock.sock; then
        exit 0
    fi
    sleep 1
done
echo 'EFS view did not become ready.' >&2
exit 1
