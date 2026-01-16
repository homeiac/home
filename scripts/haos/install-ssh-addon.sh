#!/bin/bash
# Install SSH addon in HAOS
source "$(dirname "$0")/../lib-sh/ha-api.sh"

echo "=== Installing SSH & Web Terminal addon ==="
ha_api_post "hassio/addons/a0d7b954_ssh/install" "{}" | jq '.'

echo ""
echo "If successful, configure with authorized_keys and start the addon"
