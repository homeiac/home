#!/bin/bash
# Cleanly reboot a Proxmox host: stop guests gracefully first, reboot, wait for SSH, list what came back
#
# Usage: ./reboot-host-safely.sh <host-ip-or-name> [--yes]
#   (--yes skips the 5 s abort window)
#
# 1. kills leftover "bash -s" helper scripts we started on the host (e.g. a half-run vm105-disk-isolation.sh),
#    so nothing restarts a guest mid-shutdown
# 2. qm shutdown / pct shutdown every running guest (300 s each, then force stop)
# 3. reboot (detached, so the SSH drop does not matter), then waits up to 15 min for SSH and prints guests
# Guests with onboot=1 start by themselves; VM 105 (GPU passthrough + 32 GB memfd) needs ~5-10 min.
# Used 2026-11-16 when the USB-HDD ZFS pool wedged (zfs create stuck in txg_wait_synced behind PBS GC).

set -euo pipefail
HOST="${1:?host}"; [[ "${2:-}" == --yes ]] || { echo "Rebooting $HOST in 5 s - Ctrl-C to abort"; sleep 5; }
R="ssh -o ConnectTimeout=10 root@$HOST"
# match the exact command line "bash -s" (a looser pattern also matches this very ssh command's shell)
$R 'for p in $(pgrep -f "^bash -s$"); do kill -9 $p; done; true'
$R 'for v in $(qm list | awk "NR>1 && \$3==\"running\"{print \$1}"); do echo "qm shutdown $v"; qm shutdown $v --timeout 300 --forceStop 1; done
    for c in $(pct list | awk "NR>1 && \$2==\"running\"{print \$1}"); do echo "pct shutdown $c"; pct shutdown $c --timeout 120 --forceStop 1; done
    echo "guests stopped, rebooting at $(date -u +%T)"; systemd-run --on-active=3 --unit=safe-reboot systemctl reboot'
sleep 30
for i in $(seq 1 90); do $R true 2>/dev/null && break; sleep 10; done
$R 'echo "up since: $(uptime -s)"; zpool status -x; qm list; pct list'
