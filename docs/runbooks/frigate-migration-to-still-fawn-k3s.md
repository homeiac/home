# Frigate Migration: pumped-piglet → still-fawn (K3s)

**Date:** 2026-02-14
**Status:** Planning Phase (Phase 3)
**Objective:** Migrate Frigate NVR from pumped-piglet K3s node to still-fawn K3s node with PCIe Coral TPU

---

## Overview

This runbook migrates Frigate from `k3s-vm-pumped-piglet-gpu` to `k3s-vm-still-fawn`. This reduces concentration risk on pumped-piglet and moves Frigate to dedicated NVR hardware with:
- **PCIe Coral TPU** (faster than USB, already owned)
- **AMD RX 580 GPU** (VAAPI for hardware encoding)
- **SSD storage** (faster than HDD recordings)

**Current State:**
- Frigate runs on pumped-piglet (RTX 3070 + USB Coral TPU)
- RTX 3070 is overkill for Frigate - it only needs NVDEC/VAAPI for decode
- USB Coral can be slow under heavy load compared to PCIe

**Target State:**
- Frigate runs on still-fawn (AMD RX 580 VAAPI + PCIe Coral TPU)
- pumped-piglet freed for Ollama/Stable Diffusion/GPU-heavy workloads
- Dedicated NVR node with SSD recordings

---

## Prerequisites

### Hardware

- [ ] PCIe Coral TPU installed in still-fawn
- [ ] AMD RX 580 GPU (already in still-fawn)
- [ ] Both devices passed through to K3s VM (VMID 108)

### Cluster

- [ ] still-fawn K3s node is healthy and stable (Phase 1 - 1-2 weeks)
- [ ] still-fawn has sufficient storage for recordings (700Gi allocated)
- [ ] Flux GitOps is reconciling normally

### Backups

- [ ] Face training data backed up (see `frigate-face-backup-restore.md`)
- [ ] Current recordings backed up if needed (usually not critical)

---

## Hardware Inventory

### still-fawn (target)

| Component | Details |
|-----------|---------|
| CPU | Intel i5-4460 (4 cores) |
| RAM | 32GB |
| GPU | AMD Radeon RX 580 |
| Coral TPU | PCIe (to be installed) |
| Storage | 2TB SSD mirror (rpool) |

### Current VM 108 Configuration

```bash
# Check current PCI passthrough
ssh root@still-fawn.maas 'qm config 108 | grep -E "(hostpci|pci)"'
```

Expected: AMD RX 580 passthrough already configured.

---

## Architecture

### Current (pumped-piglet)

```
pumped-piglet K3s VM (105)
├── NVIDIA RTX 3070 (PCI passthrough)
├── USB Coral TPU (physically on pumped-piglet)
└── Frigate deployment
    ├── nodeSelector: k3s-vm-pumped-piglet-gpu
    ├── runtimeClassName: nvidia
    └── PVCs: frigate-config, frigate-media
```

### Target (still-fawn)

```
still-fawn K3s VM (108)
├── AMD RX 580 (PCI passthrough, VAAPI)
├── PCIe Coral TPU (PCI passthrough)
└── Frigate deployment
    ├── nodeSelector: k3s-vm-still-fawn
    ├── NO runtimeClassName (VAAPI, not NVIDIA)
    └── PVCs: frigate-config-still-fawn, frigate-media-still-fawn
```

---

## Storage Plan

### still-fawn Storage Allocation

With PBS datastore on the physically-moved 3TB HDD (see `pbs-migration-to-still-fawn.md`), the 2TB SSD mirror is available for high-performance workloads:

| Use Case | Storage | Allocation |
|----------|---------|------------|
| K3s VM root (existing) | SSD mirror | 40GB |
| PBS LXC root | SSD mirror | 20GB |
| Frigate config PVC | SSD mirror | 1Gi |
| Frigate media PVC | SSD mirror | 1TB |
| Headroom | SSD mirror | ~700GB |
| **PBS datastore** | **3TB HDD** | **2.7TB** |

**Benefits of SSD for Frigate recordings:**
- Faster write speeds for multiple camera streams
- Better random I/O for event lookups
- More headroom than the original 200Gi on pumped-piglet

### PVC Strategy

Create new PVCs on still-fawn storage, then migrate data:
- `frigate-config-still-fawn` (1Gi)
- `frigate-media-still-fawn` (700Gi)

---

## Procedure

### Phase 1: Hardware Installation (Physical)

#### 1.1 Power Down still-fawn

```bash
# Shutdown K3s VM first
ssh root@still-fawn.maas 'qm shutdown 108'

# Wait for clean shutdown, then power off host
ssh root@still-fawn.maas 'shutdown -h now'
```

#### 1.2 Install PCIe Coral TPU

1. Open still-fawn chassis
2. Install Coral PCIe card in available slot
3. Close chassis and power on

#### 1.3 Verify Coral Detection on Host

