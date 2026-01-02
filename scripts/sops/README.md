# SOPS Scripts

Scripts for managing encrypted secrets with Mozilla SOPS + age encryption.

## Overview

This homelab uses SOPS to encrypt Kubernetes secrets in git. Flux automatically decrypts them during deployment.

**Authoritative key location**: K8s secret `flux-system/sops-age`

## Scripts

| Script | Purpose |
|--------|---------|
| `setup-local-sops.sh` | Fetch age key from K8s to enable local encrypt/decrypt |
| `encrypt-secret.sh` | Encrypt a secret YAML file |
| `copy-secret-to-namespace.sh` | Copy encrypted secret to different namespace |

## Quick Start

```bash
# 1. Setup local SOPS access (one-time)
./scripts/sops/setup-local-sops.sh

# 2. Create a secret file
cat > my-secret.yaml << 'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
  namespace: my-app
stringData:
  password: "super-secret-value"
EOF

# 3. Encrypt it
./scripts/sops/encrypt-secret.sh my-secret.yaml

# 4. Commit (now safe!)
git add my-secret.yaml
git commit -m "feat: add encrypted secret"
```

## Common Tasks

### Encrypt a new secret

```bash
./scripts/sops/encrypt-secret.sh path/to/secret.yaml
```

### Edit an encrypted secret

```bash
# Opens in $EDITOR, decrypts, re-encrypts on save
sops path/to/secret.yaml
```

### View decrypted content

```bash
sops --decrypt path/to/secret.yaml
```

### Copy secret to another namespace

```bash
./scripts/sops/copy-secret-to-namespace.sh \
  source-secret.yaml \
  new-namespace \
  dest-secret.yaml
```

## Full Documentation

See [docs/secret-management.md](../../docs/secret-management.md) for complete documentation including:
- How SOPS works
- Troubleshooting
- Team setup
- Migration guides
