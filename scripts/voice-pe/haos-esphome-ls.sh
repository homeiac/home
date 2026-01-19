#!/bin/bash
# List files in ESPHome addon in HAOS via docker exec
# Usage: ./haos-esphome-ls.sh [path]
# Example: ./haos-esphome-ls.sh /config/esphome
set -e

DIR_PATH="${1:-/config/esphome}"

ssh root@chief-horse.maas "qm guest exec 116 -- docker exec addon_5c53de3b_esphome ls -la '$DIR_PATH'" 2>/dev/null | \
    python3 -c "import sys, json; print(json.load(sys.stdin).get('out-data', ''))"
