#!/bin/bash
# Check HA config API capabilities
source "$(dirname "$0")/../lib-sh/ha-api.sh"

echo "=== HA Config Endpoints ==="

echo "1. Check /api/config:"
ha_api_get "config" | jq '{config_dir, allowlist_external_dirs, allowlist_external_urls}' 2>/dev/null

echo ""
echo "2. Check for file upload API:"
ha_api_get "services" | jq -r '.[].domain' | grep -E "file|config|hassio" | sort -u

echo ""
echo "3. Check hassio addon for SSH/Terminal:"
for addon in "core_ssh" "a0d7b954_ssh" "core_terminal" "a0d7b954_terminal" "core_configurator"; do
    RESULT=$(ha_api_get "hassio/addons/$addon/info" 2>/dev/null) || continue
    if echo "$RESULT" | jq -e '.data.name' > /dev/null 2>&1; then
        echo "   FOUND: $addon"
        echo "$RESULT" | jq '{name: .data.name, state: .data.state}'
    fi
done
