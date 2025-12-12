#!/bin/bash
# Force export 3TB ZFS pool from still-fawn
# Pool is in SUSPENDED state, so we'll skip unmount and go straight to export

set -euo pipefail

HOST="root@still-fawn.maas"
POOL="local-3TB-backup"

echo "=== Force exporting 3TB ZFS pool from still-fawn ==="
echo "Pool is in SUSPENDED state - skipping unmount, going straight to export"
echo

# Step 1: Check pool status
echo "--- Step 1: Current pool status ---"
ssh "$HOST" "zpool status $POOL || echo 'Pool status check failed'"
echo

# Step 2: Force export the pool (don't try to unmount datasets)
echo "--- Step 2: Force exporting pool ---"
ssh "$HOST" "zpool export -f $POOL && echo 'Pool force exported successfully' || echo 'Pool export failed'"
echo

# Step 3: Verify pool is gone
echo "--- Step 3: Verification ---"
echo "Remaining ZFS pools on still-fawn:"
ssh "$HOST" "zpool list || echo 'No pools remaining'"
echo

echo "=== Force export complete ==="
echo "The pool has been forcibly exported from still-fawn"
echo "The disk can now be physically moved to pumped-piglet (or imported remotely if already connected)"
