#!/bin/bash
# Read a .storage file from HAOS VM
# Usage: read-ha-storage.sh <filename> [jq_filter]
#
# Examples:
#   read-ha-storage.sh core.config_entries                           # full file
#   read-ha-storage.sh core.config_entries '.data.entries[] | select(.domain == "ollama")'
#   read-ha-storage.sh core.entity_registry '.data.entities[] | select(.platform == "ollama")'

source "$(dirname "$0")/../lib-sh/ha-api.sh"

STORAGE_FILE="${1:?Usage: $0 <filename> [jq_filter]}"
JQ_FILTER="${2:-.}"

STORAGE_PATH="/config/.storage/$STORAGE_FILE"

echo "Reading $STORAGE_PATH from HAOS..." >&2
# HAOS runs HA inside a Docker container - must use docker exec
RAW=$(ssh root@chief-horse.maas "qm guest exec 116 -- docker exec homeassistant cat $STORAGE_PATH" 2>/dev/null)

# Extract the out-data field from qm guest exec JSON output
echo "$RAW" | python3 -c "
import json, sys
raw = sys.stdin.read()
try:
    outer = json.loads(raw)
    content = outer.get('out-data', raw)
    data = json.loads(content)
    print(json.dumps(data))
except json.JSONDecodeError:
    # Try extracting out-data with string parsing if JSON fails
    print(raw)
" | jq "$JQ_FILTER"
