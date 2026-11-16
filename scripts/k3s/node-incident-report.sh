#!/bin/bash
# Evidence report for a K3s node incident window (NotReady, flapping, slow etcd) - read-only
#
# Usage: ./node-incident-report.sh <proxmox-host> <vmid> "<since>" "<until>"
#   e.g. ./node-incident-report.sh 192.168.4.175 105 "2026-11-16 01:10" "2026-11-16 01:23"
#   (times are UTC, as journalctl inside the VM uses UTC)
#
# Collects, from inside the VM via qm guest exec:
#   - k3s/kubelet log lines about node status, PLEG, lease, timeouts, etcd slowness (counts + samples)
#   - kernel: hung tasks (which tasks), I/O errors, OOM kills, soft lockups, NVIDIA/Xid errors
#   - current memory, swap, dirty/writeback, load, D-state processes, per-disk bdi limits
# and from the Proxmox host:
#   - host kernel hung tasks / I/O errors in the same window, ZFS pool health
# Nothing is changed.

set -euo pipefail
HOST="${1:?proxmox host}"; VMID="${2:?vmid}"; SINCE="${3:?since}"; UNTIL="${4:?until}"

gx() {
  ssh -o ConnectTimeout=10 "root@$HOST" "qm guest exec $VMID --timeout 90 -- bash -c $(printf '%q' "$1")" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.stdout.write(d.get("out-data","")+d.get("err-data",""))'
}

echo "===== VM $VMID on $HOST, window $SINCE .. $UNTIL (UTC)"
gx "
S='$SINCE'; U='$UNTIL'
echo '--- k3s/kubelet: counts by symptom'
journalctl -u k3s --since \"\$S\" --until \"\$U\" --no-pager -o cat > /tmp/k3s-window.log
for p in 'Error updating node status' 'PLEG is not healthy' 'failed to update lease' 'context deadline exceeded' 'apply request took too long' 'leader changed' 'etcdserver: request timed out' 'Kubelet stopped posting' 'connection refused' 'statfs' 'Failed to get' 'Unable to read' ; do
  printf '%6d  %s\n' \"\$(grep -c \"\$p\" /tmp/k3s-window.log)\" \"\$p\"
done
echo '--- k3s: first error/fatal lines in window'
grep -E 'level=(error|fatal)|E[0-9]{4} ' /tmp/k3s-window.log | cut -c1-220 | head -12
echo '--- kernel in window'
journalctl -k --since \"\$S\" --until \"\$U\" --no-pager -o cat > /tmp/kern-window.log
echo \"hung tasks:\"; grep -E 'blocked for more than' /tmp/kern-window.log | sed -E 's/.*task ([^ ]+).*than ([0-9]+).*/  \1 (\2 s)/' | sort | uniq -c
for p in 'I/O error' 'Out of memory' 'oom-kill' 'soft lockup' 'NVRM' 'Xid' 'reset' 'EXT4-fs error' 'blk_update_request'; do
  n=\$(grep -ci \"\$p\" /tmp/kern-window.log); [ \"\$n\" -gt 0 ] && printf '%6d  %s\n' \"\$n\" \"\$p\"
done
echo '--- now: load, memory, swap, dirty'
uptime; free -m | head -3
grep -E '^(Dirty|Writeback|MemAvailable|SwapCached):' /proc/meminfo | tr -s ' '
echo \"bdi max_ratio: sda=\$(cat /sys/block/sda/bdi/max_ratio) sdb=\$(cat /sys/block/sdb/bdi/max_ratio)  vm.dirty_ratio=\$(sysctl -n vm.dirty_ratio)\"
echo '--- now: D-state processes'
ps -eo pid,stat,wchan:32,comm | awk '\$2 ~ /^D/' | head -15
echo '--- now: top CPU'
ps -eo pcpu,pmem,comm --sort=-pcpu | head -8
rm -f /tmp/k3s-window.log /tmp/kern-window.log
"
echo
echo "===== Proxmox host $HOST, same window"
ssh -o ConnectTimeout=10 "root@$HOST" "
journalctl -k --since '$SINCE' --until '$UNTIL' --no-pager -o cat | grep -E 'blocked for more than' | sed -E 's/.*task ([^ ]+).*than ([0-9]+).*/  \1 (\2 s)/' | sort | uniq -c
journalctl -k --since '$SINCE' --until '$UNTIL' --no-pager -o cat | grep -ciE 'I/O error|reset|uas|usb .*disconnect' | sed 's/^/usb\/io errors: /'
zpool status -x
"
