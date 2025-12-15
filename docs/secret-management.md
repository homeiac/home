# Secret Management with SOPS + age

This homelab uses Mozilla SOPS with age encryption for GitOps secret management.

## Overview

**SOPS (Secrets OPerationS)** encrypts Kubernetes secrets so they can be safely committed to git. **age** is the encryption backend (modern, simple alternative to PGP).

### Benefits

- ✅ Secrets encrypted in git
- ✅ Flux automatically decrypts during deployment
- ✅ Human-readable YAML structure (only values encrypted)
- ✅ Simple key management with age
- ✅ No external dependencies (works offline)

## Setup

### Initial Setup (One-time)

```bash
# Run the setup script
./scripts/k3s/setup-sops-encryption.sh
```

This will:
1. Install `age` and `sops` tools
2. Generate age encryption key (`~/.config/sops/age/keys.txt`)
3. Create Kubernetes secret with private key for Flux
4. Generate `.sops.yaml` configuration

### Backup Your Key

**⚠ CRITICAL**: Backup your age private key securely!

```bash
# Copy to secure location (password manager, encrypted USB, etc.)
cp ~/.config/sops/age/keys.txt /path/to/secure/backup/

# Get public key for sharing/documentation
grep "# public key:" ~/.config/sops/age/keys.txt
```

### Enable Flux Decryption

Update your Flux Kustomization to decrypt SOPS secrets:

```yaml
# gitops/clusters/homelab/flux-system/kustomization.yaml
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
  interval: 1m
  path: ./gitops/clusters/homelab
  prune: true
  sourceRef:
    kind: GitRepository
    name: flux-system
```

## Usage

### Encrypting a New Secret

```bash
# Create secret normally
cat > secret.yaml << EOF
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
  namespace: default
stringData:
  password: "my-secure-password"
  api-key: "super-secret-key"
EOF

# Encrypt in-place (modifies the file)
sops --encrypt --in-place secret.yaml

# Now it's safe to commit!
git add secret.yaml
git commit -m "feat: add encrypted secret"
```

### Editing Encrypted Secrets

```bash
# Opens in your $EDITOR, decrypts for editing, re-encrypts on save
sops gitops/clusters/homelab/apps/postgres/secret.yaml
```

SOPS automatically:
- Decrypts the file
- Opens in your editor
- Re-encrypts when you save and exit

### Viewing Encrypted Secrets

```bash
# Decrypt to stdout (doesn't modify file)
sops --decrypt gitops/clusters/homelab/apps/postgres/secret.yaml

# View specific value
sops --decrypt gitops/clusters/homelab/apps/postgres/secret.yaml | \
  yq '.stringData.POSTGRES_PASSWORD'
```

### Encrypting Existing Secrets

```bash
# Encrypt a plain YAML file
sops --encrypt --in-place path/to/secret.yaml

# Encrypt only specific fields (configured in .sops.yaml)
# By default, only 'data' and 'stringData' are encrypted
```

## File Structure

Encrypted files look like this:

```yaml
apiVersion: v1
kind: Secret
metadata:
    name: postgres-credentials
    namespace: database
type: Opaque
stringData:
    POSTGRES_PASSWORD: ENC[AES256_GCM,data:encrypted_value_here,iv:...,tag:...,type:str]
    POSTGRES_USER: ENC[AES256_GCM,data:another_encrypted_value,iv:...,tag:...,type:str]
sops:
    kms: []
    gcp_kms: []
    azure_kv: []
    hc_vault: []
    age:
        - recipient: age1234567890abcdefghijklmnopqrstuvwxyz
          enc: |
            -----BEGIN AGE ENCRYPTED FILE-----
            ...
            -----END AGE ENCRYPTED FILE-----
    lastmodified: "2025-12-15T12:00:00Z"
    mac: ENC[HEX,...]
    pgp: []
    version: 3.8.1
```

- Metadata is plaintext (readable in git diffs)
- Only secret values are encrypted
- SOPS metadata tracks encryption info

## Configuration (.sops.yaml)

Located at repository root: `/home/claude/projects/home/.sops.yaml`

```yaml
creation_rules:
  - path_regex: .*.yaml
    encrypted_regex: ^(data|stringData)$
    age: age1uwvq3llqjt666t4ckls9wv44wcpxxwlu8svqwx5kc7v76hncj94qg3tsna
```

This tells SOPS:
- Encrypt all `.yaml` files
- Only encrypt `data` and `stringData` fields
- Use the specified age public key

