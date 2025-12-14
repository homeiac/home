#!/bin/bash
# Analyze doorbell motion detection - collect snapshots and motion debug images
# Usage: ./doorbell-motion-analysis.sh [num_samples] [interval_seconds]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/doorbell-analysis"
NUM_SAMPLES="${1:-5}"
INTERVAL="${2:-2}"

mkdir -p "$OUTPUT_DIR"

echo "=== Doorbell Motion Analysis ==="
echo "Collecting $NUM_SAMPLES samples, ${INTERVAL}s apart"
echo "Output: $OUTPUT_DIR"
echo ""

# Get the motion mask config
echo "--- Motion Mask Config ---"
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate --request-timeout=10s -- \
    cat /config/config.yml 2>/dev/null | grep -A10 "reolink_doorbell:" | grep -A5 "motion:" | tee "$OUTPUT_DIR/motion-config.txt"
echo ""

# Collect snapshots and motion debug images
for i in $(seq 1 "$NUM_SAMPLES"); do
    TIMESTAMP=$(date '+%H%M%S')
    echo "[$i/$NUM_SAMPLES] Capturing at $TIMESTAMP..."

    # Latest snapshot
    KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate --request-timeout=10s -- \
        curl -s "http://localhost:5000/api/reolink_doorbell/latest.jpg" 2>/dev/null \
        > "$OUTPUT_DIR/snapshot-$TIMESTAMP.jpg"

    # Motion debug image (shows motion regions)
    KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate --request-timeout=10s -- \
        curl -s "http://localhost:5000/api/reolink_doorbell/latest.jpg?debug=motion" 2>/dev/null \
        > "$OUTPUT_DIR/motion-$TIMESTAMP.jpg" || echo "  (motion debug not available)"

    # Get current detection stats
    STATS=$(KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate --request-timeout=10s -- \
        curl -s "http://localhost:5000/api/stats" 2>/dev/null)
    DET_FPS=$(echo "$STATS" | jq -r '.cameras.reolink_doorbell.detection_fps // "N/A"')
    echo "  Detection FPS: $DET_FPS"

    [[ $i -lt $NUM_SAMPLES ]] && sleep "$INTERVAL"
done

echo ""
echo "--- Collected Files ---"
ls -la "$OUTPUT_DIR"/*.jpg 2>/dev/null | tail -20

echo ""
echo "View images: open $OUTPUT_DIR"
