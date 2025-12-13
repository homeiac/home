#!/bin/bash
# Check current state of Ollama prompt after update attempt

set -e

echo "========================================================"
echo "  Checking Ollama Prompt State"
echo "========================================================"
echo ""

echo "1. Current prompt in storage file..."
timeout 30 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@chief-horse.maas \
    "qm guest exec 116 -- cat /mnt/data/supervisor/homeassistant/.storage/core.config_entries 2>/dev/null" 2>/dev/null | \
    jq -r '."out-data" // .' 2>/dev/null | \
    jq -r '.data.entries[] | select(.domain == "ollama") | .subentries[0].data.prompt' 2>/dev/null

echo ""
echo "========================================================"
