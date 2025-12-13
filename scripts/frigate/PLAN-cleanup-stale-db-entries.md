# Fix Frigate VirtioFS I/O Bottleneck

## Status: IN PROGRESS

## Problem Statement

Frigate K8s deployment has constant 12MB/s disk I/O on the 20TB USB drive, causing:
- Load average of 15+ on pumped-piglet host
- ZFS zvol threads consuming CPU

## Root Cause Analysis

### Investigation Timeline

1. **Initial symptom**: High CPU (1188m) on Frigate pod, 15+ load on host
2. **First finding**: Detection was disabled on all cameras (from PBS database import)
3. **Second finding**: `/import` VirtioFS mount was `readOnly: true`
4. **Third finding**: recording_cleanup thread crashing with "Read-only file system" errors
5. **Fourth finding**: Symlinks in `/media/frigate/recordings/` pointing to `/import/recordings/`
6. **Root cause**: VirtioFS mount + USB drive creates I/O bottleneck

### Architecture Problem

```
Frigate Pod
    ↓ reads /media/frigate/recordings/2025-12-06
    ↓ (symlink to /import/recordings/2025-12-06)
VirtioFS mount (/import)
    ↓
QEMU VirtioFS daemon
    ↓
ZFS zvol on USB drive (local-20TB-zfs)
    ↓
USB 3.0 Seagate 20TB
```

Each recording access traverses this entire stack, causing constant I/O.

### What Was Done (Partial Fix)

1. ✅ Changed `readOnly: true` to `readOnly: false` in deployment
2. ✅ Frigate cleanup deleted old recordings (May, Aug, Nov entries)
3. ✅ Removed broken symlinks for deleted dates
4. ⚠️ Removed symlinks for Dec 6-11 (within retention) - data lost
5. ❌ VirtioFS mount still in deployment - still causing overhead

### Current State

- Recordings: Only Dec 12-13 (local, no symlinks)
- Symlinks: All removed
- VirtioFS mount: Still attached but not used
- I/O: Still checking (may have dropped)

---

## Solution: Fresh Start - Remove VirtioFS + Reset Database

Since we're switching to local K3s VM storage and accepting loss of old recordings:

### Phase 1: Backup Current Database

```bash
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- \
  cp /config/frigate.db /config/frigate.db.pre-reset-backup
```

### Phase 2: Remove VirtioFS from Deployment

**Changes to `k8s/frigate-016/deployment.yaml`**:

1. Remove volumeMount:
```yaml
# DELETE these lines (76-79):
            # Old Frigate recordings for import (read-only)
            - name: old-recordings
              mountPath: /import
              readOnly: false
```

2. Remove volume:
```yaml
# DELETE these lines (120-124):
        # Old Frigate recordings via virtiofs from host
        - name: old-recordings
          hostPath:
            path: /mnt/frigate-import/frigate
            type: Directory
```

### Phase 3: Delete Database and Apply Deployment

```bash
# Delete database (Frigate will create fresh one on startup)
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- \
  rm /config/frigate.db

# Apply deployment changes
KUBECONFIG=~/kubeconfig kubectl apply -f k8s/frigate-016/deployment.yaml

# Restart to pick up changes and create fresh DB
KUBECONFIG=~/kubeconfig kubectl rollout restart deployment/frigate -n frigate
```

### Phase 4: Verify I/O Dropped

```bash
# Check I/O
ssh root@pumped-piglet.maas "zpool iostat local-20TB-zfs 3 3"
# Expected: Read I/O drops to near 0 (only VM disk I/O remains)

# Check load
ssh root@pumped-piglet.maas "uptime"
# Expected: Load drops from 15+ to <5

# Check Frigate
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- \
  curl -s http://localhost:5000/api/stats | jq '.detectors'
```

### Phase 5: PBS Backup Causing I/O (ACTUAL ROOT CAUSE)

**Root cause found**: A PBS backup job is running for VM 105, reading the 18TB USB-attached zvol (scsi1).

```
lock: backup
task UPID:pumped-piglet:001854D2:1B2ADD95:693C976B:vzdump:105:root@pam:
```

The K3s VM (105) has `scsi1` attached to `local-20TB-zfs/vm-105-disk-0` (18TB USB zvol). The backup is reading this entire disk even though nothing inside the VM uses it.

**Current VM disk layout**:
| Device | Proxmox Disk | Pool | Size | Status |
|--------|--------------|------|------|--------|
| scsi0 (sda) | vm-105-disk-1 | local-2TB-zfs (NVMe) | 1800G | In use - root/storage |
| scsi1 (sdb) | vm-105-disk-0 | local-20TB-zfs (USB) | 18TB | **NOT MOUNTED - causing I/O** |

**frigate-media is already on NVMe** (`/dev/sda1`). The USB disk is unused.

**Solution**: Detach scsi1 from VM 105

**Implementation** (requires VM reboot):
```bash
# On pumped-piglet.maas
# 1. Shutdown VM
qm shutdown 105

# 2. Detach the USB disk
qm set 105 --delete scsi1

# 3. Start VM
qm start 105
```

**Alternative** (no reboot - hot remove):
```bash
# Check if hot-unplug is supported
qm monitor 105 -cmd "info block"
# If supported:
qm monitor 105 -cmd "device_del scsi1"
```

### Phase 6: Optional - Unmount VirtioFS on Host

If VirtioFS is no longer needed:
```bash
# On K3s VM
sudo umount /mnt/frigate-import

# Remove from fstab if present
sudo sed -i '/frigate-import/d' /etc/fstab
```

---

## Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Disk Read I/O (20TB) | 12-13 MB/s | ~0 MB/s |
| Host Load Average | 15+ | <5 |
| Recordings | Via symlinks to USB | Local to VM disk |
| VirtioFS | Mounted, causing overhead | Removed |

---

## Trade-offs

**Lost**:
- Old recordings from Dec 6-11 (were on VirtioFS/USB)
- Historical data from May, Aug, Nov (already deleted by retention)

**Gained**:
- 60%+ reduction in host load
- No VirtioFS overhead
- Simpler architecture (recordings on local VM disk)
- Faster recording access

---

## Files to Modify

| File | Change |
|------|--------|
| `k8s/frigate-016/deployment.yaml` | Remove old-recordings volumeMount and volume |

---

## Rollback Plan

If issues occur, re-add the VirtioFS mount:
```bash
git checkout k8s/frigate-016/deployment.yaml
KUBECONFIG=~/kubeconfig kubectl apply -f k8s/frigate-016/deployment.yaml
```

---

## Script

**Script**: `scripts/frigate/21-remove-virtiofs-mount.sh`
