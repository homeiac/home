#!/bin/bash
# Camera IP Sync Script
# Run from HAOS to discover camera IPs and update Frigate ConfigMap
#
# This script:
# 1. Uses nmap to scan for cameras by MAC address
# 2. Compares to current Frigate config
# 3. Updates ConfigMap if IPs changed
# 4. Triggers Frigate restart
#
# Known camera MACs (found via nmap from HAOS):
#   Hall:        0C:79:55:4B:D4:2A
#   Living Room: 14:EA:63:A9:04:08
#
# Usage:
#   Run via HA shell_command or as a cron job in HAOS
#   docker exec homeassistant /config/scripts/camera-ip-sync.sh

set -e

# Configuration
HALL_MAC="0C:79:55:4B:D4:2A"
LIVING_ROOM_MAC="14:EA:63:A9:04:08"
SCAN_RANGE="192.168.1.0/24"
FRIGATE_API="http://frigate.frigate.svc.cluster.local:5000"  # Adjust if needed
WEBHOOK_URL="http://frigate-ip-webhook.frigate.svc.cluster.local:8080/update"

echo "=== Camera IP Discovery ==="
echo "Scanning $SCAN_RANGE..."

# Run nmap scan
SCAN_OUTPUT=$(nmap -sn "$SCAN_RANGE" -oG - 2>/dev/null)

# Extract IPs by MAC
HALL_IP=$(echo "$SCAN_OUTPUT" | grep -i "${HALL_MAC//:/-}\|${HALL_MAC}" | grep -oE '192\.168\.1\.[0-9]+' | head -1)
LIVING_IP=$(echo "$SCAN_OUTPUT" | grep -i "${LIVING_ROOM_MAC//:/-}\|${LIVING_ROOM_MAC}" | grep -oE '192\.168\.1\.[0-9]+' | head -1)

# Alternative: parse nmap output format
if [ -z "$HALL_IP" ]; then
    # Try parsing standard nmap output
    HALL_IP=$(nmap -sn "$SCAN_RANGE" 2>/dev/null | grep -B2 -i "0C:79:55" | grep "Nmap scan report" | grep -oE '192\.168\.1\.[0-9]+')
fi
if [ -z "$LIVING_IP" ]; then
    LIVING_IP=$(nmap -sn "$SCAN_RANGE" 2>/dev/null | grep -B2 -i "14:EA:63" | grep "Nmap scan report" | grep -oE '192\.168\.1\.[0-9]+')
fi

echo "Found:"
echo "  Hall: ${HALL_IP:-NOT FOUND}"
echo "  Living Room: ${LIVING_IP:-NOT FOUND}"

if [ -z "$HALL_IP" ] || [ -z "$LIVING_IP" ]; then
    echo "ERROR: Could not find both cameras"
    exit 1
fi

# Call webhook to update Frigate ConfigMap
echo ""
echo "Calling webhook to update Frigate..."
RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d "{\"hall\": \"$HALL_IP\", \"living_room\": \"$LIVING_IP\"}" \
    "$WEBHOOK_URL" 2>&1) || true

echo "Response: $RESPONSE"
echo "Done."
