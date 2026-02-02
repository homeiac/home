#!/bin/bash
# setup-github-ssh-secret.sh - Generate SSH key + GitHub PAT → SOPS-encrypted K8s Secret
# Usage: ./scripts/claudecodeui/setup-github-ssh-secret.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SECRET_DIR="$REPO_ROOT/gitops/clusters/homelab/apps/claudecodeui/secrets"
SECRET_FILE="$SECRET_DIR/github-ssh-key.sops.yaml"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "=== Claude Code UI: GitHub SSH Key Setup ==="
echo ""

# --- Step 1: Generate ED25519 key pair ---
KEY_FILE="$TMPDIR/id_ed25519"
echo "Generating ED25519 SSH key pair..."
ssh-keygen -t ed25519 -C "claudecodeui@homelab" -f "$KEY_FILE" -N "" -q

PRIVATE_KEY=$(cat "$KEY_FILE")
PUBLIC_KEY=$(cat "$KEY_FILE.pub")

echo ""
echo "============================================"
echo "PUBLIC KEY (add this to https://github.com/settings/keys):"
echo "============================================"
echo ""
echo "$PUBLIC_KEY"
echo ""
echo "============================================"
echo ""

# --- Step 2: Prompt for GitHub PAT ---
echo "Create a GitHub Personal Access Token (classic) at:"
echo "  https://github.com/settings/tokens"
echo ""
echo "Required scope: repo (Full control of private repositories)"
echo ""
read -rsp "Paste your GitHub PAT (input hidden): " GH_TOKEN
echo ""

if [[ -z "$GH_TOKEN" ]]; then
    echo "ERROR: No PAT provided. Aborting."
    exit 1
fi

# --- Step 3: Create plaintext secret YAML ---
PLAIN_FILE="$TMPDIR/github-ssh-key.yaml"
cat > "$PLAIN_FILE" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: github-ssh-key
  namespace: claudecodeui
type: Opaque
stringData:
  id_ed25519: |
$(echo "$PRIVATE_KEY" | sed 's/^/    /')
  id_ed25519.pub: "$PUBLIC_KEY"
  gh_token: "$GH_TOKEN"
EOF

# --- Step 4: Encrypt with SOPS ---
echo "Encrypting with SOPS..."
mkdir -p "$SECRET_DIR"
sops --encrypt --in-place "$PLAIN_FILE" 2>/dev/null || \
    sops --encrypt "$PLAIN_FILE" > "$SECRET_FILE"

# If in-place worked, move it
if [[ ! -f "$SECRET_FILE" ]] || [[ "$PLAIN_FILE" -nt "$SECRET_FILE" ]]; then
    cp "$PLAIN_FILE" "$SECRET_FILE"
fi

echo ""
echo "=== Done! ==="
echo ""
echo "Secret written to: $SECRET_FILE"
echo ""
echo "Next steps:"
echo "  1. Add the public key to GitHub: https://github.com/settings/keys"
echo "  2. Commit and push: git add '$SECRET_FILE' && git commit -m 'feat: add GitHub SSH key secret'"
echo "  3. Flux will reconcile and mount the key in the pod"
echo "  4. Verify: ./scripts/claudecodeui/verify-github-auth.sh"
