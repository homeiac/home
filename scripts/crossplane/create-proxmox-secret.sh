#!/bin/bash
# Create Proxmox credentials secret for Crossplane
# Usage: ./create-proxmox-secret.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

# Source credentials from .env
if [[ -f "$ENV_FILE" ]]; then
    API_TOKEN=$(grep "^API_TOKEN=" "$ENV_FILE" | cut -d'=' -f2-)
else
    echo "ERROR: .env file not found at $ENV_FILE"
    echo "Copy from .env.example and fill in your credentials"
    exit 1
fi

if [[ -z "$API_TOKEN" ]]; then
    echo "ERROR: API_TOKEN not found in .env"
    exit 1
fi

# Proxmox endpoint - using pumped-piglet as primary
PROXMOX_ENDPOINT="https://pumped-piglet.maas:8006"

echo "=== Creating Proxmox credentials secret for Crossplane ==="
echo ""
echo "Endpoint: $PROXMOX_ENDPOINT"
echo "Token ID: ${API_TOKEN%%=*}=***"
echo ""

# Ensure namespace exists
kubectl get namespace crossplane-system >/dev/null 2>&1 || \
    kubectl create namespace crossplane-system

# Delete existing secret if present
kubectl delete secret proxmox-credentials -n crossplane-system 2>/dev/null || true

# Create secret
kubectl create secret generic proxmox-credentials \
    -n crossplane-system \
    --from-literal=api_token="$API_TOKEN" \
    --from-literal=endpoint="$PROXMOX_ENDPOINT"

echo ""
echo "Secret created successfully!"
echo ""
echo "Verify with: kubectl get secret proxmox-credentials -n crossplane-system"
