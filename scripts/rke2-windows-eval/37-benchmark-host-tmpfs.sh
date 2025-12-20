#!/bin/bash
# Benchmark tmpfs directly on Proxmox host (no VM overhead)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"

echo "=== Direct tmpfs Benchmark (no VM overhead) ==="
echo ""

ssh -o StrictHostKeyChecking=no root@${PROXMOX_HOST} '
cd /mnt/ramdisk

# Sequential write 1GB
echo "--- Sequential Write (1GB) ---"
START=$(date +%s.%N)
dd if=/dev/zero of=testfile bs=1M count=1024 conv=fdatasync 2>&1 | tail -1
END=$(date +%s.%N)
ELAPSED=$(echo "$END - $START" | bc)
SPEED=$(echo "scale=2; 1024 / $ELAPSED" | bc)
echo "Speed: $SPEED MB/s"
echo ""

# Sequential read
echo "--- Sequential Read (1GB) ---"
echo 3 > /proc/sys/vm/drop_caches
START=$(date +%s.%N)
dd if=testfile of=/dev/null bs=1M 2>&1 | tail -1
END=$(date +%s.%N)
ELAPSED=$(echo "$END - $START" | bc)
SPEED=$(echo "scale=2; 1024 / $ELAPSED" | bc)
echo "Speed: $SPEED MB/s"
echo ""

# Small file creation
echo "--- Small Files (1000 x 4KB) ---"
mkdir -p smalltest
START=$(date +%s.%N)
for i in $(seq 1 1000); do dd if=/dev/zero of=smalltest/file$i bs=4096 count=1 2>/dev/null; done
END=$(date +%s.%N)
ELAPSED=$(echo "$END - $START" | bc)
RATE=$(echo "scale=2; 1000 / $ELAPSED" | bc)
echo "Rate: $RATE files/sec"

# Cleanup
rm -rf testfile smalltest
'

echo ""
echo "=== Comparison ==="
echo "VM (tmpfs-backed):  3123 MB/s write, 5023 MB/s read, 2042 files/sec"
echo "See above for raw tmpfs performance (no QEMU overhead)"
