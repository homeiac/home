#!/bin/bash
# Install Crossplane Proxmox provider after Crossplane is ready
# Usage: ./install-provider.sh
#
# This handles the chicken-and-egg problem:
# 1. Crossplane must be installed first (via Flux)
# 2. Provider CRDs only exist after Crossplane installs
# 3. This script waits for Crossplane, then applies provider
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CROSSPLANE_DIR="$SCRIPT_DIR/../../gitops/clusters/homelab/infrastructure/crossplane"

echo "=== Installing Crossplane Proxmox Provider ==="
echo ""

# Check kubectl
if ! command -v kubectl &> /dev/null; then
    echo "ERROR: kubectl not found"
    exit 1
fi

# Set kubeconfig if needed
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

# Wait for Crossplane to be ready
echo "Waiting for Crossplane to be ready..."
for i in {1..30}; do
    if kubectl get deployment crossplane -n crossplane-system &>/dev/null; then
        if kubectl rollout status deployment/crossplane -n crossplane-system --timeout=10s &>/dev/null; then
            echo "  Crossplane is ready!"
            break
        fi
    fi
    echo "  Attempt $i/30 - waiting..."
    sleep 10
done

# Verify Provider CRD exists
echo ""
echo "Checking for Provider CRD..."
if ! kubectl get crd providers.pkg.crossplane.io &>/dev/null; then
    echo "ERROR: Provider CRD not found - Crossplane may not be fully installed"
    echo "Check: kubectl get pods -n crossplane-system"
    exit 1
fi
echo "  Provider CRD exists"

# Apply provider
echo ""
echo "Applying Proxmox provider..."
kubectl apply -f "$CROSSPLANE_DIR/provider-proxmox.yaml"

# Wait for provider to be healthy
echo ""
echo "Waiting for provider to be healthy..."
for i in {1..30}; do
    STATUS=$(kubectl get provider provider-proxmox-bpg -o jsonpath='{.status.conditions[?(@.type=="Healthy")].status}' 2>/dev/null || echo "Unknown")
    if [[ "$STATUS" == "True" ]]; then
        echo "  Provider is healthy!"
        break
    fi
    echo "  Attempt $i/30 - status: $STATUS"
    sleep 10
done

# Create secret (requires .env)
echo ""
echo "Creating Proxmox credentials secret..."
"$SCRIPT_DIR/create-proxmox-secret.sh"

# Apply provider config
echo ""
echo "Applying ProviderConfig..."
kubectl apply -f "$CROSSPLANE_DIR/provider-config.yaml"

# Verify
echo ""
echo "=== Installation Complete ==="
echo ""
kubectl get providers
echo ""
kubectl get providerconfigs
