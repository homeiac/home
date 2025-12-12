#!/bin/bash
# Unmount 3TB ZFS pool from still-fawn
# Pool: local-3TB-backup (currently SUSPENDED)
# Active datasets: /, backup-tmpdir, subvol-113-disk-0

set -euo pipefail

HOST="root@still-fawn.maas"
POOL="local-3TB-backup"

echo "=== Unmounting 3TB ZFS pool from still-fawn ==="
echo

# Step 1: Check what's using the pool
echo "--- Step 1: Checking processes using the pool ---"
ssh "$HOST" "lsof +D /local-3TB-backup 2>/dev/null || echo 'No processes found via lsof'"
echo

ssh "$HOST" "fuser -v -m /local-3TB-backup 2>&1 || echo 'No processes found via fuser'"
echo

# Step 2: Stop any LXC containers using this storage
echo "--- Step 2: Checking for LXC containers using this storage ---"
CONTAINERS=$(ssh "$HOST" "pct list | grep -E '(113)' || echo ''")
if [ -n "$CONTAINERS" ]; then
    echo "Found containers that may be using this storage:"
    echo "$CONTAINERS"
    echo
    echo "Stopping container 113 (Frigate)..."
    ssh "$HOST" "pct stop 113 || echo 'Container 113 already stopped'"
    sleep 5
else
    echo "No relevant containers found running"
fi
echo

# Step 3: Unmount all datasets in reverse order
echo "--- Step 3: Unmounting ZFS datasets ---"
echo "Unmounting subvol-113-disk-0..."
ssh "$HOST" "umount /local-3TB-backup/subvol-113-disk-0 2>/dev/null || zfs unmount local-3TB-backup/subvol-113-disk-0 || echo 'Already unmounted'"

echo "Unmounting backup-tmpdir..."
ssh "$HOST" "umount /local-3TB-backup/backup-tmpdir 2>/dev/null || zfs unmount local-3TB-backup/backup-tmpdir || echo 'Already unmounted'"

echo "Unmounting pool root..."
ssh "$HOST" "umount /local-3TB-backup 2>/dev/null || zfs unmount local-3TB-backup || echo 'Already unmounted'"
echo

# Step 4: Export the pool
echo "--- Step 4: Exporting ZFS pool ---"
ssh "$HOST" "zpool export $POOL && echo 'Pool exported successfully' || echo 'Pool export failed or already exported'"
echo

# Step 5: Verify
echo "--- Step 5: Verification ---"
echo "Remaining ZFS pools on still-fawn:"
ssh "$HOST" "zpool list"
echo

echo "Checking if pool is available for import:"
ssh "$HOST" "zpool import | grep -A 5 '$POOL' || echo 'Pool not visible for import (expected - disk will be physically moved)'"
echo

echo "=== Unmount complete ==="
echo "The 3TB disk can now be physically moved to pumped-piglet"
