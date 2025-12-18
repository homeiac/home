#!/bin/bash
# Fetch Voice PE ESPHome YAML from HAOS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_YAML="$SCRIPT_DIR/voice-pe-config.yaml"

echo "=== Fetching Voice PE ESPHome config from HAOS ==="

# List available ESPHome configs
echo "1. Available ESPHome configs on HAOS:"
ssh root@chief-horse.maas "qm guest exec 116 -- ls -la /config/esphome/" 2>/dev/null | jq -r '."out-data"' | grep -E "\.yaml$" || echo "   (none found yet - adoption may still be in progress)"

echo ""
echo "2. Looking for Voice PE config..."

# Try common names
for name in "home-assistant-voice-09f5a3" "voice-pe" "home-assistant-voice" "esphome-voice"; do
    YAML_PATH="/config/esphome/${name}.yaml"
    RESULT=$(ssh root@chief-horse.maas "qm guest exec 116 -- cat '$YAML_PATH'" 2>/dev/null | jq -r '."out-data"' 2>/dev/null)
    if [[ -n "$RESULT" && "$RESULT" != "null" ]]; then
        echo "   Found: $YAML_PATH"
        echo "$RESULT" > "$LOCAL_YAML"
        echo ""
        echo "3. Saved to: $LOCAL_YAML"
        echo ""
        echo "Contents:"
        head -30 "$LOCAL_YAML"
        echo "..."
        exit 0
    fi
done

echo "   No Voice PE config found. Listing all configs:"
ssh root@chief-horse.maas "qm guest exec 116 -- ls /config/esphome/" 2>/dev/null | jq -r '."out-data"'

echo ""
echo "Once adoption completes, re-run this script or manually specify:"
echo "  ssh root@chief-horse.maas \"qm guest exec 116 -- cat /config/esphome/<device>.yaml\""
