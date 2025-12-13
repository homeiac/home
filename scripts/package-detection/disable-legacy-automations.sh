#!/bin/bash
# Disable the legacy LLM Vision automations that spam on every motion

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "=== Disabling Legacy LLM Vision Automations ==="
echo ""

echo "[1/2] Disabling automation.llm_vision..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "automation.llm_vision"}' \
    "$HA_URL/api/services/automation/turn_off" > /dev/null
echo "      Done"

echo "[2/2] Disabling automation.ai_event_summary_v1_5_0..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "automation.ai_event_summary_v1_5_0"}' \
    "$HA_URL/api/services/automation/turn_off" > /dev/null
echo "      Done"

echo ""
echo "=== Verifying ==="
echo ""
echo "automation.llm_vision:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/automation.llm_vision" | jq -r '"  state: \(.state)"'

echo "automation.ai_event_summary_v1_5_0:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/automation.ai_event_summary_v1_5_0" | jq -r '"  state: \(.state)"'

echo ""
echo "=== Complete ==="
echo "Only automation.package_delivery_detection (v3) remains active."
echo "It will only alert when a package is detected."
