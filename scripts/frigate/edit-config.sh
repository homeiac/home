#!/bin/bash
# Safe Frigate config editor with backup/restore
# Uses copy-edit-copy-back pattern to prevent data loss
#
# Usage:
#   ./edit-config.sh                           # Interactive editor
#   ./edit-config.sh --sed 's/old/new/'        # Apply sed command
#   ./edit-config.sh --sed 's/threshold: 20/threshold: 50/' --apply
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/../k3s/doorbell-analysis"
NAMESPACE="frigate"
POD_CONFIG_PATH="/config/config.yml"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/config-backup-$TIMESTAMP.yml"
TEMP_ORIGINAL=$(mktemp)
TEMP_EDITED=$(mktemp)

# Parse arguments
SED_CMD=""
AUTO_APPLY=false
NO_RESTART=false
DOORBELL_HOST=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --sed) SED_CMD="$2"; shift 2 ;;
        --apply) AUTO_APPLY=true; shift ;;
        --no-restart) NO_RESTART=true; shift ;;
        --set-doorbell-host) DOORBELL_HOST="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Ensure KUBECONFIG is set
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

cleanup() {
    rm -f "$TEMP_ORIGINAL" "$TEMP_EDITED"
}
trap cleanup EXIT

get_pod() {
    kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

echo "=== Frigate Config Editor ==="
echo ""

# Get pod name
POD=$(get_pod)
if [[ -z "$POD" ]]; then
    echo "ERROR: No Frigate pod found in namespace $NAMESPACE"
    exit 1
fi
echo "Pod: $POD"

# Step 1: Download current config
echo ""
echo "Step 1: Downloading current config..."
kubectl exec -n "$NAMESPACE" "$POD" -- cat "$POD_CONFIG_PATH" > "$TEMP_ORIGINAL"
cp "$TEMP_ORIGINAL" "$TEMP_EDITED"
echo "Downloaded $(wc -l < "$TEMP_ORIGINAL" | tr -d ' ') lines"

# Step 2: Create backup
echo ""
echo "Step 2: Creating backup..."
mkdir -p "$BACKUP_DIR"
cp "$TEMP_ORIGINAL" "$BACKUP_FILE"
echo "Backup saved: $BACKUP_FILE"

# Step 3: Edit (interactive, sed, or targeted change)
echo ""
if [[ -n "$DOORBELL_HOST" ]]; then
    echo "Step 3: Updating doorbell host to: $DOORBELL_HOST"
    # Use python for precise YAML manipulation - only change go2rtc reolink_doorbell stream
    # Use helper script for precise doorbell host replacement
    python3 "$SCRIPT_DIR/helpers/replace_doorbell_host.py" "$TEMP_EDITED" "$DOORBELL_HOST"
elif [[ -n "$SED_CMD" ]]; then
    echo "Step 3: Applying sed command: $SED_CMD"
    echo "WARNING: sed is dangerous - consider using --set-doorbell-host instead"
    sed -i '' "$SED_CMD" "$TEMP_EDITED"
else
    echo "Step 3: Opening editor..."
    EDITOR="${EDITOR:-vim}"
    $EDITOR "$TEMP_EDITED"
fi

# Step 4: Check if changed
if diff -q "$TEMP_ORIGINAL" "$TEMP_EDITED" > /dev/null 2>&1; then
    echo ""
    echo "No changes made. Exiting."
    exit 0
fi

# Step 5: Validate YAML
echo ""
echo "Step 4: Validating YAML syntax..."
if ! python3 -c "import yaml; yaml.safe_load(open('$TEMP_EDITED'))" 2>/dev/null; then
    echo "ERROR: Invalid YAML syntax!"
    echo "Your changes are saved at: $TEMP_EDITED"
    echo "Fix the syntax and try again."
    exit 1
fi
echo "YAML syntax OK"

# Step 6: Show diff
echo ""
echo "Step 5: Changes to apply:"
echo "----------------------------------------"
diff --color=auto "$TEMP_ORIGINAL" "$TEMP_EDITED" || true
echo "----------------------------------------"

# Step 7: Confirm
echo ""
if [[ "$AUTO_APPLY" == "true" ]]; then
    echo "Auto-applying changes (--apply flag)"
else
    read -p "Apply these changes? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted. No changes applied."
        echo "Your edits saved at: $TEMP_EDITED"
        exit 0
    fi
fi

# Step 8: Upload
echo ""
echo "Step 6: Uploading config to pod..."
kubectl cp "$TEMP_EDITED" "$NAMESPACE/$POD:$POD_CONFIG_PATH"
echo "Config uploaded successfully"

# Step 9: Restart prompt
echo ""
if [[ "$NO_RESTART" == "true" ]]; then
    echo "Skipped restart (--no-restart flag). Changes apply on next Frigate restart."
elif [[ "$AUTO_APPLY" == "true" ]]; then
    echo "Restarting Frigate..."
    kubectl rollout restart deployment/frigate -n "$NAMESPACE"
    echo "Restart initiated. Watch with: kubectl get pods -n frigate -w"
else
    read -p "Restart Frigate to apply changes? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Restarting Frigate..."
        kubectl rollout restart deployment/frigate -n "$NAMESPACE"
        echo "Restart initiated. Watch with: kubectl get pods -n frigate -w"
    else
        echo "Skipped restart. Changes will apply on next Frigate restart."
    fi
fi

echo ""
echo "=== Done ==="
echo "Backup: $BACKUP_FILE"
echo "Rollback: kubectl cp $BACKUP_FILE $NAMESPACE/$POD:$POD_CONFIG_PATH"
