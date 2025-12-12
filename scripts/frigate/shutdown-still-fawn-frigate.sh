#!/bin/bash
set -euo pipefail

# shutdown-still-fawn-frigate.sh
# Safely shuts down Frigate LXC 110 on still-fawn.maas after K8s migration is verified
#
# Usage: ./shutdown-still-fawn-frigate.sh [-y|--yes]
#   -y, --yes    Skip all confirmation prompts (auto-confirm)
#
# What this script does:
# 1. Runs K8s Frigate verification checks
# 2. Creates a snapshot of LXC 110 before stopping (for easy rollback)
# 3. Stops the container
# 4. Disables auto-start
# 5. Provides rollback instructions
#
# IMPORTANT: Recordings on still-fawn (116GB on local-3TB-backup) are NOT deleted
# They can be imported to K8s Frigate later if needed

# Parse arguments
AUTO_YES=false
while [[ $# -gt 0 ]]; do
    case $1 in
        -y|--yes)
            AUTO_YES=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [-y|--yes]"
            exit 1
            ;;
    esac
done

LXC_ID="110"
LXC_HOST="still-fawn.maas"
SNAPSHOT_NAME="pre-k8s-migration-$(date +%Y%m%d-%H%M%S)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Helper function for confirmations
confirm() {
    local prompt="$1"
    if [[ "$AUTO_YES" == true ]]; then
        echo "$prompt yes (auto-confirmed)"
        return 0
    fi
    read -p "$prompt " response
    [[ "$response" == "yes" ]]
}

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================="
echo "Shutdown still-fawn Frigate LXC"
echo "========================================="
echo ""
echo "This script will:"
echo "  1. Verify K8s Frigate is working correctly"
echo "  2. Create a snapshot of LXC $LXC_ID"
echo "  3. Stop LXC $LXC_ID on $LXC_HOST"
echo "  4. Disable auto-start for LXC $LXC_ID"
echo ""
echo -e "${YELLOW}WARNING: This will stop your current Frigate instance!${NC}"
echo "Make sure K8s Frigate is fully configured before proceeding."
echo ""

# Step 1: Verify K8s Frigate
echo "========================================="
echo "Step 1: Verifying K8s Frigate"
echo "========================================="
echo ""

VERIFY_SCRIPT="$SCRIPT_DIR/verify-frigate-k8s.sh"
if [ ! -f "$VERIFY_SCRIPT" ]; then
    echo -e "${RED}ERROR: Verification script not found at $VERIFY_SCRIPT${NC}"
    exit 1
fi

if ! bash "$VERIFY_SCRIPT"; then
    echo ""
    echo -e "${RED}K8s Frigate verification FAILED!${NC}"
    echo "Do NOT proceed with shutdown until K8s Frigate is working correctly."
    echo ""
    if ! confirm "Do you want to proceed anyway? (type 'yes' to confirm):"; then
        echo "Aborting shutdown."
        exit 1
    fi
    echo -e "${YELLOW}Proceeding despite failed verification...${NC}"
fi

echo ""
echo "========================================="
echo "Step 2: User Confirmation"
echo "========================================="
echo ""
echo "Before proceeding, please confirm:"
echo "  - You have tested K8s Frigate with your cameras"
echo "  - Coral TPU detection is working in K8s"
echo "  - You have updated Home Assistant to point to new Frigate URL"
echo "  - You understand recordings on still-fawn will NOT be deleted"
echo ""
if ! confirm "Proceed with shutdown of LXC $LXC_ID? (type 'yes' to confirm):"; then
    echo "Shutdown cancelled."
    exit 0
fi

echo ""
echo "========================================="
echo "Step 3: Creating Snapshot"
echo "========================================="
echo ""

echo "Creating snapshot '$SNAPSHOT_NAME' on $LXC_HOST..."
if ssh "root@$LXC_HOST" "pct snapshot $LXC_ID $SNAPSHOT_NAME --description 'Pre-K8s migration backup'"; then
    echo -e "${GREEN}✓ Snapshot created successfully${NC}"
else
    echo -e "${RED}✗ Failed to create snapshot!${NC}"
    if ! confirm "Continue without snapshot? (type 'yes' to confirm):"; then
        echo "Aborting shutdown."
        exit 1
    fi
fi

echo ""
echo "========================================="
echo "Step 4: Stopping LXC Container"
echo "========================================="
echo ""

echo "Stopping LXC $LXC_ID on $LXC_HOST..."
# Check if already stopped
if ssh "root@$LXC_HOST" "pct status $LXC_ID" 2>/dev/null | grep -q "stopped"; then
    echo -e "${GREEN}✓ Container is already stopped${NC}"
elif ssh "root@$LXC_HOST" "pct stop $LXC_ID"; then
    echo -e "${GREEN}✓ Container stopped successfully${NC}"
else
    echo -e "${RED}✗ Failed to stop container!${NC}"
    echo "You may need to manually stop it:"
    echo "  ssh root@$LXC_HOST 'pct stop $LXC_ID'"
    exit 1
fi

echo ""
echo "========================================="
echo "Step 5: Disabling Auto-Start"
echo "========================================="
echo ""

echo "Disabling auto-start for LXC $LXC_ID..."
if ssh "root@$LXC_HOST" "pct set $LXC_ID -onboot 0"; then
    echo -e "${GREEN}✓ Auto-start disabled${NC}"
else
    echo -e "${RED}✗ Failed to disable auto-start!${NC}"
    echo "You may need to manually disable it:"
    echo "  ssh root@$LXC_HOST 'pct set $LXC_ID -onboot 0'"
fi

echo ""
echo "========================================="
echo "Shutdown Complete!"
echo "========================================="
echo ""
echo -e "${GREEN}✓ still-fawn Frigate LXC has been shut down${NC}"
echo ""
echo "Important information:"
echo "  - Container ID: $LXC_ID"
echo "  - Host: $LXC_HOST"
echo "  - Snapshot: $SNAPSHOT_NAME"
echo "  - Recordings: Still on local-3TB-backup (116GB) - NOT deleted"
echo "  - Coral USB TPU: Still physically attached to still-fawn"
echo ""
echo "Next steps:"
echo "  1. Verify K8s Frigate is working correctly with cameras"
echo "  2. Update Home Assistant integrations to use new Frigate URL"
echo "  3. Test all automations that depend on Frigate"
echo ""
echo -e "${BLUE}Rollback instructions:${NC}"
echo "  If you need to rollback to still-fawn Frigate, run:"
echo "  $SCRIPT_DIR/rollback-to-still-fawn.sh"
echo ""
echo "Recording migration (optional):"
echo "  To import recordings from still-fawn to K8s Frigate later:"
echo "  1. Mount local-3TB-backup storage in K8s Frigate pod"
echo "  2. Copy /var/lib/frigate/recordings to new location"
echo "  3. Frigate will detect and index the recordings"
echo ""
