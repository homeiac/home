#!/bin/bash
# Copy an encrypted secret to a new namespace
#
# This is useful when you need the same secret (e.g., Cloudflare API token)
# in multiple namespaces. It decrypts the source, changes the namespace,
# and re-encrypts.
#
# Usage:
#   ./scripts/sops/copy-secret-to-namespace.sh <source-secret.yaml> <new-namespace> <dest-secret.yaml>
#
# Example:
#   ./scripts/sops/copy-secret-to-namespace.sh \
#     gitops/clusters/homelab/infrastructure/external-dns/cloudflare-secret.yaml \
#     cert-manager \
#     gitops/clusters/homelab/infrastructure/cert-manager/cloudflare-secret.yaml
#
# Prerequisites:
#   - Run ./scripts/sops/setup-local-sops.sh first
#   - sops and yq installed

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check arguments
if [[ $# -ne 3 ]]; then
    echo "Usage: $0 <source-secret.yaml> <new-namespace> <dest-secret.yaml>"
    echo ""
    echo "Example:"
    echo "  $0 gitops/.../external-dns/cloudflare-secret.yaml cert-manager gitops/.../cert-manager/cloudflare-secret.yaml"
    exit 1
fi

SOURCE_FILE="$1"
NEW_NAMESPACE="$2"
DEST_FILE="$3"

# Check source exists
if [[ ! -f "$SOURCE_FILE" ]]; then
    echo "ERROR: Source file not found: $SOURCE_FILE"
    exit 1
fi

# Check age key exists and set SOPS_AGE_KEY_FILE
if [[ ! -f "$HOME/.config/sops/age/keys.txt" ]]; then
    echo "ERROR: Age key not found. Run ./scripts/sops/setup-local-sops.sh first"
    exit 1
fi
export SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"

# Check yq installed
if ! command -v yq &>/dev/null; then
    echo "ERROR: yq not installed. Run: brew install yq"
    exit 1
fi

# Create dest directory if needed
mkdir -p "$(dirname "$DEST_FILE")"

# Decrypt, change namespace, save
echo "Decrypting source: $SOURCE_FILE"
echo "Changing namespace to: $NEW_NAMESPACE"

# Decrypt and change namespace (yq preserves all other fields)
sops --decrypt "$SOURCE_FILE" | \
    yq eval ".metadata.namespace = \"$NEW_NAMESPACE\"" - > "$DEST_FILE"

# Verify the output has required fields
if ! grep -q "apiVersion:" "$DEST_FILE"; then
    echo "ERROR: Output file is missing apiVersion - yq may have failed"
    rm -f "$DEST_FILE"
    exit 1
fi

# Encrypt destination
echo "Encrypting destination: $DEST_FILE"
sops --encrypt --in-place "$DEST_FILE"

echo ""
echo "✅ Secret copied and encrypted!"
echo ""
echo "Source:      $SOURCE_FILE"
echo "Destination: $DEST_FILE"
echo "Namespace:   $NEW_NAMESPACE"
echo ""
echo "Verify with:"
echo "  sops --decrypt $DEST_FILE | head -20"
