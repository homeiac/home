#!/opt/homebrew/bin/bash
# setup-github-ssh-secret.sh - Generate SSH key + GitHub PAT → SOPS-encrypted K8s Secret
#
# Composable: accepts PAT from stdin, --pat flag, or interactive prompt.
# Outputs the public key to stdout so callers can pipe it.
# All status messages go to stderr so stdout stays clean.
#
# Usage:
#   gh auth token | ./scripts/claudecodeui/setup-github-ssh-secret.sh
#   ./scripts/claudecodeui/setup-github-ssh-secret.sh --pat ghp_xxxx
#   ./scripts/claudecodeui/setup-github-ssh-secret.sh              # interactive prompt
#
# Options:
#   --pat TOKEN   Provide GitHub PAT directly
#   --force       Overwrite existing SOPS secret file
#
# Outputs:
#   stdout: public key (for piping to gh ssh-key add, etc.)
#   stderr: status/progress messages
#   File:   gitops/clusters/homelab/apps/claudecodeui/secrets/github-ssh-key.sops.yaml
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SECRET_DIR="$REPO_ROOT/gitops/clusters/homelab/apps/claudecodeui/secrets"
SECRET_FILE="$SECRET_DIR/github-ssh-key.sops.yaml"
ENCRYPT_SCRIPT="$REPO_ROOT/scripts/sops/encrypt-secret.sh"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# --- Parse arguments ---
GH_TOKEN=""
FORCE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pat)
            GH_TOKEN="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            awk 'NR>1 && /^#/{sub(/^# ?/,""); print} /^set -/{exit}' "$0" >&2
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# --- Check for existing secret file ---
if [[ -f "$SECRET_FILE" ]] && [[ "$FORCE" != true ]]; then
    echo "ERROR: Secret file already exists: $SECRET_FILE" >&2
    echo "       Use --force to overwrite." >&2
    exit 1
fi

# --- Get PAT: stdin > --pat > interactive ---
if [[ -z "$GH_TOKEN" ]]; then
    if [[ ! -t 0 ]]; then
        # stdin is a pipe — read PAT from it
        read -r GH_TOKEN
    else
        # interactive prompt
        echo "Create a GitHub Personal Access Token (classic) at:" >&2
        echo "  https://github.com/settings/tokens" >&2
        echo "Required scope: repo (Full control of private repositories)" >&2
        echo "" >&2
        read -rsp "Paste your GitHub PAT (input hidden): " GH_TOKEN >&2
        echo "" >&2
    fi
fi

if [[ -z "$GH_TOKEN" ]]; then
    echo "ERROR: No PAT provided. Pass via stdin, --pat, or interactive prompt." >&2
    exit 1
fi

# --- Generate ED25519 key pair ---
KEY_FILE="$TMPDIR/id_ed25519"
echo "Generating ED25519 SSH key pair..." >&2
ssh-keygen -t ed25519 -C "claudecodeui@homelab" -f "$KEY_FILE" -N "" -q

PRIVATE_KEY=$(cat "$KEY_FILE")
PUBLIC_KEY=$(cat "$KEY_FILE.pub")

# --- Create plaintext secret YAML ---
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

# --- Encrypt with SOPS ---
echo "Encrypting with SOPS via $ENCRYPT_SCRIPT ..." >&2
mkdir -p "$SECRET_DIR"
cp "$PLAIN_FILE" "$SECRET_FILE"
"$ENCRYPT_SCRIPT" "$SECRET_FILE" >&2

echo "" >&2
echo "Secret written to: $SECRET_FILE" >&2

# --- Output public key to stdout ---
echo "$PUBLIC_KEY"
