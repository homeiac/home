#!/bin/bash
# List all camera entities in Home Assistant

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "=== Camera Entities ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    python3 -c "
import sys, json
d = json.load(sys.stdin)
cameras = [e for e in d if e['entity_id'].startswith('camera.')]
print(f'Found {len(cameras)} camera entities:')
for c in cameras:
    print(f'  - {c[\"entity_id\"]}')
"

echo ""
echo "=== Image Entities (for Frigate snapshots) ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    python3 -c "
import sys, json
d = json.load(sys.stdin)
images = [e for e in d if e['entity_id'].startswith('image.')]
print(f'Found {len(images)} image entities:')
for i in images:
    print(f'  - {i[\"entity_id\"]}')
"

echo ""
echo "=== Binary Sensors (motion detection) ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    python3 -c "
import sys, json
d = json.load(sys.stdin)
motion = [e for e in d if 'motion' in e['entity_id'].lower() or 'person' in e['entity_id'].lower() or 'frigate' in e['entity_id'].lower()]
print(f'Found {len(motion)} motion/frigate entities:')
for m in sorted(motion, key=lambda x: x['entity_id'])[:30]:
    print(f'  - {m[\"entity_id\"]}: {m.get(\"state\", \"unknown\")}')
"
