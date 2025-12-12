#!/bin/bash
#
# 01-create-zfs-dataset.sh
#
# Create dedicated ZFS dataset for virtiofs sharing with optimized settings
#

set -euo pipefail

HOST="pumped-piglet.maas"
POOL="local-3TB-backup"
DATASET="frigate-import"
FULL_PATH="${POOL}/${DATASET}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Create ZFS Dataset for VirtioFS"
echo "========================================="
echo ""
echo "Host: $HOST"
echo "Dataset: $FULL_PATH"
echo ""

# Check if dataset already exists
echo "Step 1: Checking if dataset exists..."
if ssh root@$HOST "zfs list $FULL_PATH" 2>/dev/null; then
    echo -e "${YELLOW}Dataset $FULL_PATH already exists${NC}"
    echo ""
    ssh root@$HOST "zfs get all $FULL_PATH | grep -E 'xattr|acltype|atime|sync'"
    echo ""
    echo "To destroy and recreate: zfs destroy $FULL_PATH"
    exit 0
fi

# Create dataset
echo "Step 2: Creating dataset..."
ssh root@$HOST "zfs create $FULL_PATH"
echo -e "${GREEN}Dataset created${NC}"
echo ""

# Set optimized properties for virtiofs
echo "Step 3: Setting virtiofs-optimized properties..."

echo "  - Setting xattr=sa (extended attributes)..."
ssh root@$HOST "zfs set xattr=sa $FULL_PATH"

echo "  - Setting acltype=posixacl (POSIX ACLs)..."
ssh root@$HOST "zfs set acltype=posixacl $FULL_PATH"

echo "  - Setting atime=off (disable access time updates)..."
ssh root@$HOST "zfs set atime=off $FULL_PATH"

echo "  - Setting sync=disabled (async writes for import performance)..."
ssh root@$HOST "zfs set sync=disabled $FULL_PATH"

echo -e "${GREEN}Properties set${NC}"
echo ""

# Verify
echo "Step 4: Verifying dataset..."
ssh root@$HOST "zfs list $FULL_PATH"
echo ""
ssh root@$HOST "zfs get xattr,acltype,atime,sync $FULL_PATH"
echo ""

# Show mount point
MOUNTPOINT=$(ssh root@$HOST "zfs get -H -o value mountpoint $FULL_PATH")
echo "Mountpoint: $MOUNTPOINT"
echo ""

echo "========================================="
echo -e "${GREEN}ZFS dataset created successfully!${NC}"
echo "========================================="
echo ""
echo "Next: Run 02-copy-recordings.sh to copy old recordings"