## Best Practices

### DO

✅ **Encrypt before committing**
```bash
sops --encrypt --in-place secret.yaml
git add secret.yaml
```

✅ **Use `sops` to edit encrypted files**
```bash
sops gitops/clusters/homelab/apps/postgres/secret.yaml
```

✅ **Backup your age private key securely**

✅ **Share age public key** (safe to share, needed by team members)

✅ **Use `.sops.yaml` to control what gets encrypted**

### DON'T

❌ **Don't commit unencrypted secrets**
```bash
# BAD - plain secret in git
git add secret.yaml  # if not encrypted
```

❌ **Don't edit encrypted files manually** (use `sops` command)

❌ **Don't lose your private key** (backup!)

❌ **Don't share your private key** via git/email/slack

## Troubleshooting

### "failed to get the data key"

Flux can't decrypt - check the `sops-age` secret exists:

```bash
kubectl get secret sops-age -n flux-system

# Recreate if missing
./scripts/k3s/setup-sops-encryption.sh
```

### "no age keys found"

Your age private key is missing:

```bash
# Check key exists
ls -la ~/.config/sops/age/keys.txt

# Restore from backup
cp /path/to/backup/keys.txt ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
```

### "MAC mismatch"

File corruption or wrong key. Restore from git history:

```bash
git checkout HEAD~1 -- path/to/secret.yaml
```

### Can't decrypt in git diff

Normal! Use `sops --decrypt` to view:

```bash
# View diff of decrypted content
git diff <(sops --decrypt HEAD:path/to/secret.yaml) \
         <(sops --decrypt path/to/secret.yaml)
```

## Team Usage

### Adding Team Members

Share your age public key (safe):

```bash
grep "# public key:" ~/.config/sops/age/keys.txt
# age1234567890abcdefghijklmnopqrstuvwxyz
```

Team member setup:
1. Install age and sops
2. Generate their own age key: `age-keygen`
3. Add their public key to `.sops.yaml`:

```yaml
creation_rules:
  - path_regex: .*.yaml
    encrypted_regex: ^(data|stringData)$
    age: >-
      age1original_key,
      age1team_member_key
```

4. Re-encrypt all secrets with both keys:

```bash
find . -name "*.yaml" -path "*/secrets/*" -exec sops updatekeys {} \;
```

## Migration

### From Manual Secrets

If you have manually created secrets (via `kubectl create secret`):

```bash
# 1. Extract existing secret
kubectl get secret postgres-credentials -n database -o yaml > secret.yaml

# 2. Clean up (remove cluster-specific fields)
yq 'del(.metadata.uid, .metadata.resourceVersion, .metadata.creationTimestamp)' secret.yaml > clean-secret.yaml

# 3. Encrypt
sops --encrypt --in-place clean-secret.yaml

# 4. Move to GitOps repo
mv clean-secret.yaml gitops/clusters/homelab/apps/postgres/secret.yaml

# 5. Commit
git add gitops/clusters/homelab/apps/postgres/secret.yaml
git commit -m "feat: migrate postgres secret to SOPS"
```

### From .example Files

```bash
# 1. Copy example to real file
cp secret.yaml.example secret.yaml

# 2. Edit with real values
vim secret.yaml  # or use your editor

# 3. Encrypt
sops --encrypt --in-place secret.yaml

# 4. Commit
git add secret.yaml
git commit -m "feat: add encrypted secret"

# 5. Delete example (optional)
git rm secret.yaml.example
```

## Current Encrypted Secrets

| Secret | Namespace | Purpose |
|--------|-----------|---------|
| `postgres-credentials` | database | PostgreSQL admin password |
| `rclone-gdrive-config` | database | Google Drive OAuth token for backups |
| `mqtt-credentials` | claudecodeui | MQTT broker credentials |

## Key Backup Locations

The age private key should be backed up to multiple locations:

- [x] Proxmox host: `chief-horse.maas:/root/.sops-age-backup/`
- [x] Proxmox host: `still-fawn.maas:/root/.sops-age-backup/`
- [ ] Google Drive (encrypted)
- [ ] Password manager

**Current Public Key:** `age1uwvq3llqjt666t4ckls9wv44wcpxxwlu8svqwx5kc7v76hncj94qg3tsna`

## References

- [SOPS Documentation](https://github.com/getsops/sops)
- [age Documentation](https://github.com/FiloSottile/age)
- [Flux SOPS Guide](https://fluxcd.io/flux/guides/mozilla-sops/)
