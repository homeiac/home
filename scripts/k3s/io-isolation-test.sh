#!/bin/bash
# Does bulk writing to one VM disk slow down fsyncs on another? (etcd-style latency test)
#
# Usage: ./io-isolation-test.sh [proxmox-host] [vmid] [load-seconds]
#        defaults: 192.168.4.175 105 40
#
# Inside the VM (qm guest exec):
#   1. baseline (15 s): 4 KiB write + fdatasync in a loop on the ROOT disk (where etcd keeps its WAL),
#      reports n, median, p99, max latency
#   2. load (<load-seconds>): same measurement while a background dd streams RANDOM data (not zeros:
#      ZFS compression and QEMU detect-zeroes would skip zeros) to the SMB disk (/mnt/samba-storage)
#   3. removes both test files; prints etcd's own "slow fdatasync" count during the run
# If load latency is far above baseline, the two virtual disks are not isolated (e.g. a shared
# virtio-scsi controller without per-disk iothreads). Rerun after a fix to compare.
# It deliberately stresses the node for <load-seconds>; etcd may log slow writes meanwhile.

set -euo pipefail
HOST="${1:-192.168.4.175}"; VMID="${2:-105}"; LOAD_S="${3:-40}"

ssh -o ConnectTimeout=10 "root@$HOST" "qm guest exec $VMID --timeout $((LOAD_S + 90)) -- bash -c $(printf '%q' "
set -e
cat > /tmp/fsync_probe.py <<'PY'
import os, sys, time
path, secs = sys.argv[1], float(sys.argv[2])
fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
lat = []; end = time.time() + secs; buf = os.urandom(4096)
while time.time() < end:
    t = time.time(); os.pwrite(fd, buf, 0); os.fdatasync(fd); lat.append(time.time() - t)
    time.sleep(0.05)
os.close(fd); os.unlink(path); lat.sort()
p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))] * 1000
print('n=%d  median=%.1f ms  p99=%.1f ms  max=%.1f ms' % (len(lat), p(0.5), p(0.99), lat[-1] * 1000))
PY
START=\$(date '+%F %T')
echo -n 'baseline (root disk, no load):   '; python3 /tmp/fsync_probe.py /var/lib/fsync-probe.tmp 15
( timeout $LOAD_S dd if=/dev/urandom of=/mnt/samba-storage/.io-isolation-test bs=1M status=none || true ) &
sleep 2
echo -n 'under load (SMB disk streaming): '; python3 /tmp/fsync_probe.py /var/lib/fsync-probe.tmp $((LOAD_S - 4))
wait
echo \"SMB disk written during load: \$(du -m /mnt/samba-storage/.io-isolation-test | cut -f1) MB\"
rm -f /mnt/samba-storage/.io-isolation-test /tmp/fsync_probe.py
echo \"etcd 'slow fdatasync' during test: \$(journalctl -u k3s --since \"\$START\" --no-pager | grep -c 'slow fdatasync')\"
")" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.stdout.write(d.get("out-data","")+d.get("err-data",""))'
