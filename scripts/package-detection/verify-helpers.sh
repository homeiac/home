#!/bin/bash
# Verify notification helpers are created and working

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "═══════════════════════════════════════════════════════"
echo "  Verifying Notification Helpers"
echo "═══════════════════════════════════════════════════════"
echo ""

echo "1️⃣  Checking HA config validation..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/core/check_config" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print('   Result:', d.get('result'), '- Errors:', d.get('errors'))"

echo ""
echo "2️⃣  Listing all input_* entities..."
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | python3 -c "
import sys, json
states = json.load(sys.stdin)
found = False
for s in states:
    if s['entity_id'].startswith('input_'):
        print(f\"   {s['entity_id']}: {s['state']}\")
        found = True
if not found:
    print('   No input_* entities found')
"

echo ""
echo "3️⃣  Checking required helpers..."
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | python3 -c "
import sys, json
states = json.load(sys.stdin)
helpers = [
    'input_boolean.has_pending_notification',
    'input_text.pending_notification_message',
    'input_text.pending_notification_type'
]
for h in helpers:
    found = any(s['entity_id'] == h for s in states)
    status = '✅' if found else '❌'
    print(f'   {status} {h}')
"

echo ""
echo "4️⃣  Checking HA logs for input_text errors..."
ssh root@chief-horse.maas 'qm guest exec 116 -- tail -50 /mnt/data/supervisor/homeassistant/home-assistant.log' 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); lines=d.get('out-data','').split('\n'); [print('   '+l) for l in lines if 'input_text' in l.lower() or 'error' in l.lower()]" 2>/dev/null

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Done"
echo "═══════════════════════════════════════════════════════"
echo ""
