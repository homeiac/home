#!/bin/bash
# Reload a HA integration/domain
# Usage: reload-integration.sh <domain>
# Examples: reload-integration.sh script
#           reload-integration.sh automation

source "$(dirname "$0")/../lib-sh/ha-api.sh"

DOMAIN="${1:?Usage: $0 <domain>}"

echo "Reloading: $DOMAIN"
ha_reload "$DOMAIN" >/dev/null
echo "Done."
