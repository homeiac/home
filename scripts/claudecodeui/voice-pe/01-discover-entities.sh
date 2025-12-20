#!/bin/bash
# Discover what Voice PE exposes to HA
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

echo "=== Voice PE Entities in HA ==="
echo ""

echo "1. All entities with 'voice' or '09f5a3' in name:"
curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" \
    "http://192.168.1.122:8123/api/states" 2>/dev/null | \
    jq -r '.[] | select(.entity_id | test("voice|09f5a3"; "i")) | "\(.entity_id): \(.state)"'

echo ""
echo "2. Light entities (for LED ring):"
curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" \
    "http://192.168.1.122:8123/api/states" 2>/dev/null | \
    jq -r '.[] | select(.entity_id | test("light.*09f5a3"; "i")) | .entity_id'

echo ""
echo "3. Binary sensors (buttons/switches):"
curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" \
    "http://192.168.1.122:8123/api/states" 2>/dev/null | \
    jq -r '.[] | select(.entity_id | test("binary_sensor.*09f5a3"; "i")) | "\(.entity_id): \(.state)"'

echo ""
echo "4. Sensors (may include dial/encoder):"
curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" \
    "http://192.168.1.122:8123/api/states" 2>/dev/null | \
    jq -r '.[] | select(.entity_id | test("sensor.*09f5a3"; "i")) | "\(.entity_id): \(.state)"'
