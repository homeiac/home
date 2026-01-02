#!/bin/bash
# Encrypt a Kubernetes secret YAML file with SOPS
#
# This script encrypts the stringData/data fields of a K8s secret YAML file
# using the age key from ~/.config/sops/age/keys.txt
#
# Usage:
#   ./scripts/sops/encrypt-secret.sh <secret-file.yaml>
#
# Example:
#   ./scripts/sops/encrypt-secret.sh gitops/clusters/homelab/apps/myapp/secret.yaml
#
# Prerequisites:
#   - Run ./scripts/sops/setup-local-sops.sh first (to get the age key)
#   - sops installed (brew install sops)
#
# What it does:
#   1. Checks the age key exists locally
#   2. Encrypts only stringData and data fields (per .sops.yaml config)
#   3. Modifies the file in-place
#
# After encrypting:
#   - Safe to commit to git
#   - Flux will auto-decrypt when deploying

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/../.."

# Check argument
if [[ -z "$1" ]]; then
    echo "Usage: $0 <secret-file.yaml>"
    echo ""
    echo "Example:"
    echo "  $0 gitops/clusters/homelab/apps/myapp/secret.yaml"
    exit 1
fi

SECRET_FILE="$1"

# Check file exists
if [[ ! -f "$SECRET_FILE" ]]; then
    echo "ERROR: File not found: $SECRET_FILE"
    exit 1
fi

# Check age key exists and set SOPS_AGE_KEY_FILE
if [[ ! -f "$HOME/.config/sops/age/keys.txt" ]]; then
    echo "ERROR: Age key not found at ~/.config/sops/age/keys.txt"
    echo ""
    echo "Run this first:"
    echo "  ./scripts/sops/setup-local-sops.sh"
    exit 1
fi
export SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"

# Check if already encrypted
if grep -q "ENC\[AES256_GCM" "$SECRET_FILE" 2>/dev/null; then
    echo "WARNING: File appears to already be encrypted"
    echo "         Use 'sops $SECRET_FILE' to edit, or"
    echo "         Use 'sops --decrypt $SECRET_FILE' to view"
    exit 1
fi

# Encrypt
echo "Encrypting: $SECRET_FILE"
sops --encrypt --in-place "$SECRET_FILE"

echo ""
echo "✅ Encrypted successfully!"
echo ""
echo "Verify with:"
echo "  sops --decrypt $SECRET_FILE | head -20"
echo ""
echo "Safe to commit:"
echo "  git add $SECRET_FILE"
