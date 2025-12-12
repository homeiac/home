#!/bin/bash
#
# 02-copy-recordings.sh
#
# Copy old Frigate recordings to new virtiofs dataset
# This is a one-time operation, ~120GB, takes 10-30 minutes
#

set -euo pipefail

HOST="pumped-piglet.maas"
SOURCE="/local-3TB-backup/subvol-113-disk-0/frigate/"
DEST="/local-3TB-backup/frigate-import/"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Copy Old Frigate Recordings"
echo "========================================="
echo ""
echo "Host: $HOST"
echo "Source: $SOURCE"
echo "Dest: $DEST"
echo ""

# Check source exists and show size
echo "Step 1: Checking source data..."
ssh root@$HOST "du -sh $SOURCE"
echo ""

# Check destination exists
echo "Step 2: Checking destination..."
if ! ssh root@$HOST "test -d $DEST"; then
    echo -e "${RED}Destination $DEST does not exist!${NC}"
    echo "Run 01-create-zfs-dataset.sh first"
    exit 1
fi
echo -e "${GREEN}Destination exists${NC}"
echo ""

# Check if data already copied
echo "Step 3: Checking if data already copied..."
DEST_SIZE=$(ssh root@$HOST "du -s $DEST 2>/dev/null | cut -f1" || echo "0")
if [ "$DEST_SIZE" -gt 1000000 ]; then  # > 1GB
    DEST_HUMAN=$(ssh root@$HOST "du -sh $DEST")
    echo -e "${YELLOW}Destination already has data: $DEST_HUMAN${NC}"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted"
        exit 0
    fi
fi

# Start copy
echo "Step 4: Starting rsync copy..."
echo "This may take 10-30 minutes for ~120GB"
echo ""
echo "Command: rsync -avP --stats $SOURCE $DEST"
echo ""

START_TIME=$(date +%s)

ssh root@$HOST "rsync -avP --stats $SOURCE $DEST"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

echo ""
echo "========================================="
echo -e "${GREEN}Copy complete!${NC}"
echo "========================================="
echo ""
echo "Duration: ${MINUTES}m ${SECONDS}s"
echo ""

# Verify
echo "Step 5: Verifying copy..."
echo ""
echo "Source size:"
ssh root@$HOST "du -sh $SOURCE"
echo ""
echo "Destination size:"
ssh root@$HOST "du -sh $DEST"
echo ""
echo "Destination contents:"
ssh root@$HOST "ls -la $DEST"
echo ""

echo "Next: Run 03-create-directory-mapping.sh"
