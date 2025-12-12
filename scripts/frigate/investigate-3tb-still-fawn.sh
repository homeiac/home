#!/bin/bash
# Investigation script for 3TB storage on still-fawn
# This gathers information needed for unmount script

set -euo pipefail

HOST="root@still-fawn.maas"

echo "=== Investigating 3TB storage on still-fawn ==="
echo

echo "--- ZFS pools ---"
ssh "$HOST" "zpool list"
echo

echo "--- ZFS datasets ---"
ssh "$HOST" "zfs list"
echo

echo "--- Mount points ---"
ssh "$HOST" "df -h | grep -E '(3T|3.0T|2.7T|local-3TB)' || echo 'No 3TB mounts found by size pattern'"
echo

echo "--- All ZFS mounts ---"
ssh "$HOST" "mount | grep zfs"
echo

echo "--- Block devices ---"
ssh "$HOST" "lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | grep -E '(2.7T|3T)' || echo 'No 3TB devices found by size pattern'"
echo

echo "=== Investigation complete ==="
