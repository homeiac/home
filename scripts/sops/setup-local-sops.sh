#!/bin/bash
# Setup local SOPS access by fetching the age key from K8s
#
# The authoritative age key is stored in K8s secret: flux-system/sops-age
# This script fetches it and saves it locally for sops encrypt/decrypt operations.
#
# Usage:
#   ./scripts/sops/setup-local-sops.sh
#
# Prerequisites:
#   - kubectl access to the K8s cluster
#   - KUBECONFIG set or ~/kubeconfig exists

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Determine KUBECONFIG
if [[ -z "$KUBECONFIG" ]]; then
    if [[ -f "$HOME/kubeconfig" ]]; then
        export KUBECONFIG="$HOME/kubeconfig"
    else
        echo "ERROR: KUBECONFIG not set and ~/kubeconfig not found"
        exit 1
    fi
fi

echo "Using KUBECONFIG: $KUBECONFIG"

# Check if secret exists
if ! kubectl get secret sops-age -n flux-system &>/dev/null; then
    echo "ERROR: Secret 'sops-age' not found in flux-system namespace"
    echo "       Run scripts/k3s/setup-sops-encryption.sh first"
    exit 1
fi

# Create directory
mkdir -p ~/.config/sops/age

# Fetch and save key
echo "Fetching age key from K8s cluster..."
kubectl get secret sops-age -n flux-system \
    -o jsonpath='{.data.age\.agekey}' | base64 -d > ~/.config/sops/age/keys.txt

chmod 600 ~/.config/sops/age/keys.txt

# Verify
PUBLIC_KEY=$(grep "# public key:" ~/.config/sops/age/keys.txt | awk '{print $4}')
echo ""
echo "✅ Age key saved to: ~/.config/sops/age/keys.txt"
echo "   Public key: $PUBLIC_KEY"
echo ""
echo "To use sops, first set the key path:"
echo "  export SOPS_AGE_KEY_FILE=$HOME/.config/sops/age/keys.txt"
echo ""
echo "Or add to your shell profile (~/.zshrc or ~/.bashrc):"
echo "  echo 'export SOPS_AGE_KEY_FILE=\$HOME/.config/sops/age/keys.txt' >> ~/.zshrc"
echo ""
echo "Then you can use sops commands:"
echo "  sops --encrypt --in-place secret.yaml"
echo "  sops --decrypt secret.yaml"
echo "  sops secret.yaml  # edit in place"
