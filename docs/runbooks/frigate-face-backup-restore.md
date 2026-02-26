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
│  pumped-piglet                        Frigate (pumped-piglet K3s VM)    │
│  ┌─────────────────┐                  ┌─────────────────┐               │
│  │ cron job        │───── HTTPS ─────▶│ /api/faces      │               │
│  │ 3am daily       │                  │ /clips/faces/*  │               │
│  └────────┬────────┘                  └─────────────────┘               │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────┐                                                    │
│  │ /local-3TB-backup/frigate-backups/                                   │
│  │ ├── frigate-faces-20260206.tar.gz                                    │
│  │ ├── frigate-faces-20260205.tar.gz                                    │
│  │ └── ... (last 7 days)                                                │
│  └─────────────────┘                                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

> **Note**: Frigate was migrated from still-fawn to pumped-piglet on 2026-02-08.
> The backup architecture remains the same - backups stored on pumped-piglet's
> 3TB ZFS, separate from the K3s VM storage.

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
- After Frigate migration to different node (e.g., still-fawn → pumped-piglet)
- After K3s VM is recreated
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

**Method 1: Direct file copy (recommended)**

The Frigate API may not accept bulk uploads reliably. Copy files directly to the pod:

```bash
# 1. Download and extract backup
scp root@pumped-piglet.maas:/local-3TB-backup/frigate-backups/frigate-faces-20260206.tar.gz /tmp/
cd /tmp && rm -rf faces-restore && mkdir faces-restore
tar xzf frigate-faces-20260206.tar.gz -C faces-restore --strip-components=1

# 2. Create tarball and copy to pod
tar czf /tmp/faces-all.tar.gz -C /tmp/faces-restore .
export KUBECONFIG=~/kubeconfig
POD=$(kubectl get pod -n frigate -l app=frigate -o jsonpath='{.items[0].metadata.name}')
kubectl cp /tmp/faces-all.tar.gz frigate/${POD}:/tmp/faces-all.tar.gz

# 3. Extract in pod
kubectl exec -n frigate ${POD} -- bash -c "cd /media/frigate/clips/faces && rm -rf * && tar xzf /tmp/faces-all.tar.gz && rm -f ._* ._.* && ls -la"

# 4. Verify
curl -sk https://frigate.app.home.panderosystems.com/api/faces | jq
```

**Method 2: Via API (may be unreliable)**

```bash
FRIGATE_URL="https://frigate.app.home.panderosystems.com"
for face_dir in /tmp/faces-restore/*/; do
    name=$(basename "$face_dir")
    for img in "$face_dir"/*.webp; do
        curl -sk -X POST "${FRIGATE_URL}/api/faces/${name}" -F "file=@${img}"
    done
done
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

- Frigate PVC is inside K3s VM (local-path storage)
- If the node dies, both Frigate AND its PVC are gone
- API-based backup stores data on separate ZFS storage (survives node failure)
- **Proven in practice**: 2026-02-08 still-fawn failure - face data restored from backup

### Why pumped-piglet?

- Always on (hosts PBS and other critical services)
- Has 3TB ZFS storage for backups
- Network access to Frigate via Traefik

---

## Incident History

### 2026-02-08: still-fawn Node Failure

**What happened**: The still-fawn Proxmox host went offline, taking the K3s VM (108) and Frigate with it.

**Impact**: Frigate was migrated to pumped-piglet. The old PVC with face training data was lost.

**Recovery**:
1. Backups existed on pumped-piglet's 3TB ZFS: `frigate-faces-20260206.tar.gz` (2.6MB)
2. Direct file copy method used (API restore was unreliable)
3. All 580 training images restored (Adil: 36, Asha: 153, G: 380, Waffles: 11)
4. Face recognition operational within minutes of restore

**Lesson**: The separate-storage backup strategy worked exactly as designed.

---

---

## Recordings Backup

### Overview

Frigate recordings are stored in the `frigate-media` PVC at `/media/frigate/recordings/`. Unlike face data (which uses API backup), recordings are backed up via file-based streaming.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Recordings Backup Flow (manual or scheduled from Mac)                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Mac                             K3s (pumped-piglet VM 105)             │
│  ┌─────────────────┐             ┌─────────────────┐                    │
│  │ backup script   │──kubectl──▶│ Frigate pod     │                    │
│  │ (streaming tar) │             │ /media/frigate/ │                    │
│  └────────┬────────┘             │   recordings/   │                    │
│           │                      └─────────────────┘                    │
│           │ ssh pipe                                                    │
│           ▼                                                             │
│  pumped-piglet Proxmox Host                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐
│  │  /local-3TB-backup/frigate-recordings/                              │
│  │  ├── backyard_hd/                                                   │
│  │  │   └── 2026-02-08/00/xx.mp4, 01/xx.mp4, ...                       │
│  │  ├── driveway/                                                      │
│  │  └── ... (per camera, per day, per hour)                            │
│  └─────────────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────────────┘
```

### Backup Details

| Setting | Value |
|---------|-------|
| **Schedule** | Manual (or add to Mac crontab for automation) |
| **Location** | `pumped-piglet.maas:/local-3TB-backup/frigate-recordings/` |
| **Retention** | 7 days (matching Frigate's default) |
| **Script** | `scripts/frigate/backup-recordings-mac.sh` |
| **Size** | Typically 1-50GB depending on motion activity |

### Manual Backup

```bash
cd ~/code/home
./scripts/frigate/backup-recordings-mac.sh
```

Or dry run to preview:

```bash
./scripts/frigate/backup-recordings-mac.sh --dry-run
```

### Restore Recordings

```bash
# Restore all cameras
./scripts/frigate/restore-recordings.sh

# Restore specific camera
./scripts/frigate/restore-recordings.sh backyard_hd

# Preview what would be restored
./scripts/frigate/restore-recordings.sh --dry-run
```

### GitOps CronJob (Future)

A K8s CronJob approach is prepared but requires VM storage passthrough:

**Files**:
- `gitops/clusters/homelab/apps/frigate/backup-storage-class.yaml`
- `gitops/clusters/homelab/apps/frigate/backup-pvc.yaml`
- `gitops/clusters/homelab/apps/frigate/backup-recordings-cronjob.yaml`

**Prerequisite**: VM 105 needs 3TB mount via virtio-fs or 9p:
```bash
# On pumped-piglet
qm set 105 --virtiofs1 local-3TB-backup:/mnt/3tb-backup,cache=auto
# Requires VM restart
```

Then uncomment the resources in `gitops/clusters/homelab/apps/frigate/kustomization.yaml`.

### Verify Backup

```bash
# Check backup exists
ssh root@pumped-piglet.maas "ls -la /local-3TB-backup/frigate-recordings/"

# Check backup size
ssh root@pumped-piglet.maas "du -sh /local-3TB-backup/frigate-recordings/"

# Check per-camera breakdown
ssh root@pumped-piglet.maas "du -sh /local-3TB-backup/frigate-recordings/*/"
```

---

## Comparison: Faces vs Recordings Backup

| Aspect | Faces | Recordings |
|--------|-------|------------|
| **Size** | ~3MB | ~1-50GB |
| **Method** | API download (curl) | File streaming (tar+kubectl) |
| **Schedule** | Host cron at 3 AM | Manual or Mac cron |
| **Location** | `/local-3TB-backup/frigate-backups/` | `/local-3TB-backup/frigate-recordings/` |
| **Restore** | API upload or kubectl cp | tar stream via kubectl |
| **Critical?** | Yes (AI training data) | Medium (can be regenerated) |

---

## Tags

frigate, face-recognition, recordings, backup, restore, training-data, pumped-piglet, 3tb-backup, api, runbook, disaster-recovery
