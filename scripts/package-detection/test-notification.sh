#!/bin/bash
# Test HA Companion App Notification
# Usage: ./test-notification.sh [service_name]
# Default: notify.mobile_app_iphone (or notify.my_phone if specified)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

# Load HA_TOKEN from .env
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
else
    echo "ERROR: .env file not found at $ENV_FILE"
    exit 1
fi

HA_URL="http://192.168.4.240:8123"
NOTIFY_SERVICE="${1:-persistent_notification}"

echo "Testing notification via: $NOTIFY_SERVICE"

# Send test notification
RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message": "Package detection test - if you see this, notifications work!", "title": "Test from Claude"}' \
    "$HA_URL/api/services/notify/$NOTIFY_SERVICE" 2>&1)

if [[ -z "$RESPONSE" ]] || echo "$RESPONSE" | grep -q "^\[\]$"; then
    echo "✅ Notification sent successfully via notify.$NOTIFY_SERVICE"
else
    echo "Response: $RESPONSE"
    if echo "$RESPONSE" | grep -qi "error\|not found"; then
        echo "❌ Notification failed"
        echo ""
        echo "Available notify services:"
        curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/services" | \
            python3 -c "import sys,json; d=json.load(sys.stdin); [print('  - notify.' + k) for s in d if s['domain']=='notify' for k in s['services'].keys()]" 2>/dev/null
    else
        echo "✅ Notification likely sent"
    fi
fi
