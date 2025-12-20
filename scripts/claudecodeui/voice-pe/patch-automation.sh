#!/bin/bash
# Patch automation to use assist_satellite.start_conversation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HA_CONFIG="/mnt/data/supervisor/homeassistant"
PROXMOX_HOST="root@chief-horse.maas"
VMID=116
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== Patching Approval Automation ==="

# Step 1: Backup
echo "1. Backing up automations.yaml..."
ssh "$PROXMOX_HOST" "qm guest exec $VMID -- cp $HA_CONFIG/automations.yaml $HA_CONFIG/automations.yaml.pre-voice-approval-$TIMESTAMP" 2>/dev/null

# Step 2: Get current file
echo "2. Downloading automations.yaml..."
ssh "$PROXMOX_HOST" "qm guest exec $VMID -- cat $HA_CONFIG/automations.yaml" 2>/dev/null | \
    jq -r '.["out-data"]' > /tmp/ha-automations-original.yaml

# Step 3: Find and replace the tts.speak section in approval_request
# The current pattern is:
#   - target:
#       entity_id: tts.piper
#     data:
#       media_player_entity_id: media_player.home_assistant_voice_09f5a3_media_player
#       message: Run {{ trigger.payload_json.input.command | default('this command') | truncate(50) }}?
#     action: tts.speak
#
# Replace with:
#   - target:
#       entity_id: assist_satellite.home_assistant_voice_09f5a3_assist_satellite
#     data:
#       start_message: '{{ trigger.payload_json.message | default("Approve this action?") }}'
#     action: assist_satellite.start_conversation

echo "3. Patching automation..."
cat /tmp/ha-automations-original.yaml | python3 -c "
import sys
import re

content = sys.stdin.read()

# Pattern to find the tts.speak block in approval_request context
old_pattern = r'''- target:
          entity_id: tts\.piper
        data:
          media_player_entity_id: media_player\.home_assistant_voice_09f5a3_media_player
          message: Run \{\{ trigger\.payload_json\.input\.command \| default\('this command'\)
            \| truncate\(50\) \}\}\?
        action: tts\.speak'''

new_block = '''- target:
          entity_id: assist_satellite.home_assistant_voice_09f5a3_assist_satellite
        data:
          start_message: '{{ trigger.payload_json.message | default(\"Approve this action?\") }}'
        action: assist_satellite.start_conversation'''

# Try the replacement
new_content = re.sub(old_pattern, new_block, content, flags=re.MULTILINE)

if new_content == content:
    print('WARNING: Pattern not found, trying simpler replacement', file=sys.stderr)
    # Try simpler pattern
    old_simple = 'action: tts.speak'
    # Only replace the first occurrence in approval context
    # This is fragile - better to do manual edit
    print(content)
else:
    print(new_content)
" > /tmp/ha-automations-patched.yaml

# Step 4: Check if patch worked
if diff -q /tmp/ha-automations-original.yaml /tmp/ha-automations-patched.yaml > /dev/null 2>&1; then
    echo "   WARNING: No changes made - pattern may not match"
    echo "   Manual edit required in HA UI"
    exit 1
fi

echo "4. Uploading patched automation..."
cat /tmp/ha-automations-patched.yaml | ssh "$PROXMOX_HOST" "qm guest exec $VMID -- tee $HA_CONFIG/automations.yaml" 2>/dev/null | jq -r '.exitcode'

echo ""
echo "=== Patch complete ==="
echo "Backup: automations.yaml.pre-voice-approval-$TIMESTAMP"
echo ""
echo "Restart HA to apply: scripts/haos/restart-ha.sh"
