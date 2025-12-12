#!/bin/bash
#
# mount-3tb-pumped-piglet.sh
#
# Mount the 3TB storage on pumped-piglet for K8s Frigate recordings
#

set -euo pipefail

HOST="pumped-piglet.maas"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Mount 3TB Storage on pumped-piglet"
echo "========================================="
echo ""

# Step 1: Check available disks
echo "Step 1: Checking available disks..."
ssh root@$HOST "lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE"
echo ""

# Step 2: Check for ZFS pools
echo "Step 2: Checking ZFS pools..."
ssh root@$HOST "zpool list 2>/dev/null || echo 'No ZFS pools found'"
ssh root@$HOST "zpool import 2>/dev/null || echo 'No pools available for import'"
echo ""

# Step 3: Check blkid for filesystem info
echo "Step 3: Checking filesystem info..."
ssh root@$HOST "blkid | grep -v loop || true"
echo ""

echo "========================================="
echo "Manual steps needed:"
echo "========================================="
echo ""
echo "Based on the output above, determine:"
echo "1. Is this a ZFS pool? Use: zpool import <pool-name>"
echo "2. Is this ext4/xfs? Use: mount /dev/sdX /mount/point"
echo ""
echo "Then update this script with the correct commands."