```bash
ssh root@still-fawn.maas

# Check PCIe device
lspci | grep -i "Global Unichip"
# Expected: xx:00.0 System peripheral: Global Unichip Corp. Coral Edge TPU

# Check IOMMU group
for d in /sys/kernel/iommu_groups/*/devices/*; do
    n=${d#*/iommu_groups/*}; n=${n%%/*}
    printf 'IOMMU Group %s ' "$n"
    lspci -nns "${d##*/}"
done | grep -i "Global"
```

Record the IOMMU group and PCI address.

#### 1.4 Add Coral TPU to VM Passthrough

```bash
ssh root@still-fawn.maas

VMID=108
CORAL_PCI="0000:xx:00.0"  # Replace with actual PCI address

# Add Coral to VM
qm set $VMID --hostpci1 $CORAL_PCI,pcie=1

# Verify config
qm config $VMID | grep hostpci
```

#### 1.5 Start VM and Verify Devices

```bash
# Start VM
ssh root@still-fawn.maas 'qm start 108'

# Wait for boot
sleep 60

# Verify devices inside VM
scripts/k3s/exec-still-fawn.sh "lspci | grep -iE 'coral|amd|radeon'"

# Expected:
# xx:00.0 VGA compatible controller: Advanced Micro Devices...
# xx:00.0 System peripheral: Global Unichip Corp. Coral Edge TPU
```

#### 1.6 Verify Coral Device Node

```bash
scripts/k3s/exec-still-fawn.sh "ls -la /dev/apex_*"
# Expected: /dev/apex_0

scripts/k3s/exec-still-fawn.sh "ls -la /dev/dri/"
# Expected: renderD128 (for VAAPI)
```

### Phase 2: Create Storage on still-fawn

#### 2.1 Expand VM Disk (if needed)

The K3s VM currently has ~40GB. Need 700Gi+ for Frigate media.

```bash
ssh root@still-fawn.maas

# Check current VM disk
qm config 108 | grep scsi

# Resize if needed (add 800GB)
qm resize 108 scsi0 +800G
```

#### 2.2 Extend Filesystem in VM

```bash
scripts/k3s/exec-still-fawn.sh bash -c '
# Extend partition (Ubuntu cloud-init auto-resizes root)
sudo growpart /dev/sda 2
sudo resize2fs /dev/sda2
df -h
'
```

#### 2.3 Create StorageClass for still-fawn

Create a StorageClass that provisions on still-fawn's local storage.

```yaml
# gitops/clusters/homelab/apps/frigate/storageclass-still-fawn.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: frigate-still-fawn-storage
provisioner: rancher.io/local-path
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
parameters:
  nodePath: /var/local-path-provisioner
```

**Note:** May need to use `local-path` provisioner node affinity or manual PV/PVC binding.

### Phase 3: GitOps Changes

#### 3.1 Create New Deployment Variant

Create `deployment-still-fawn.yaml` that targets still-fawn:

```yaml
# Key differences from current deployment.yaml:

spec:
  template:
    spec:
      # NO runtimeClassName (VAAPI, not NVIDIA)
      # runtimeClassName: nvidia  # REMOVED

      nodeSelector:
        kubernetes.io/hostname: k3s-vm-still-fawn  # CHANGED

      containers:
        - name: frigate
          env:
            # REMOVE NVIDIA vars, add LIBVA for VAAPI
            - name: LIBVA_DRIVERS_PATH
              value: "/usr/lib/x86_64-linux-gnu/dri"
            - name: LIBVA_DRIVER_NAME
              value: "radeonsi"

          volumeMounts:
            # Coral device (PCIe)
            - name: apex
              mountPath: /dev/apex_0

      volumes:
        # PCIe Coral device
        - name: apex
          hostPath:
            path: /dev/apex_0
            type: CharDevice
```

#### 3.2 Update Frigate Config for VAAPI

Update `configmap.yaml` to use VAAPI instead of NVDEC:

```yaml
# In ffmpeg section:
ffmpeg:
  hwaccel_args:
    - -hwaccel
    - vaapi
    - -hwaccel_device
    - /dev/dri/renderD128
    - -hwaccel_output_format
    - vaapi
```

#### 3.3 Create New PVCs

```yaml
# gitops/clusters/homelab/apps/frigate/pvc-still-fawn.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: frigate-config-still-fawn
  namespace: frigate
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: frigate-still-fawn-storage
  resources:
    requests:
      storage: 1Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: frigate-media-still-fawn
  namespace: frigate
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: frigate-still-fawn-storage
  resources:
    requests:
      storage: 1Ti
```

### Phase 4: Data Migration

#### 4.1 Scale Down Frigate on pumped-piglet

```bash
kubectl scale deployment frigate -n frigate --replicas=0
```

#### 4.2 Migrate Face Training Data

```bash
# Get face backup from pumped-piglet
ssh root@pumped-piglet.maas "cat /local-3TB-backup/frigate-backups/frigate-faces-latest.tar.gz" > /tmp/faces.tar.gz

# Will restore after new Frigate is running (see frigate-face-backup-restore.md)
```

#### 4.3 Migrate Database (Optional)

If you want to preserve events history:

