#!/bin/bash
# Create HA intents for voice approval (yes/no)
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }

HA_URL="${HA_URL:-http://192.168.1.122:8123}"

echo "=== Creating custom sentences for voice approval ==="

# Check if custom_sentences directory exists
echo "Checking HA config structure..."

# Create the custom sentences YAML
cat << 'SENTENCES' > /tmp/voice_approval_sentences.yaml
# Voice approval intents for ClaudeCodeUI
# Place in config/custom_sentences/en/voice_approval.yaml

language: "en"
intents:
  ApproveClaudeAction:
    data:
      - sentences:
          - "yes"
          - "approve"
          - "do it"
          - "go ahead"
          - "confirmed"
          - "yep"
          - "yeah"
  RejectClaudeAction:
    data:
      - sentences:
          - "no"
          - "reject"
          - "cancel"
          - "stop"
          - "don't do that"
          - "nope"
          - "negative"
SENTENCES

echo "Custom sentences YAML created at /tmp/voice_approval_sentences.yaml"
echo ""
echo "=== Next steps ==="
echo "1. Copy to HA: scp /tmp/voice_approval_sentences.yaml root@homeassistant.maas:/config/custom_sentences/en/"
echo "2. Create intent scripts in HA to handle ApproveClaudeAction and RejectClaudeAction"
echo "3. Guard intents with input_boolean.claude_awaiting_approval"
echo ""
echo "Testing phrase recognition..."
# We can't directly test Whisper, but we can check if assist pipeline is configured
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config" | jq -r '.components[]' | grep -E "^(assist|conversation|whisper)" || echo "Assist components not found"
