#!/bin/bash
# Clean up stale pool cache on still-fawn
# The pool has been imported on pumped-piglet, need to clear still-fawn's cache

set -euo pipefail

HOST="root@still-fawn.maas"
POOL="local-3TB-backup"

echo "=== Cleaning up stale pool cache on still-fawn ==="
echo

# Step 1: Try to clear the pool (will fail but refresh cache)
echo "--- Step 1: Attempting to clear pool (expected to fail) ---"
ssh "$HOST" "zpool clear $POOL 2>&1 || echo 'Pool clear failed (expected - pool is on another host)'"
echo

# Step 2: Force export to clear from cache
echo "--- Step 2: Force clearing pool from still-fawn cache ---"
ssh "$HOST" "zpool export -f $POOL 2>&1 || echo 'Export failed or pool already released'"
echo

# Step 3: Verify pool is gone from still-fawn
echo "--- Step 3: Verification ---"
echo "Pools on still-fawn:"
ssh "$HOST" "zpool list || echo 'No pools'"
echo

echo "=== Cleanup complete ==="
