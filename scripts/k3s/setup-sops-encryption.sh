#!/bin/bash
# Setup SOPS + age encryption for Flux GitOps secrets
# This allows encrypting secrets in git that Flux can decrypt automatically

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

echo "========================================="
echo "SOPS + age Encryption Setup for Flux"
echo "========================================="
echo ""

# Step 1: Check/Install required tools
echo "Step 1: Checking required tools..."

# Add ~/.local/bin to PATH if it exists (for local installs)
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"

if ! command -v age &> /dev/null; then
    echo "  Installing age locally..."
    mkdir -p "$HOME/.local/bin"
    AGE_VERSION="1.1.1"
    wget -q "https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-linux-amd64.tar.gz" -O /tmp/age.tar.gz
    tar -xzf /tmp/age.tar.gz -C /tmp
    cp /tmp/age/age /tmp/age/age-keygen "$HOME/.local/bin/"
    chmod +x "$HOME/.local/bin/age" "$HOME/.local/bin/age-keygen"
    rm -rf /tmp/age /tmp/age.tar.gz
    export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v sops &> /dev/null; then
    echo "  Installing sops locally..."
    mkdir -p "$HOME/.local/bin"
    SOPS_VERSION="3.8.1"
    wget -q "https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops_${SOPS_VERSION}_amd64.deb" -O /tmp/sops.deb
    cd /tmp && ar x /tmp/sops.deb && tar -xzf data.tar.gz
    cp /tmp/usr/bin/sops "$HOME/.local/bin/"
    chmod +x "$HOME/.local/bin/sops"
    rm -f /tmp/sops.deb /tmp/control.tar.* /tmp/data.tar.* /tmp/debian-binary
    rm -rf /tmp/usr
    cd - > /dev/null
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "  ✓ age version: $(age --version 2>&1 | head -1)"
echo "  ✓ sops version: $(sops --version 2>&1 | head -1)"
echo ""

# Step 2: Generate or use existing age key
AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
mkdir -p "$(dirname "$AGE_KEY_FILE")"

if [ -f "$AGE_KEY_FILE" ]; then
    echo "Step 2: Using existing age key at $AGE_KEY_FILE"
else
    echo "Step 2: Generating new age key..."
    age-keygen -o "$AGE_KEY_FILE"
    chmod 600 "$AGE_KEY_FILE"
    echo "  ✓ Age key generated: $AGE_KEY_FILE"
fi

# Extract public key
AGE_PUBLIC_KEY=$(grep "# public key:" "$AGE_KEY_FILE" | sed 's/# public key: //')
echo "  Public key: $AGE_PUBLIC_KEY"
echo ""

# Step 3: Create Kubernetes secret with age private key for Flux
echo "Step 3: Creating Kubernetes secret for Flux to decrypt secrets..."
kubectl create namespace flux-system --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic sops-age \
    --namespace=flux-system \
    --from-file=age.agekey="$AGE_KEY_FILE" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "  ✓ Secret 'sops-age' created in flux-system namespace"
echo ""

# Step 4: Create .sops.yaml config file
echo "Step 4: Creating .sops.yaml configuration..."
cat > "$REPO_ROOT/.sops.yaml" << EOF
creation_rules:
  - path_regex: .*.yaml
    encrypted_regex: ^(data|stringData)$
    age: $AGE_PUBLIC_KEY
EOF

echo "  ✓ Created $REPO_ROOT/.sops.yaml"
echo ""

# Step 5: Update Flux Kustomization to enable decryption
echo "Step 5: Instructions to enable SOPS decryption in Flux..."
echo ""
echo "Add this to your Flux Kustomization resources:"
echo ""
cat << 'EOF'
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: homelab
  namespace: flux-system
spec:
  decryption:
    provider: sops
    secretRef:
      name: sops-age
  # ... rest of your kustomization spec
EOF
echo ""

# Step 6: Provide instructions for encrypting secrets
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Your age public key: $AGE_PUBLIC_KEY"
echo "Private key location: $AGE_KEY_FILE"
echo ""
echo "⚠ BACKUP YOUR PRIVATE KEY! Store it securely (password manager, etc.)"
echo "   cp $AGE_KEY_FILE /path/to/secure/backup/"
echo ""
echo "Next steps:"
echo ""
echo "1. Encrypt a secret file:"
echo "   sops --encrypt --in-place gitops/clusters/homelab/apps/postgres/secret.yaml"
echo ""
echo "2. Edit encrypted secret:"
echo "   sops gitops/clusters/homelab/apps/postgres/secret.yaml"
echo ""
echo "3. Decrypt to view (won't modify file):"
echo "   sops --decrypt gitops/clusters/homelab/apps/postgres/secret.yaml"
echo ""
echo "4. Update Flux Kustomization to enable decryption"
echo "   (see instructions above)"
echo ""
echo "5. Commit encrypted secrets to git - they're safe now!"
echo ""
