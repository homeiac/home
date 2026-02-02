#!/bin/bash
# create-homelab-env-secret.sh - Read .env and create SOPS-encrypted K8s Secret
# Contains all homelab credentials for Claude Code UI pod to manage infrastructure
# Usage: ./scripts/claudecodeui/create-homelab-env-secret.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$REPO_ROOT/proxmox/homelab/.env"
SECRET_DIR="$REPO_ROOT/gitops/clusters/homelab/apps/claudecodeui/blue/secrets"
SECRET_FILE="$SECRET_DIR/homelab-env.sops.yaml"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "=== Claude Code UI: Homelab Environment Secret ==="
echo ""

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env file not found at $ENV_FILE"
    exit 1
fi

# Keys to extract from .env (credential/secret keys only)
KEYS=(
    # Home Assistant
    HA_TOKEN
    HA_URL
    HOME_ASSISTANT_TOKEN
    HOME_ASSISTANT_URL
    # Proxmox
    API_TOKEN
    PBS_API_TOKEN
    PBS_URL
    PVE_ROOT_PASSWORD
    # MQTT
    MQTT_USER
    MQTT_PASS
    # MAAS
    MAAS_URL
    MAAS_USER
    MAAS_PASSWORD
    # Uptime Kuma
    UPTIME_KUMA_USERNAME
    UPTIME_KUMA_PASSWORD
    UPTIME_KUMA_PVE_API_KEY
    UPTIME_KUMA_PVE_URL
    UPTIME_KUMA_FUNBEDBUG_URL
    # Frigate cameras
    FRIGATE_CAM_REOLINK_USER
    FRIGATE_CAM_REOLINK_PASS
    FRIGATE_CAM_LIVINGROOM_USER
    FRIGATE_CAM_LIVINGROOM_PASS
    FRIGATE_CAM_LIVINGROOM_IP
    FRIGATE_CAM_MJPEG_USER
    FRIGATE_CAM_MJPEG_PASS
    FRIGATE_CAM_TRENDNET_USER
    FRIGATE_CAM_TRENDNET_PASS
    FRIGATE_MQTT_USER
    FRIGATE_MQTT_PASS
    PLUS_API_KEY
    # Crucible
    CRUCIBLE_USER_PASSWORD
)

echo "Reading credentials from $ENV_FILE..."

# Build stringData block
PLAIN_FILE="$TMPDIR/homelab-env.yaml"
cat > "$PLAIN_FILE" <<'HEADER'
apiVersion: v1
kind: Secret
metadata:
  name: homelab-env
  namespace: claudecodeui
type: Opaque
stringData:
HEADER

# Also build the .env content for file mount
ENV_CONTENT=""
FOUND=0
MISSING=0

for KEY in "${KEYS[@]}"; do
    # Extract value from .env (handle quotes, take first match)
    VALUE=$(grep "^${KEY}=" "$ENV_FILE" | head -1 | cut -d'=' -f2- | sed 's/^"//' | sed 's/"$//')
    if [[ -n "$VALUE" ]]; then
        # Escape for YAML string (wrap in quotes if contains special chars)
        printf '  %s: "%s"\n' "$KEY" "$VALUE" >> "$PLAIN_FILE"
        ENV_CONTENT+="${KEY}=${VALUE}\n"
        FOUND=$((FOUND + 1))
    else
        echo "  WARN: $KEY not found in .env"
        MISSING=$((MISSING + 1))
    fi
done

# Add the combined .env file content as a single key
printf '  dot-env: |\n' >> "$PLAIN_FILE"
printf "$ENV_CONTENT" | while IFS= read -r line; do
    printf '    %s\n' "$line" >> "$PLAIN_FILE"
done

echo ""
echo "Found $FOUND keys, missing $MISSING keys"
echo ""

# Encrypt with SOPS
echo "Encrypting with SOPS..."
mkdir -p "$SECRET_DIR"
sops --encrypt "$PLAIN_FILE" > "$SECRET_FILE"

echo ""
echo "=== Done! ==="
echo ""
echo "Encrypted secret: $SECRET_FILE"
echo "Keys included: $FOUND"
echo ""
echo "Next steps:"
echo "  1. Update deployment-blue.yaml to mount the secret"
echo "  2. Update kustomization.yaml to include the secret"
echo "  3. Commit and push"
echo "  4. Flux will reconcile and mount credentials in the pod"
