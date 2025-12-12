#!/bin/bash
#
# 03-create-directory-mapping.sh
#
# Create Proxmox Directory Mapping for virtiofs via pvesh API
#

set -euo pipefail

HOST="pumped-piglet.maas"
MAPPING_ID="frigate-import"
MAPPING_PATH="/local-3TB-backup/frigate-import"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Create Proxmox Directory Mapping"
echo "========================================="
echo ""
echo "Host: $HOST"
echo "Mapping ID: $MAPPING_ID"
echo "Path: $MAPPING_PATH"
echo ""

# Check if mapping already exists
echo "Step 1: Checking existing mappings..."
EXISTING=$(ssh root@$HOST "pvesh get /cluster/mapping/dir --output-format json 2>/dev/null" || echo "[]")

if echo "$EXISTING" | grep -q "\"$MAPPING_ID\""; then
    echo -e "${YELLOW}Mapping '$MAPPING_ID' already exists${NC}"
    echo ""
    ssh root@$HOST "pvesh get /cluster/mapping/dir/$MAPPING_ID --output-format yaml"
    echo ""
    echo "To delete: pvesh delete /cluster/mapping/dir/$MAPPING_ID"
    exit 0
fi

echo "No existing mapping found"
echo ""

# Check path exists and has data
echo "Step 2: Verifying path has data..."
ssh root@$HOST "ls -la $MAPPING_PATH | head -10"
echo ""

# Create mapping
echo "Step 3: Creating directory mapping..."
ssh root@$HOST "pvesh create /cluster/mapping/dir --id $MAPPING_ID --map node=pumped-piglet,path=$MAPPING_PATH"
echo -e "${GREEN}Mapping created${NC}"
echo ""

# Verify
echo "Step 4: Verifying mapping..."
ssh root@$HOST "pvesh get /cluster/mapping/dir/$MAPPING_ID --output-format yaml"
echo ""

echo "========================================="
echo -e "${GREEN}Directory mapping created!${NC}"
echo "========================================="
echo ""
echo "The mapping is now visible in Proxmox GUI:"
echo "  Datacenter -> Resource Mappings -> Directory"
echo ""
echo "Next: Run 04-attach-virtiofs-to-vm.sh"
