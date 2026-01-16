#!/bin/bash
# List services for a specific domain
# Usage: list-domain-services.sh <domain>
# Examples: list-domain-services.sh light
#           list-domain-services.sh esphome

source "$(dirname "$0")/../lib-sh/ha-api.sh"

DOMAIN="${1:?Usage: $0 <domain>}"

echo "=== Services for $DOMAIN ==="
ha_list_domain_services "$DOMAIN"
