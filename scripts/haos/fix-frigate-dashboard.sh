#!/bin/bash
# Fix Frigate dashboard card configuration - add frigate URL and camera_name
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HA_VM_ID="116"
HA_HOST="chief-horse.maas"
DASHBOARD_FILE="/mnt/data/supervisor/homeassistant/.storage/lovelace.dashboard_frigate"
FRIGATE_URL="http://192.168.4.82:5000"

echo "=== Fixing Frigate Dashboard Cards ==="
echo ""

# Step 1: Backup first
echo "1. Creating backup..."
"$SCRIPT_DIR/backup-dashboard.sh" lovelace.dashboard_frigate

echo ""
echo "2. Fetching current dashboard config..."
CURRENT=$(ssh -o StrictHostKeyChecking=no "root@$HA_HOST" "qm guest exec $HA_VM_ID -- cat $DASHBOARD_FILE" 2>/dev/null | jq -r '.["out-data"]')

if [[ -z "$CURRENT" || "$CURRENT" == "null" ]]; then
    echo "ERROR: Could not read dashboard config"
    exit 1
fi

echo "3. Updating camera cards with Frigate config..."

# Update the config using jq to add frigate block to each advanced-camera-card
UPDATED=$(echo "$CURRENT" | jq --arg url "$FRIGATE_URL" '
def fix_cameras:
  if .cameras then
    .cameras = [.cameras[] |
      if .camera_entity then
        . + {
          frigate: {
            url: $url,
            camera_name: (.camera_entity | split(".")[1])
          }
        }
      else
        .
      end
    ]
  else
    .
  end;

def walk_and_fix:
  if type == "object" then
    if .type == "custom:advanced-camera-card" then
      fix_cameras
    else
      with_entries(.value |= walk_and_fix)
    end
  elif type == "array" then
    map(walk_and_fix)
  else
    .
  end;

walk_and_fix
')

echo "4. Writing updated config to HAOS..."

# Write via a temp file approach
TEMP_FILE=$(mktemp)
echo "$UPDATED" > "$TEMP_FILE"

# Copy to Proxmox host then to VM
scp -o StrictHostKeyChecking=no "$TEMP_FILE" "root@$HA_HOST:/tmp/dashboard_fix.json" 2>/dev/null
ssh -o StrictHostKeyChecking=no "root@$HA_HOST" "qm guest exec $HA_VM_ID -- cp /tmp/dashboard_fix.json $DASHBOARD_FILE" 2>/dev/null

# Actually need to write content, not copy - qm guest exec doesn't support cp like that
# Use a different approach - write via stdin
ssh -o StrictHostKeyChecking=no "root@$HA_HOST" "cat /tmp/dashboard_fix.json | qm guest exec $HA_VM_ID --pass-stdin -- tee $DASHBOARD_FILE > /dev/null" 2>/dev/null

rm -f "$TEMP_FILE"

echo "5. Verifying update..."
VERIFY=$(ssh -o StrictHostKeyChecking=no "root@$HA_HOST" "qm guest exec $HA_VM_ID -- cat $DASHBOARD_FILE" 2>/dev/null | jq -r '.["out-data"]' | jq '.data.config.views[0].sections[0].cards[1].cameras[0].frigate.url // "not found"')

if [[ "$VERIFY" == "$FRIGATE_URL" ]]; then
    echo ""
    echo "✅ Dashboard updated successfully!"
    echo ""
    echo "Refresh the Frigate dashboard in HA (Ctrl+F5 or clear cache)"
else
    echo ""
    echo "⚠ Verification unclear. Please check manually."
    echo "Verify result: $VERIFY"
fi
