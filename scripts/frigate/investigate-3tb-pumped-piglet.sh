#!/bin/bash
# Investigation script for 3TB storage detection on pumped-piglet
# This gathers information needed for mount script

set -euo pipefail

HOST="root@pumped-piglet.maas"

echo "=== Investigating available storage on pumped-piglet ==="
echo

echo "--- All block devices ---"
ssh "$HOST" "lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT"
echo

echo "--- ZFS pools (if any) ---"
ssh "$HOST" "zpool list 2>/dev/null || echo 'No ZFS pools currently imported'"
echo

echo "--- Available ZFS pools to import ---"
ssh "$HOST" "zpool import 2>/dev/null || echo 'No pools available to import'"
echo

echo "--- Disk IDs and labels ---"
ssh "$HOST" "blkid | grep -E '(2.7T|3T|zfs)' || blkid"
echo

echo "--- Current mounts ---"
ssh "$HOST" "df -h"
echo

echo "=== Investigation complete ==="
