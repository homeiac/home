# Frigate Configuration Management Runbook

## Overview

Frigate configuration involves multiple layers: GitOps ConfigMap, PVC-stored config, K8s Secrets, and environment variables. This runbook explains how they interact.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Configuration Flow                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  GitOps (git repo)                                                       │
│  └── gitops/clusters/homelab/apps/frigate/configmap.yaml                │
│       │                                                                  │
│       │ Flux reconcile                                                   │
│       ▼                                                                  │
│  K8s ConfigMap (frigate-config)                                         │
│       │                                                                  │
│       │ Init container (ONLY if /config/config.yml missing)             │
│       ▼                                                                  │
│  PVC (/config/config.yml)  ◄─── This is what Frigate actually uses      │
│       │                                                                  │
│       │ Frigate reads at startup                                        │
│       ▼                                                                  │
│  Frigate Runtime                                                         │
│       │                                                                  │
│       │ Environment variable substitution                                │
│       │ (from K8s Secret frigate-credentials)                           │
│       ▼                                                                  │
│  Final Config (with real credentials)                                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Configuration Locations

| Location | Path | Purpose |
|----------|------|---------|
| GitOps ConfigMap | `gitops/clusters/homelab/apps/frigate/configmap.yaml` | Source of truth for git |
| K8s ConfigMap | `frigate-config` in namespace `frigate` | Template deployed by Flux |
| PVC Config | `/config/config.yml` inside pod | **Actual config Frigate uses** |
| K8s Secret | `frigate-credentials` in namespace `frigate` | Credentials (env vars) |
| Local .env | `proxmox/homelab/.env` | Backup of all credentials |

## Environment Variable Substitution

Frigate substitutes `{ENV_VAR}` placeholders at runtime.

### Supported Locations

| Config Section | Supports `{ENV_VAR}` | Notes |
|----------------|---------------------|-------|
| `mqtt.password` | ✅ Yes | |
| `go2rtc.streams` | ✅ Yes | |
| `cameras.*.ffmpeg.inputs.path` | ✅ Yes | |
| `cameras.*.onvif.user` | ❌ No | Must hardcode |
| `cameras.*.onvif.password` | ❌ No | Must hardcode |

### Current Environment Variables

Stored in K8s Secret `frigate-credentials`:

```bash
# View current secret keys
kubectl --kubeconfig ~/kubeconfig get secret frigate-credentials -n frigate -o jsonpath='{.data}' | jq -r 'keys[]'

# View decoded values
kubectl --kubeconfig ~/kubeconfig get secret frigate-credentials -n frigate -o jsonpath='{.data}' | jq -r 'to_entries[] | "\(.key): \(.value | @base64d)"'
```

| Variable | Used For |
|----------|----------|
| `FRIGATE_MQTT_PASSWORD` | MQTT broker auth |
| `FRIGATE_CAM_MJPEG_USER` | Old IP camera |
| `FRIGATE_CAM_MJPEG_PASS` | Old IP camera |
| `FRIGATE_CAM_TRENDNET_USER` | Trendnet camera |
| `FRIGATE_CAM_TRENDNET_PASS` | Trendnet camera |
| `FRIGATE_CAM_REOLINK_USER` | Reolink doorbell |
| `FRIGATE_CAM_REOLINK_PASS` | Reolink doorbell |
| `FRIGATE_CAM_LIVINGROOM_USER` | Living room camera |
| `FRIGATE_CAM_LIVINGROOM_PASS` | Living room camera |

## Init Container Behavior

The init container in `deployment.yaml`:

```yaml
initContainers:
  - name: init-config
    command:
      - /bin/sh
      - -c
      - |
        if [ ! -f /config/config.yml ]; then
          cp /config-template/config.yml /config/config.yml
        fi
```

**Key behavior:**
- Only copies ConfigMap to PVC **if config.yml doesn't exist**
- Once config exists on PVC, GitOps changes are **ignored**
- Manual edits to PVC config persist across restarts

## Updating Configuration

### Method 1: Edit PVC Config Directly (Immediate)

For quick changes that don't need to be in git:

```bash
# 1. Backup current config
kubectl --kubeconfig ~/kubeconfig exec -n frigate deployment/frigate -- \
  cat /config/config.yml > /tmp/frigate-config-backup-$(date +%Y%m%d-%H%M%S).yml

# 2. Edit locally
cp /tmp/frigate-config-backup-*.yml /tmp/frigate-config-new.yml
# Edit /tmp/frigate-config-new.yml

# 3. Upload
cat /tmp/frigate-config-new.yml | kubectl --kubeconfig ~/kubeconfig exec -i -n frigate deployment/frigate -- \
  tee /config/config.yml > /dev/null

# 4. Restart pod
kubectl --kubeconfig ~/kubeconfig delete pod -n frigate -l app=frigate
```

### Method 2: GitOps ConfigMap (Persistent)

For changes that should be version controlled:

