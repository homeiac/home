#!/bin/bash
# Export Frigate config and extract zone coordinates for doorbell camera
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/doorbell-analysis"
mkdir -p "$OUTPUT_DIR"

echo "=== Exporting Frigate Config ==="

# Export current config
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- cat /config/config.yml > "$OUTPUT_DIR/frigate-config-current.yml"

echo "Config saved to: $OUTPUT_DIR/frigate-config-current.yml"
echo ""
echo "--- reolink_doorbell zone config ---"
grep -A20 "reolink_doorbell:" "$OUTPUT_DIR/frigate-config-current.yml" | grep -A10 "zones:" | head -15
