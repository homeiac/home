#!/bin/bash
# Run io-isolation-test.sh while sampling the Proxmox HOST: are the shared ZFS zvol worker threads blocked?
#
# Usage: ./io-isolation-host-probe.sh [proxmox-host] [vmid] [load-seconds]     defaults: 192.168.4.175 105 40
#
# Hypothesis (2026-11-16): every VM disk is a ZFS volume, and ZFS serves ALL volumes from one shared pool of
# zvol_tq worker threads. When the slow USB pool throttles writers (dmu_tx wait), those threads block and requests
# for the fast NVMe volume queue behind them (head-of-line blocking) - invisible in NVMe pool stats, unaffected by
# virtio-scsi-single/iothreads (tried, no change) and by guest dirty-page limits (direct I/O still stalled).
# 1. waits until the VM is quiet (guest Dirty+Writeback < 30 MB, 1 s of sdb idle), max 5 min
# 2. samples the host every 1 s for the duration of the test: number of zvol* threads in D state and their wchan
# 3. runs io-isolation-test.sh, then prints the sampler summary + the zfs module parameters involved
set -euo pipefail
HOST="${1:-192.168.4.175}"; VMID="${2:-105}"; LOAD_S="${3:-40}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="ssh -o ConnectTimeout=10 root@$HOST"
gx() { $R "qm guest exec $VMID --timeout 30 -- bash -c $(printf '%q' "$1")" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("out-data","").strip())'; }

for i in $(seq 1 30); do
  d=$(gx "awk '/^(Dirty|Writeback):/{s+=\$2} END{print int(s/1024)}' /proc/meminfo")
  [[ "${d:-999}" -lt 30 ]] && { echo "VM quiet (dirty+writeback ${d} MB)"; break; }
  echo "waiting for the VM to flush ($d MB dirty+writeback)"; sleep 10
done

$R "rm -f /tmp/zvol-sample.log; nohup bash -c 'end=\$((SECONDS+$((LOAD_S+25)))); while [ \$SECONDS -lt \$end ]; do
  ps -eLo stat,wchan:30,comm | awk \"\\\$3 ~ /^zvol/ {t++; if (\\\$1 ~ /^D/) {d++; w[\\\$2]++}} END{printf \\\"%d/%d \\\", d+0, t+0; for (k in w) printf \\\"%s=%d \\\", k, w[k]; print \\\"\\\"}\" >> /tmp/zvol-sample.log; sleep 1; done' >/dev/null 2>&1 &"
"$DIR/io-isolation-test.sh" "$HOST" "$VMID" "$LOAD_S"
sleep 3
echo "--- host zvol worker threads blocked (D) / total, per second; max and wait channels"
$R "sort -t/ -k1 -n /tmp/zvol-sample.log | tail -1 | sed 's/^/peak: /'; echo samples: \$(wc -l < /tmp/zvol-sample.log), with any blocked: \$(awk '\$1 !~ /^0\//' /tmp/zvol-sample.log | wc -l); awk '\$1 !~ /^0\//' /tmp/zvol-sample.log | head -6
  echo '--- zfs module parameters'; for p in zvol_threads zvol_num_taskqs zvol_request_sync zvol_prefetch_bytes zfs_dirty_data_max zfs_txg_timeout; do printf '%s=' \$p; cat /sys/module/zfs/parameters/\$p 2>/dev/null || echo n/a; done"
