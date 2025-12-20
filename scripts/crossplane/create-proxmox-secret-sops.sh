#!/bin/bash
# Create SOPS-encrypted Proxmox credentials secret for Crossplane
# Usage: ./create-proxmox-secret-sops.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"
OUTPUT_FILE="$SCRIPT_DIR/../../gitops/clusters/homelab/infrastructure/crossplane/proxmox-secret.yaml"

# Source credentials from .env
if [[ -f "$ENV_FILE" ]]; then
    API_TOKEN=$(grep "^API_TOKEN=" "$ENV_FILE" | cut -d'=' -f2-)
else
    echo "ERROR: .env file not found at $ENV_FILE"
    exit 1
fi

if [[ -z "$API_TOKEN" ]]; then
    echo "ERROR: API_TOKEN not found in .env"
    exit 1
fi

# Parse API_TOKEN format: user@realm!tokenid=tokensecret
# e.g., root@pam!provision-manage-vms=abc123...
TOKEN_USER="${API_TOKEN%%!*}"           # root@pam
TOKEN_ID_SECRET="${API_TOKEN#*!}"       # provision-manage-vms=abc123...
TOKEN_ID="${TOKEN_ID_SECRET%%=*}"       # provision-manage-vms
TOKEN_SECRET="${TOKEN_ID_SECRET#*=}"    # abc123...

# Proxmox endpoint
PROXMOX_ENDPOINT="https://pumped-piglet.maas:8006"

echo "=== Creating SOPS-encrypted Proxmox secret ==="
echo ""
echo "Endpoint: $PROXMOX_ENDPOINT"
echo "User: $TOKEN_USER"
echo "Token ID: $TOKEN_ID"
echo ""

# Create unencrypted YAML - provider expects JSON in 'credentials' key
cat > /tmp/proxmox-secret-plain.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: proxmox-credentials
  namespace: crossplane-system
type: Opaque
stringData:
  credentials: |
    {
      "endpoint": "${PROXMOX_ENDPOINT}",
      "api_token": "${TOKEN_USER}!${TOKEN_ID}=${TOKEN_SECRET}",
      "insecure": "true"
    }
EOF

# Encrypt with SOPS
cd "$SCRIPT_DIR/../.."
sops --encrypt /tmp/proxmox-secret-plain.yaml > "$OUTPUT_FILE"
rm /tmp/proxmox-secret-plain.yaml

echo "Created: $OUTPUT_FILE"
echo ""
echo "Add to kustomization.yaml and commit to Git."
echo "Flux will decrypt and apply automatically."
