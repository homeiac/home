#!/bin/bash
# Read file from ESPHome addon in HAOS via docker exec
# Usage: ./haos-esphome-cat.sh <path-in-esphome-container>
# Example: ./haos-esphome-cat.sh /config/esphome/home-assistant-voice-09f5a3.yaml
set -e

FILE_PATH="${1:-/config/esphome/home-assistant-voice-09f5a3.yaml}"

ssh root@chief-horse.maas "qm guest exec 116 -- docker exec addon_5c53de3b_esphome cat '$FILE_PATH'" 2>/dev/null | \
    python3 -c "import sys, json; print(json.load(sys.stdin).get('out-data', ''))"
