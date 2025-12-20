#!/bin/bash
# Reload ESPHome config entry to force HA reconnection after firmware update
# This is REQUIRED after flashing new firmware with API actions
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"
ENTRY_ID="01KBR6935BVYK5EX7PF6D4QYEY"  # Voice PE ESPHome entry

echo "=== Reloading ESPHome config entry ==="
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"entry_id\": \"$ENTRY_ID\"}" \
  "$HA_URL/api/services/homeassistant/reload_config_entry"

echo ""
echo "Done. Wait 10-15 seconds for reconnection before testing API actions."
