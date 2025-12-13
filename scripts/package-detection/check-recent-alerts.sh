#!/bin/bash
# Check recent package detection activity (last 10 minutes)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

# Get timestamp for 10 minutes ago
TEN_MIN_AGO=$(date -u -v-10M +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d '10 minutes ago' +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null)

echo "=== Recent Package Detection Activity (last 10 min) ==="
echo "Checking from: $TEN_MIN_AGO"
echo ""

# Check logbook
echo "--- Logbook Entries ---"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/logbook/$TEN_MIN_AGO" 2>/dev/null | \
    jq -r '.[] | select(.name | test("Package|Delivery|Doorbell|person"; "i")) | "\(.when): \(.name) - \(.message // .state)"' 2>/dev/null | tail -20

echo ""
echo "--- Current Automation Config Version ---"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/config/automation/config/package_delivery_detection" 2>/dev/null | \
    jq -r '.description // "unknown"'

echo ""
echo "--- Person Sensor Current State ---"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/binary_sensor.reolink_video_doorbell_wifi_person" 2>/dev/null | \
    jq -r '"State: \(.state) | Last changed: \(.last_changed)"'