```bash
# Copy from pumped-piglet Frigate PVC
kubectl cp frigate/frigate-xxx:/config/frigate.db /tmp/frigate.db

# Will copy to new Frigate after deployment
```

### Phase 5: Deploy on still-fawn

#### 5.1 Update Kustomization

```yaml
# gitops/clusters/homelab/apps/frigate/kustomization.yaml
resources:
  - namespace.yaml
  - configmap.yaml
  - secrets/frigate-credentials.sops.yaml
  - pvc-still-fawn.yaml           # NEW
  - storageclass-still-fawn.yaml  # NEW
  - deployment-still-fawn.yaml    # NEW (replaces deployment.yaml)
  - service.yaml
  - ingress.yaml
  - ingressroute-tcp.yaml
```

#### 5.2 Commit and Push

```bash
git add gitops/clusters/homelab/apps/frigate/
git commit -m "feat(frigate): migrate to still-fawn with PCIe Coral + VAAPI"
git push
```

#### 5.3 Reconcile Flux

```bash
flux reconcile kustomization flux-system --with-source
```

#### 5.4 Monitor Deployment

```bash
kubectl get pods -n frigate -w
kubectl logs -n frigate -l app=frigate -f
```

### Phase 6: Verification

#### 6.1 Check Coral TPU Detection

```bash
kubectl exec -n frigate deploy/frigate -- cat /dev/shm/logs/frigate/current | grep -i TPU
```

Expected: "EdgeTPU" or "Coral" detected.

#### 6.2 Check VAAPI Encoding

```bash
kubectl exec -n frigate deploy/frigate -- ffmpeg -hwaccel vaapi -hwaccel_device /dev/dri/renderD128 -hwaccel_output_format vaapi -i /dev/null -f null - 2>&1 | head -20
```

Should show VAAPI initialization success.

#### 6.3 Check Camera Streams

1. Open Frigate web UI: https://frigate.app.home.panderosystems.com
2. Verify all cameras streaming
3. Check for object detection (person, car, etc.)
4. Verify recordings are saving

#### 6.4 Restore Face Training Data

See `docs/runbooks/frigate-face-backup-restore.md` for restore procedure.

---

## Rollback Plan

**If migration fails:**

1. Revert GitOps changes:
   ```bash
   git revert HEAD
   git push
   flux reconcile kustomization flux-system --with-source
   ```

2. Frigate automatically deploys back to pumped-piglet

3. Clean up still-fawn PVCs:
   ```bash
   kubectl delete pvc frigate-config-still-fawn frigate-media-still-fawn -n frigate
   ```

**Data safety:** Original PVCs on pumped-piglet remain until explicitly deleted.

---

## Post-Migration Tasks

### Update Backup Scripts

Update face backup script to point to still-fawn if using direct API access:

```bash
# Old: https://frigate.app.home.panderosystems.com (unchanged - uses ingress)
# No change needed if using ingress
```

### Retire Frigate LXC 113 on fun-bedbug

After stable operation (1 week):

```bash
ssh root@fun-bedbug.maas
pct stop 113
pct destroy 113 --purge
```

### Free pumped-piglet USB Coral

The USB Coral TPU on pumped-piglet is no longer needed for Frigate.
Options:
1. Remove from pumped-piglet VM passthrough
2. Use for other workloads (e.g., TensorFlow Lite)
3. Keep as spare

---

## Troubleshooting

### Coral TPU Not Detected

```bash
# Check device node exists
scripts/k3s/exec-still-fawn.sh "ls -la /dev/apex_*"

# Check driver loaded
scripts/k3s/exec-still-fawn.sh "lsmod | grep gasket"

# May need gasket driver installed in VM
scripts/k3s/exec-still-fawn.sh "sudo apt install gasket-dkms libedgetpu1-std"
```

### VAAPI Not Working

```bash
# Check DRI device
scripts/k3s/exec-still-fawn.sh "ls -la /dev/dri/"

# Test VAAPI
scripts/k3s/exec-still-fawn.sh "vainfo"
```

May need `libva` packages in Frigate container or sidecar.

### Pod Can't Access Devices

Check privileged mode and device mounts:

```yaml
securityContext:
  privileged: true
```

Verify volume mounts for `/dev/apex_0` and `/dev/dri`.

### Recordings Not Saving

1. Check PVC is bound: `kubectl get pvc -n frigate`
2. Check storage on still-fawn: `scripts/k3s/exec-still-fawn.sh "df -h"`
3. Check Frigate logs for I/O errors

---

## Related Documentation

- `docs/runbooks/frigate-face-backup-restore.md` - Face training data backup
- `docs/runbooks/proxmox-gpu-passthrough-k3s-node.md` - GPU passthrough setup
- `docs/runbooks/frigate-tpu-troubleshooting.md` - Coral TPU debugging
- `docs/rca/2026-02-12-frigate-coral-tpu-instability.md` - TPU stability issues

---

## Tags

frigate, nvr, migration, still-fawn, pumped-piglet, coral, tpu, pcie, vaapi, amd, gpu, k3s, kubernetes, recordings, face-recognition
