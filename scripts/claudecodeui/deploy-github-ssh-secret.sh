#!/opt/homebrew/bin/bash
# deploy-github-ssh-secret.sh - End-to-end GitHub SSH secret deployment
#
# Orchestrates the full lifecycle:
#   1. Generate SSH key + encrypt SOPS secret (via setup-github-ssh-secret.sh)
#   2. Register public key on GitHub (via gh ssh-key add)
#   3. Uncomment the secret in kustomization.yaml (if commented out)
#   4. Commit + push the SOPS secret and kustomization change
#   5. Trigger Flux reconciliation
#   6. Wait for pod rollout
#   7. Verify GitHub auth from inside the pod
#
# Usage:
#   ./scripts/claudecodeui/deploy-github-ssh-secret.sh           # uses gh auth token
#   ./scripts/claudecodeui/deploy-github-ssh-secret.sh --force    # regenerate existing secret
#
# Prerequisites:
#   - gh CLI authenticated (gh auth status)
#   - sops + age key configured (scripts/sops/setup-local-sops.sh)
#   - kubectl configured with homelab cluster access
#   - flux CLI installed
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SETUP_SCRIPT="$SCRIPT_DIR/setup-github-ssh-secret.sh"
VERIFY_SCRIPT="$SCRIPT_DIR/verify-github-auth.sh"
KUSTOMIZATION="$REPO_ROOT/gitops/clusters/homelab/apps/claudecodeui/kustomization.yaml"
SECRET_FILE="$REPO_ROOT/gitops/clusters/homelab/apps/claudecodeui/secrets/github-ssh-key.sops.yaml"

NAMESPACE="claudecodeui"
DEPLOYMENT="claudecodeui-blue"
FORCE=""
DRY_RUN=false

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)
            FORCE="--force"
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            awk 'NR>1 && /^#/{sub(/^# ?/,""); print} /^set -/{exit}' "$0"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option: $1"
            exit 1
            ;;
    esac
done

# --- Preflight checks ---
echo "=== Preflight Checks ==="

if ! command -v gh &>/dev/null; then
    echo "ERROR: gh CLI not found. Install with: brew install gh"
    exit 1
fi

if ! gh auth status &>/dev/null; then
    echo "ERROR: gh CLI not authenticated. Run: gh auth login"
    exit 1
fi

if ! command -v sops &>/dev/null; then
    echo "ERROR: sops not found. Install with: brew install sops"
    exit 1
fi

if ! command -v kubectl &>/dev/null; then
    echo "ERROR: kubectl not found."
    exit 1
fi

if ! command -v flux &>/dev/null; then
    echo "ERROR: flux CLI not found. Install with: brew install fluxcd/tap/flux"
    exit 1
fi

echo "All tools present."
echo ""

# --- Step 1: Generate key + encrypt secret ---
echo "=== Step 1: Generate SSH key + SOPS-encrypt secret ==="
PUBKEY=$(gh auth token | "$SETUP_SCRIPT" $FORCE)

if [[ -z "$PUBKEY" ]]; then
    echo "ERROR: setup script did not output a public key."
    exit 1
fi

echo "Public key: $PUBKEY"
echo ""

# --- Step 2: Register public key on GitHub ---
echo "=== Step 2: Register public key on GitHub ==="

# Write pubkey to temp file (gh ssh-key add reads from file)
TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT
echo "$PUBKEY" > "$TMPFILE"

if gh ssh-key add "$TMPFILE" --title "claudecodeui@homelab-$(date +%Y%m%d)" 2>&1; then
    echo "Public key registered on GitHub."
else
    echo "WARNING: Failed to add SSH key to GitHub (may already exist)."
    echo "         Check: https://github.com/settings/keys"
fi
rm -f "$TMPFILE"
echo ""

# --- Step 3: Uncomment secret in kustomization.yaml ---
echo "=== Step 3: Update kustomization.yaml ==="

if grep -q '# - secrets/github-ssh-key.sops.yaml' "$KUSTOMIZATION"; then
    # Uncomment the line (remove "# " prefix and trailing comment)
    sed -i '' 's|^  # - secrets/github-ssh-key.sops.yaml.*|  - secrets/github-ssh-key.sops.yaml|' "$KUSTOMIZATION"
    echo "Uncommented github-ssh-key.sops.yaml in kustomization.yaml"
elif grep -q '- secrets/github-ssh-key.sops.yaml' "$KUSTOMIZATION"; then
    echo "Already uncommented in kustomization.yaml."
else
    echo "WARNING: github-ssh-key.sops.yaml not found in kustomization.yaml."
    echo "         You may need to add it manually."
fi
echo ""

if [[ "$DRY_RUN" == true ]]; then
    echo "=== DRY RUN: Stopping before git/flux operations ==="
    echo "Files modified:"
    echo "  $SECRET_FILE"
    echo "  $KUSTOMIZATION"
    exit 0
fi

# --- Step 4: Commit + push ---
echo "=== Step 4: Commit and push ==="

cd "$REPO_ROOT"

git add "$SECRET_FILE" "$KUSTOMIZATION"

# Safety: verify no secrets in staged diff
if git diff --cached | grep -iE "password|secret.*=|token.*=|private_key" | grep -v "ENC\[AES256_GCM" | grep -v "^[+-].*name:" | grep -qv "^[+-].*#"; then
    echo "ERROR: Possible secrets detected in staged changes. Aborting commit."
    echo "Run: git diff --cached"
    git reset HEAD "$SECRET_FILE" "$KUSTOMIZATION"
    exit 1
fi

git commit -m "$(cat <<'EOF'
feat: add SOPS-encrypted GitHub SSH key secret for Claude Code UI

- Generated ED25519 key pair for git operations
- Encrypted with SOPS (age) for safe GitOps storage
- Enabled in kustomization.yaml for Flux deployment

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"

git push
echo ""

# --- Step 5: Flux reconcile ---
echo "=== Step 5: Flux reconcile ==="
flux reconcile kustomization flux-system --with-source
echo ""

# --- Step 6: Wait for rollout ---
echo "=== Step 6: Waiting for pod rollout ==="

# Restart the deployment to pick up the new secret
kubectl rollout restart deployment/"$DEPLOYMENT" -n "$NAMESPACE"
kubectl rollout status deployment/"$DEPLOYMENT" -n "$NAMESPACE" --timeout=120s
echo ""

# --- Step 7: Verify ---
echo "=== Step 7: Verify GitHub auth ==="

# Give the init container a moment to set up SSH
echo "Waiting 15s for init container to configure SSH..."
sleep 15

"$VERIFY_SCRIPT"

echo ""
echo "=== Deploy complete ==="
