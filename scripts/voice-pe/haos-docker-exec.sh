#!/bin/bash
# Run command in HAOS docker container
# Usage: ./haos-docker-exec.sh <container> <command>
# Example: ./haos-docker-exec.sh addon_5c53de3b_esphome "ls /config"
set -e

CONTAINER="${1:-addon_5c53de3b_esphome}"
COMMAND="$2"

if [[ -z "$COMMAND" ]]; then
    echo "Usage: $0 <container> <command>"
    echo "Example: $0 addon_5c53de3b_esphome 'ls /config/esphome'"
    echo ""
    echo "Common containers:"
    echo "  addon_5c53de3b_esphome  - ESPHome addon"
    exit 1
fi

RESULT=$(ssh root@chief-horse.maas "qm guest exec 116 -- docker exec $CONTAINER sh -c '$COMMAND'" 2>/dev/null)

# Parse JSON output
echo "$RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if 'out-data' in data:
        print(data['out-data'], end='')
    if 'err-data' in data and data['err-data']:
        print(data['err-data'], file=sys.stderr, end='')
    sys.exit(data.get('exitcode', 0))
except:
    print(sys.stdin.read())
"
