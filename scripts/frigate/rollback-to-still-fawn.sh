#!/bin/bash
set -euo pipefail

# rollback-to-still-fawn.sh
# Rollback to still-fawn Frigate LXC if K8s migration has issues
#
# What this script does:
# 1. Re-enables auto-start for LXC 110
# 2. Starts LXC 110 back up
# 3. Verifies Frigate is running
# 4. Provides instructions to update Home Assistant

LXC_ID="110"
LXC_HOST="still-fawn.maas"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================="
echo "Rollback to still-fawn Frigate LXC"
echo "========================================="
echo ""
echo "This script will:"
echo "  1. Re-enable auto-start for LXC $LXC_ID"
echo "  2. Start LXC $LXC_ID on $LXC_HOST"
echo "  3. Verify Frigate is running"
echo ""

read -p "Proceed with rollback? (type 'yes' to confirm): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Rollback cancelled."
    exit 0
fi

echo ""
echo "========================================="
echo "Step 1: Re-enabling Auto-Start"
echo "========================================="
echo ""

echo "Re-enabling auto-start for LXC $LXC_ID..."
if ssh "root@$LXC_HOST" "pct set $LXC_ID -onboot 1"; then
    echo -e "${GREEN}✓ Auto-start re-enabled${NC}"
else
    echo -e "${RED}✗ Failed to re-enable auto-start!${NC}"
    echo "You may need to manually enable it:"
    echo "  ssh root@$LXC_HOST 'pct set $LXC_ID -onboot 1'"
fi

echo ""
echo "========================================="
echo "Step 2: Starting LXC Container"
echo "========================================="
echo ""

echo "Starting LXC $LXC_ID on $LXC_HOST..."
if ssh "root@$LXC_HOST" "pct start $LXC_ID"; then
    echo -e "${GREEN}✓ Container started successfully${NC}"
else
    echo -e "${RED}✗ Failed to start container!${NC}"
    echo "You may need to manually start it:"
    echo "  ssh root@$LXC_HOST 'pct start $LXC_ID'"
    exit 1
fi

echo ""
echo "Waiting 10 seconds for Frigate to initialize..."
sleep 10

echo ""
echo "========================================="
echo "Step 3: Verifying Frigate"
echo "========================================="
echo ""

echo "Checking Frigate container status..."
CONTAINER_STATUS=$(ssh "root@$LXC_HOST" "pct status $LXC_ID" 2>/dev/null || echo "unknown")
if echo "$CONTAINER_STATUS" | grep -q "running"; then
    echo -e "${GREEN}✓ Container is running${NC}"
else
    echo -e "${RED}✗ Container status: $CONTAINER_STATUS${NC}"
fi

echo ""
echo "Checking Frigate API..."
# Get the container's IP address
CONTAINER_IP=$(ssh "root@$LXC_HOST" "pct exec $LXC_ID -- hostname -I | awk '{print \$1}'" 2>/dev/null || echo "")

if [ -n "$CONTAINER_IP" ]; then
    echo "Container IP: $CONTAINER_IP"
    FRIGATE_URL="http://$CONTAINER_IP:5000"

    # Wait for API to be ready (up to 30 seconds)
    echo "Waiting for Frigate API to respond..."
    API_READY=false
    for i in {1..6}; do
        if curl -sf "$FRIGATE_URL/api/stats" -o /dev/null --connect-timeout 5 --max-time 10 2>/dev/null; then
            API_READY=true
            break
        fi
        echo "  Attempt $i/6 - waiting 5 seconds..."
        sleep 5
    done

    if [ "$API_READY" = true ]; then
        echo -e "${GREEN}✓ Frigate API is responding${NC}"

        # Get stats
        STATS=$(curl -sf "$FRIGATE_URL/api/stats" 2>/dev/null || echo "{}")
        if echo "$STATS" | jq empty 2>/dev/null; then
            # Check for Coral TPU
            CORAL_STATUS=$(echo "$STATS" | jq -r '.detectors.coral.inference_speed // "not_found"' 2>/dev/null || echo "error")
            if [ "$CORAL_STATUS" != "not_found" ] && [ "$CORAL_STATUS" != "error" ]; then
                echo -e "${GREEN}✓ Coral TPU detected (inference speed: ${CORAL_STATUS}ms)${NC}"
            else
                echo -e "${YELLOW}⚠ Coral TPU not detected${NC}"
            fi

            # Check cameras
            CAMERA_COUNT=$(echo "$STATS" | jq -r '.cameras | length' 2>/dev/null || echo "0")
            if [ "$CAMERA_COUNT" -gt 0 ]; then
                echo -e "${GREEN}✓ Frigate has $CAMERA_COUNT camera(s) configured${NC}"
            else
                echo -e "${YELLOW}⚠ No cameras configured${NC}"
            fi
        fi
    else
        echo -e "${RED}✗ Frigate API is not responding${NC}"
        echo "Check Frigate logs:"
        echo "  ssh root@$LXC_HOST 'pct exec $LXC_ID -- tail -50 /dev/shm/logs/frigate/current'"
    fi
else
    echo -e "${YELLOW}⚠ Could not determine container IP${NC}"
fi

echo ""
echo "========================================="
echo "Rollback Complete!"
echo "========================================="
echo ""
echo -e "${GREEN}✓ still-fawn Frigate LXC has been restored${NC}"
echo ""
echo "Container details:"
echo "  - Container ID: $LXC_ID"
echo "  - Host: $LXC_HOST"
echo "  - IP Address: ${CONTAINER_IP:-Unknown}"
echo "  - Frigate URL: ${FRIGATE_URL:-Unknown}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo ""
echo "1. Update Home Assistant to use still-fawn Frigate:"
echo "   - URL: http://$CONTAINER_IP:5000"
echo "   - Go to Settings → Devices & Services → Frigate"
echo "   - Click Configure and update the URL"
echo ""
echo "2. Verify cameras are working:"
echo "   - Open Frigate web UI: $FRIGATE_URL"
echo "   - Check live camera feeds"
echo "   - Verify Coral TPU detection is working"
echo ""
echo "3. Check Frigate logs if there are issues:"
echo "   ssh root@$LXC_HOST 'pct exec $LXC_ID -- tail -100 /dev/shm/logs/frigate/current'"
echo ""
echo "4. If you want to try K8s Frigate again later:"
echo "   - Fix the issues in K8s Frigate deployment"
echo "   - Run verify-frigate-k8s.sh to confirm it's working"
echo "   - Run shutdown-still-fawn-frigate.sh again"
echo ""
