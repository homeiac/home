#!/bin/bash
# setup-proxmox-ssh-secret.sh - Generate SSH key for Proxmox hosts → SOPS-encrypted K8s Secret
# Also distributes the public key to all Proxmox hosts for passwordless SSH access.
# Usage: ./scripts/claudecodeui/setup-proxmox-ssh-secret.sh
#
# Prerequisites:
#   - sshpass installed (brew install sshpass or apt install sshpass)
#   - sops installed
#   - PVE_ROOT_PASSWORD set in proxmox/homelab/.env
#   - SSH access to Proxmox hosts from this machine
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$REPO_ROOT/proxmox/homelab/.env"
SECRET_DIR="$REPO_ROOT/gitops/clusters/homelab/apps/claudecodeui/blue/secrets"
SECRET_FILE="$SECRET_DIR/proxmox-ssh-key.sops.yaml"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Proxmox hosts to distribute the key to
# pve doesn't resolve via MAAS DNS, so use IP directly
PROXMOX_HOSTS=(
    "root@still-fawn.maas"
    "root@chief-horse.maas"
    "root@fun-bedbug.maas"
    "root@pumped-piglet.maas"
    "root@rapid-civet.maas"
    "root@192.168.4.122"  # pve (not in MAAS DNS)
)

echo "=== Claude Code UI: Proxmox SSH Key Setup ==="
echo ""

# --- Step 1: Read PVE_ROOT_PASSWORD from .env ---
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env file not found at $ENV_FILE"
    exit 1
fi

PVE_ROOT_PASSWORD=$(grep "^PVE_ROOT_PASSWORD=" "$ENV_FILE" | head -1 | cut -d'=' -f2- | sed 's/^"//' | sed 's/"$//')
if [[ -z "$PVE_ROOT_PASSWORD" ]]; then
    echo "ERROR: PVE_ROOT_PASSWORD not found in $ENV_FILE"
    exit 1
fi
echo "Found PVE_ROOT_PASSWORD in .env"

# --- Step 2: Generate ED25519 key pair ---
KEY_FILE="$TMPDIR/id_ed25519"
echo "Generating ED25519 SSH key pair for Proxmox access..."
ssh-keygen -t ed25519 -C "claudecodeui-proxmox@homelab" -f "$KEY_FILE" -N "" -q

PRIVATE_KEY=$(cat "$KEY_FILE")
PUBLIC_KEY=$(cat "$KEY_FILE.pub")

echo "Key generated: $PUBLIC_KEY"
echo ""

# --- Step 3: Distribute public key to Proxmox hosts ---
echo "Distributing public key to Proxmox hosts..."
echo ""

if ! command -v sshpass &>/dev/null; then
    echo "WARNING: sshpass not installed. Skipping key distribution."
    echo "Install with: brew install hudochenkov/sshpass/sshpass"
    echo "You will need to manually add this public key to each Proxmox host:"
    echo "  $PUBLIC_KEY"
    echo ""
else
    for HOST in "${PROXMOX_HOSTS[@]}"; do
        echo -n "  $HOST ... "
        if sshpass -p "$PVE_ROOT_PASSWORD" ssh-copy-id \
            -o StrictHostKeyChecking=no \
            -o ConnectTimeout=5 \
            -i "$KEY_FILE.pub" \
            "$HOST" 2>/dev/null; then
            echo "OK"
        else
            echo "FAILED (host may be offline)"
        fi
    done
fi

echo ""

# --- Step 4: Create plaintext secret YAML ---
PLAIN_FILE="$TMPDIR/proxmox-ssh-key.yaml"
cat > "$PLAIN_FILE" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: proxmox-ssh-key
  namespace: claudecodeui
type: Opaque
stringData:
  id_ed25519: |
$(echo "$PRIVATE_KEY" | sed 's/^/    /')
  id_ed25519.pub: "$PUBLIC_KEY"
EOF

# --- Step 5: Encrypt with SOPS ---
echo "Encrypting with SOPS..."
mkdir -p "$SECRET_DIR"
sops --encrypt "$PLAIN_FILE" > "$SECRET_FILE"

echo ""
echo "=== Done! ==="
echo ""
echo "Encrypted secret: $SECRET_FILE"
echo ""
echo "Next steps:"
echo "  1. Update deployment-blue.yaml to mount the secret (add volume + init container logic)"
echo "  2. Update kustomization.yaml to include: blue/secrets/proxmox-ssh-key.sops.yaml"
echo "  3. Commit and push"
echo "  4. Flux will reconcile and mount the key in the pod"
echo ""
echo "Verify from pod:"
echo "  ssh root@still-fawn.maas hostname"
echo "  ssh root@192.168.4.122 hostname   # pve"