```bash
# 1. Edit the ConfigMap
vim gitops/clusters/homelab/apps/frigate/configmap.yaml

# 2. Commit and push
git add gitops/clusters/homelab/apps/frigate/configmap.yaml
git commit -m "feat(frigate): add new camera"
git push

# 3. Force Flux reconcile
flux reconcile kustomization flux-system --with-source --kubeconfig ~/kubeconfig

# 4. Delete PVC config to force init container to copy new config
kubectl --kubeconfig ~/kubeconfig exec -n frigate deployment/frigate -- rm /config/config.yml

# 5. Restart pod
kubectl --kubeconfig ~/kubeconfig rollout restart deployment/frigate -n frigate
```

### Method 3: Update Credentials Only

To update secrets without touching config:

```bash
# Add new credential
kubectl --kubeconfig ~/kubeconfig patch secret frigate-credentials -n frigate --type='json' -p='[
  {"op": "add", "path": "/data/FRIGATE_CAM_NEW_USER", "value": "'$(echo -n 'admin' | base64)'"},
  {"op": "add", "path": "/data/FRIGATE_CAM_NEW_PASS", "value": "'$(echo -n 'password' | base64)'"}
]'

# Update existing credential
kubectl --kubeconfig ~/kubeconfig patch secret frigate-credentials -n frigate --type='json' -p='[
  {"op": "replace", "path": "/data/FRIGATE_CAM_REOLINK_PASS", "value": "'$(echo -n 'newpassword' | base64)'"}
]'

# Restart pod to pick up new secret values
kubectl --kubeconfig ~/kubeconfig delete pod -n frigate -l app=frigate
```

## Backup Locations

### Automatic Backups

None configured. Manual backups only.

### Manual Backup Procedure

```bash
# Backup PVC config
kubectl --kubeconfig ~/kubeconfig exec -n frigate deployment/frigate -- \
  cat /config/config.yml > /tmp/frigate-config-backup-$(date +%Y%m%d-%H%M%S).yml

# Backup secrets
kubectl --kubeconfig ~/kubeconfig get secret frigate-credentials -n frigate -o yaml > /tmp/frigate-credentials-backup-$(date +%Y%m%d-%H%M%S).yml
```

### Backup Locations

| What | Location | Notes |
|------|----------|-------|
| Config backups | `/tmp/frigate-config-backup-*.yml` | Manual, local only |
| Credentials backup | `proxmox/homelab/.env` | Gitignored, keep updated |
| GitOps source | `gitops/clusters/homelab/apps/frigate/` | In git |

### Restore Procedure

```bash
# Restore config from backup
cat /tmp/frigate-config-backup-YYYYMMDD-HHMMSS.yml | \
  kubectl --kubeconfig ~/kubeconfig exec -i -n frigate deployment/frigate -- \
  tee /config/config.yml > /dev/null

# Restart
kubectl --kubeconfig ~/kubeconfig delete pod -n frigate -l app=frigate
```

## Common Pitfalls

### 1. GitOps Changes Not Taking Effect

**Symptom**: Changed `configmap.yaml`, pushed, but Frigate still uses old config.

**Cause**: Init container only copies if config doesn't exist.

**Fix**:
```bash
kubectl --kubeconfig ~/kubeconfig exec -n frigate deployment/frigate -- rm /config/config.yml
kubectl --kubeconfig ~/kubeconfig rollout restart deployment/frigate -n frigate
```

### 2. Secret Changes Not Taking Effect

**Symptom**: Updated secret but Frigate uses old credentials.

**Cause**: Pod needs restart to pick up new env vars.

**Fix**:
```bash
kubectl --kubeconfig ~/kubeconfig delete pod -n frigate -l app=frigate
```

### 3. ONVIF Credentials Not Working

**Symptom**: ONVIF shows auth errors despite correct credentials.

**Cause**: ONVIF section doesn't support `{ENV_VAR}` substitution.

**Fix**: Hardcode credentials in ONVIF section:
```yaml
onvif:
  host: 192.168.1.10
  port: 8000
  user: admin          # NOT {FRIGATE_CAM_USER}
  password: realpass   # NOT {FRIGATE_CAM_PASS}
```

### 4. Lost Credentials After Secret Recreation

**Symptom**: Deleted and recreated secret, now missing some credentials.

**Cause**: Didn't backup all keys before deletion.

**Fix**: Restore from `proxmox/homelab/.env`:
```bash
# Check what's in .env
grep FRIGATE proxmox/homelab/.env

# Recreate secret with all values
kubectl --kubeconfig ~/kubeconfig delete secret frigate-credentials -n frigate
kubectl --kubeconfig ~/kubeconfig create secret generic frigate-credentials -n frigate \
  --from-literal=FRIGATE_MQTT_PASSWORD='...' \
  --from-literal=FRIGATE_CAM_MJPEG_USER='...' \
  # ... etc
```

## Keeping .env in Sync

After any credential change, update `proxmox/homelab/.env`:

```bash
# View current secrets
kubectl --kubeconfig ~/kubeconfig get secret frigate-credentials -n frigate -o jsonpath='{.data}' | \
  jq -r 'to_entries[] | "\(.key)=\(.value | @base64d)"'

# Compare with .env
grep FRIGATE proxmox/homelab/.env
```

The `.env` file is gitignored and serves as the single source of truth for credential recovery.
