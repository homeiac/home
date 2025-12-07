#!/bin/bash
# Test HA Notifications
# Usage: ./test-notification.sh [service_name|all]
# Examples:
#   ./test-notification.sh                    # Test persistent_notification
#   ./test-notification.sh mobile_app_pixel_10_pro  # Test specific phone
#   ./test-notification.sh all                # Test ALL notification services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

# Function to send notification
send_notify() {
    local SERVICE="$1"
    local MSG="$2"

    RESPONSE=$(curl -s -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"message\": \"$MSG\", \"title\": \"Test from Claude\"}" \
        "$HA_URL/api/services/notify/$SERVICE" 2>&1)

    if [[ -z "$RESPONSE" ]] || echo "$RESPONSE" | grep -q "^\[\]$"; then
        echo "   ✅ notify.$SERVICE - sent"
        return 0
    else
        echo "   ❌ notify.$SERVICE - failed: $RESPONSE"
        return 1
    fi
}

# List available services
list_services() {
    curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/services" | \
        python3 -c "
import sys,json
d = json.load(sys.stdin)
for s in d:
    if s['domain'] == 'notify':
        for k in s['services'].keys():
            print(k)
" 2>/dev/null
}

echo "═══════════════════════════════════════════════════════"
echo "  Notification Test"
echo "═══════════════════════════════════════════════════════"
echo ""

if [[ "$1" == "all" ]]; then
    echo "Testing ALL notification services..."
    echo ""

    for SERVICE in $(list_services); do
        send_notify "$SERVICE" "Test: $SERVICE ($(date +%H:%M:%S))"
    done

    echo ""
    echo "Check:"
    echo "  • Both phones for push notifications"
    echo "  • HA UI bell icon for persistent_notification"

elif [[ -n "$1" ]]; then
    echo "Testing: notify.$1"
    echo ""
    send_notify "$1" "Package detection test ($(date +%H:%M:%S))"

else
    echo "Available notification services:"
    for SERVICE in $(list_services); do
        echo "  • notify.$SERVICE"
    done
    echo ""
    echo "Usage:"
    echo "  ./test-notification.sh <service>  - Test specific service"
    echo "  ./test-notification.sh all        - Test all services"
fi

echo ""
