#!/usr/bin/env bash
# Read-only check for USB backup jobs that could conflict with read-only mounts.
set -euo pipefail
ssh -o BatchMode=yes "root@${1:-pumped-piglet.maas}" 'bash -s' <<'REMOTE'
systemctl list-timers --all --no-pager | grep -Ei 'cloud|mirror|backup' || true
systemctl list-unit-files --no-pager | grep -Ei 'cloud-backup|mirror' || true
find /usr/local/sbin /usr/local/bin -maxdepth 1 -name '*cloud-backup*' -printf '%f\n'
REMOTE
