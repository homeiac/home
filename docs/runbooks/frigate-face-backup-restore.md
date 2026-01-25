# Runbook: Frigate Face Training Data Backup and Restore

## Overview

Frigate face recognition requires training images for each person. These images are stored at `/media/frigate/clips/faces/` inside the Frigate pod. If the cluster is rebuilt or the PVC is lost, face recognition stops working until retrained.

This runbook documents the automated backup system and restore procedure.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Backup Flow (runs daily at 3am on pumped-piglet)                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  pumped-piglet                        Frigate (still-fawn)              │
│  ┌─────────────────┐                  ┌─────────────────┐               │
│  │ cron job        │───── HTTPS ─────▶│ /api/faces      │               │
│  │ 3am daily       │                  │ /clips/faces/*  │               │
│  └────────┬────────┘                  └─────────────────┘               │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────┐                                                    │
│  │ /local-3TB-backup/frigate-backups/                                   │
│  │ ├── frigate-faces-20260125.tar.gz                                    │
│  │ ├── frigate-faces-20260124.tar.gz                                    │
│  │ └── ... (last 7 days)                                                │
│  └─────────────────┘                                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Backup Details

| Setting | Value |
|---------|-------|
| **Schedule** | Daily at 3:00 AM UTC |
| **Location** | `pumped-piglet.maas:/local-3TB-backup/frigate-backups/` |
| **Retention** | Last 7 backups |
| **Script** | `/root/scripts/backup-frigate-faces.sh` |
| **Log** | `/var/log/frigate-face-backup.log` |
| **Method** | Frigate HTTP API (no kubectl required) |

### What Gets Backed Up

- All face training images from `/media/frigate/clips/faces/`
- Organized by person name (e.g., `Asha/`, `G/`)
- Format: WebP images, ~500KB total
- **Note**: Training images are NOT deleted after training - they persist

### Backup Script Location

**On pumped-piglet**: `/root/scripts/backup-frigate-faces.sh`
**In git repo**: `scripts/frigate/backup-faces-via-api.sh`

### Cron Entry (on pumped-piglet)

```cron
0 3 * * * /root/scripts/backup-frigate-faces.sh >> /var/log/frigate-face-backup.log 2>&1
```

---

## Verify Backup is Working

### Check Latest Backup

```bash
ssh root@pumped-piglet.maas "ls -lh /local-3TB-backup/frigate-backups/"
```

Expected output:
```
-rw-r--r-- 1 root root 479K Jan 25 06:58 frigate-faces-20260125.tar.gz
-rw-r--r-- 1 root root 479K Jan 24 06:51 frigate-faces-20260124.tar.gz
```

### Check Backup Log

```bash
ssh root@pumped-piglet.maas "tail -20 /var/log/frigate-face-backup.log"
```

### Check Cron is Configured

```bash
ssh root@pumped-piglet.maas "crontab -l | grep frigate"
```

### Manual Backup (if needed)

```bash
ssh root@pumped-piglet.maas "/root/scripts/backup-frigate-faces.sh"
```

---

## Restore Procedure

### When to Restore

- After cluster rebuild
- After Frigate PVC is deleted/recreated
- After VM 108 (K3s still-fawn) is recreated
- If face recognition stops working and images are missing

### Prerequisites

- Mac with kubectl access (`~/kubeconfig`)
- SSH access to pumped-piglet.maas
- Frigate pod running

### Quick Restore (Most Recent Backup)

```bash
cd ~/code/home
./scripts/frigate/restore-faces.sh
```

### Restore Specific Date

```bash
./scripts/frigate/restore-faces.sh 20260124
```

### What the Restore Script Does

1. Finds most recent backup (or specified date)
2. Downloads tarball from pumped-piglet
3. Extracts face images locally
4. Uploads each image via Frigate API (`POST /api/faces/{name}`)
5. Verifies restore by querying `/api/faces`

### Manual Restore (if script fails)

```bash
# 1. Download backup
scp root@pumped-piglet.maas:/local-3TB-backup/frigate-backups/frigate-faces-20260125.tar.gz /tmp/

# 2. Extract
cd /tmp && tar xzf frigate-faces-20260125.tar.gz

# 3. Upload via API
FRIGATE_URL="https://frigate.app.home.panderosystems.com"
for face_dir in faces-20260125/*/; do
    name=$(basename "$face_dir")
    for img in "$face_dir"/*.webp; do
        curl -sk -X POST "${FRIGATE_URL}/api/faces/${name}" -F "file=@${img}"
    done
done

# 4. Verify
curl -sk "${FRIGATE_URL}/api/faces" | jq
```

### Verify Restore

```bash
# Via API
curl -sk https://frigate.app.home.panderosystems.com/api/faces | jq

# Via kubectl
export KUBECONFIG=~/kubeconfig
kubectl exec -n frigate deploy/frigate -- ls -la /media/frigate/clips/faces/
```

---

## Troubleshooting

### Backup Not Running

1. Check cron is configured:
   ```bash
   ssh root@pumped-piglet.maas "crontab -l"
   ```

2. Check script exists and is executable:
   ```bash
   ssh root@pumped-piglet.maas "ls -la /root/scripts/backup-frigate-faces.sh"
   ```

3. Run manually to see errors:
   ```bash
   ssh root@pumped-piglet.maas "/root/scripts/backup-frigate-faces.sh"
   ```

### Frigate API Unreachable from pumped-piglet

```bash
# Test connectivity
ssh root@pumped-piglet.maas "curl -sk https://frigate.app.home.panderosystems.com/api/version"
```

If fails:
- Check Traefik is running
- Check Frigate pod is running
- Check DNS resolution

### Restore Fails with "No frigate pod found"

Frigate pod may not be running. Check:

```bash
export KUBECONFIG=~/kubeconfig
kubectl get pods -n frigate
kubectl describe pod -n frigate -l app=frigate
```

### Face Recognition Not Working After Restore

1. Verify images were uploaded:
   ```bash
   curl -sk https://frigate.app.home.panderosystems.com/api/faces | jq
   ```

2. Check Frigate logs for face recognition errors:
   ```bash
   kubectl logs -n frigate deploy/frigate | grep -i face
   ```

3. Ensure `face_recognition.enabled: true` in config

---

## Redeploy Backup Script

If pumped-piglet is rebuilt or script is lost:

```bash
# From Mac
scp ~/code/home/scripts/frigate/backup-faces-via-api.sh \
    root@pumped-piglet.maas:/root/scripts/backup-frigate-faces.sh

ssh root@pumped-piglet.maas "chmod +x /root/scripts/backup-frigate-faces.sh"

# Reinstall cron
ssh root@pumped-piglet.maas "(crontab -l 2>/dev/null | grep -v backup-frigate-faces; echo '0 3 * * * /root/scripts/backup-frigate-faces.sh >> /var/log/frigate-face-backup.log 2>&1') | crontab -"
```

---

## Related Files

| File | Location | Purpose |
|------|----------|---------|
| Backup script (git) | `scripts/frigate/backup-faces-via-api.sh` | Source for backup script |
| Backup script (deployed) | `pumped-piglet:/root/scripts/backup-frigate-faces.sh` | Running backup script |
| Restore script | `scripts/frigate/restore-faces.sh` | Restore from backup |
| Backup Mac script | `scripts/frigate/backup-faces.sh` | Alternative backup via kubectl |
| Backups | `pumped-piglet:/local-3TB-backup/frigate-backups/` | Backup storage |

---

## Why This Architecture?

### Why API-based backup?

- **No kubectl on Proxmox hosts**: pumped-piglet doesn't have kubectl installed
- **No SSH to K3s VMs**: K3s VMs don't run SSH server
- **API is always available**: Frigate exposes faces via HTTP API
- **Runs without Mac**: Backup runs automatically even when Mac is off

### Why not backup the PVC directly?

- Frigate PVC is inside K3s VM on still-fawn
- If still-fawn dies, both Frigate AND its PVC are gone
- API-based backup stores data on separate physical machine (pumped-piglet)

### Why pumped-piglet?

- Always on (hosts PBS and other critical services)
- Has 3TB ZFS storage for backups
- Network access to Frigate via Traefik

---

## Tags

frigate, face-recognition, backup, restore, training-data, pumped-piglet, 3tb-backup, api, runbook, disaster-recovery
