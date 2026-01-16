#!/bin/bash
# Get automation config by ID
source "$(dirname "$0")/../lib-sh/ha-api.sh"

AUTOMATION_ID="${1:?Usage: $0 <automation_id_without_prefix>}"
ha_api_get "config/automation/config/$AUTOMATION_ID" | jq '.'
