#!/bin/bash
#
# reboot-still-fawn.sh
#
# Safely reboot still-fawn Proxmox host
# Waits for host to come back up and verifies it's healthy
#

set -euo pipefail

HOST="still-fawn.maas"
TIMEOUT_SECONDS=300
CHECK_INTERVAL=10

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Reboot still-fawn"
echo "========================================="
echo ""
echo "Host: $HOST"
echo "Timeout: ${TIMEOUT_SECONDS}s"
echo ""

# Step 1: Verify host is reachable
echo "Step 1: Checking host is reachable..."
if ! ssh -o ConnectTimeout=5 root@$HOST "uptime" &>/dev/null; then
    echo -e "${RED}Host $HOST is not reachable${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Host is reachable${NC}"
echo ""

# Step 2: Initiate reboot
echo "Step 2: Initiating reboot..."
ssh root@$HOST "reboot" &>/dev/null || true
echo "Reboot command sent"
echo ""

# Step 3: Wait for host to go down
echo "Step 3: Waiting for host to go down..."
sleep 5
for i in {1..10}; do
    if ! ping -c 1 -W 2 $HOST &>/dev/null; then
        echo -e "${GREEN}✓ Host is down${NC}"
        break
    fi
    echo "  Still up... ($i/10)"
    sleep 2
done
echo ""

# Step 4: Wait for host to come back
echo "Step 4: Waiting for host to come back up..."
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT_SECONDS ]; do
    if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@$HOST "uptime" &>/dev/null; then
        echo ""
        echo -e "${GREEN}✓ Host is back up!${NC}"
        break
    fi
    echo "  Waiting... (${ELAPSED}s / ${TIMEOUT_SECONDS}s)"
    sleep $CHECK_INTERVAL
    ELAPSED=$((ELAPSED + CHECK_INTERVAL))
done

if [ $ELAPSED -ge $TIMEOUT_SECONDS ]; then
    echo -e "${RED}✗ Timeout waiting for host to come back${NC}"
    exit 1
fi
echo ""

# Step 5: Verify host health
echo "Step 5: Verifying host health..."
ssh root@$HOST "uptime && df -h / && pveversion"
echo ""

echo "========================================="
echo -e "${GREEN}Reboot complete!${NC}"
echo "========================================="
