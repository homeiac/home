#!/bin/bash
# Frigate Coral LXC - Verify Frigate API
# GitHub Issue: #168
# Checks that Frigate is responding

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Verify Frigate API ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

if [[ -z "$VMID" ]]; then
    echo "❌ ERROR: VMID not set in config.env"
    exit 1
fi

echo "Container VMID: $VMID"
echo ""

echo "1. Checking container status..."
STATUS=$(ssh root@"$PVE_HOST" "pct status $VMID")
echo "   $STATUS"

if ! echo "$STATUS" | grep -q "running"; then
    echo "   ❌ Container is not running"
    exit 1
fi

echo ""
echo "2. Waiting for Frigate to initialize (30 seconds)..."
sleep 30

echo ""
echo "3. Checking Frigate API version..."
VERSION=$(ssh root@"$PVE_HOST" "pct exec $VMID -- curl -s http://127.0.0.1:5000/api/version 2>/dev/null" || echo "FAILED")

if [[ "$VERSION" == "FAILED" ]] || [[ -z "$VERSION" ]]; then
    echo "   ❌ Frigate API not responding"
    echo ""
    echo "   Checking Frigate service status..."
    ssh root@"$PVE_HOST" "pct exec $VMID -- supervisorctl status frigate 2>/dev/null" || echo "   Could not check service"
    exit 1
fi

echo "   ✅ Frigate version: $VERSION"

echo ""
echo "=== Frigate API Verification Complete ==="
echo ""
echo "NEXT: Run 33-verify-coral-detection.sh to check Coral TPU"
