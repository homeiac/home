# Prometheus Storage Separation Runbook

**Purpose**: Separate Prometheus storage from shared paths to dedicated isolated storage
**Duration**: ~15 minutes
**Impact**: Prometheus restart, brief monitoring gap

---

## Prerequisites

- SSH access to Proxmox host (`pumped-piglet.maas`)
- `kubectl` access to K3s cluster
- `flux` CLI installed
- Git push access to homelab repo

---

## Quick Reference

| Component | Before | After |
|-----------|--------|-------|
| StorageClass | `prometheus-2tb-storage` | `prometheus-storage` |
| PV | `prometheus-2tb-pv` | `prometheus-pv` |
| Path | `/mnt/smb_data/prometheus` | `/mnt/prometheus` |
| Capacity | 1000Gi | 500Gi |

---

## Step 1: Create Mount Point on VM

```bash
# Get VMID from inventory (pumped-piglet hosts VMID 105)
cat proxmox/inventory.txt | grep k3s-vm-pumped-piglet

# Create directory via qm guest exec
ssh root@pumped-piglet.maas "qm guest exec 105 -- mkdir -p /mnt/prometheus"

# Set ownership (Prometheus runs as 1000:2000)
ssh root@pumped-piglet.maas "qm guest exec 105 -- chown 1000:2000 /mnt/prometheus"

# Verify
ssh root@pumped-piglet.maas "qm guest exec 105 -- ls -la /mnt/"
```

---

## Step 2: Update GitOps Manifests

### 2.1 Update prometheus-storage-class.yaml

**File**: `gitops/clusters/homelab/infrastructure/monitoring/prometheus-storage-class.yaml`

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: prometheus-storage
provisioner: rancher.io/local-path
parameters:
  nodePath: /mnt/prometheus
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: prometheus-pv
spec:
  capacity:
    storage: 500Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: prometheus-storage
  local:
    path: /mnt/prometheus
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values:
                - k3s-vm-pumped-piglet-gpu
```

### 2.2 Update monitoring-values.yaml

**File**: `gitops/clusters/homelab/infrastructure/monitoring/monitoring-values.yaml`

Change `storageClassName`:
```yaml
prometheus:
  prometheusSpec:
    storageSpec:
      volumeClaimTemplate:
        spec:
          storageClassName: prometheus-storage  # Changed from prometheus-2tb-storage
```

### 2.3 Update Samba deployment (if shared path)

**File**: `gitops/clusters/homelab/apps/samba/deployment.yaml`

Change all `/mnt/smb_data` references to `/mnt/samba-storage`:
```yaml
initContainers:
- name: init-perms
  command:
  - sh
  - -c
  - |
    chown nobody:nogroup /mnt/samba-storage
    chmod 0775 /mnt/samba-storage
  volumeMounts:
  - name: share
    mountPath: /mnt/samba-storage
# ...
volumes:
- name: share
  hostPath:
    path: /mnt/samba-storage
```

---

## Step 3: Delete Old Resources

```bash
# Delete old PVC (terminates Prometheus pod)
KUBECONFIG=~/kubeconfig kubectl delete pvc -n monitoring \
  prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0

# Delete old PV
KUBECONFIG=~/kubeconfig kubectl delete pv prometheus-2tb-pv

# Delete old StorageClass
KUBECONFIG=~/kubeconfig kubectl delete sc prometheus-2tb-storage
```

---

## Step 4: Commit and Push

```bash
# Stage changes
git add gitops/clusters/homelab/infrastructure/monitoring/prometheus-storage-class.yaml
git add gitops/clusters/homelab/infrastructure/monitoring/monitoring-values.yaml
git add gitops/clusters/homelab/apps/samba/deployment.yaml

# Verify no secrets
git diff --cached | grep -iE "password|secret|token" || echo "No secrets found"

# Commit
git commit -m "refactor(storage): separate Prometheus from Samba storage"

# Push
git push
```

---

## Step 5: Reconcile Flux

```bash
# Reconcile to apply changes
KUBECONFIG=~/kubeconfig flux reconcile kustomization flux-system --with-source

# Verify new StorageClass and PV created
KUBECONFIG=~/kubeconfig kubectl get sc,pv | grep prometheus

# Expected output:
# storageclass.storage.k8s.io/prometheus-storage     rancher.io/local-path   Retain
# persistentvolume/prometheus-pv                     500Gi      RWO    Retain   Available
```

---

## Step 6: Handle StatefulSet Recreation

The Prometheus operator's volumeClaimTemplate is immutable. If the PVC is stuck:

```bash
# Suspend Flux to prevent interference
KUBECONFIG=~/kubeconfig flux suspend helmrelease kube-prometheus-stack -n monitoring

# Delete StatefulSet (orphan pods)
KUBECONFIG=~/kubeconfig kubectl delete statefulset -n monitoring \
  prometheus-kube-prometheus-stack-prometheus --cascade=orphan

# Delete stuck PVC
KUBECONFIG=~/kubeconfig kubectl delete pvc -n monitoring \
  prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0

# Resume Flux to recreate StatefulSet
KUBECONFIG=~/kubeconfig flux resume helmrelease kube-prometheus-stack -n monitoring
```

---

## Step 7: Clean Up Old Symlinks

```bash
# Remove old symlink on VM
ssh root@pumped-piglet.maas "qm guest exec 105 -- rm -f /mnt/smb_data"

# Verify clean state
ssh root@pumped-piglet.maas "qm guest exec 105 -- ls -la /mnt/"
```

---

## Verification

```bash
# Check Prometheus pod running
KUBECONFIG=~/kubeconfig kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus

# Verify new PVC bound
KUBECONFIG=~/kubeconfig kubectl get pvc -n monitoring | grep prometheus
# Should show: Bound prometheus-pv 500Gi prometheus-storage

# Verify storage path inside pod
KUBECONFIG=~/kubeconfig kubectl exec -n monitoring prometheus-kube-prometheus-stack-prometheus-0 \
  -c prometheus -- df -h /prometheus
# Should show: /dev/sda1 with ~1.5TB available

# Test Prometheus is scraping
KUBECONFIG=~/kubeconfig kubectl exec -n monitoring prometheus-kube-prometheus-stack-prometheus-0 \
  -c prometheus -- wget -qO- "http://localhost:9090/api/v1/query?query=up" | head -100
```

---

## Rollback

If issues occur, revert to old storage:

```bash
# Revert git changes
git revert HEAD
git push

# Recreate old symlink
ssh root@pumped-piglet.maas "qm guest exec 105 -- ln -s /mnt/samba-storage/smb_data /mnt/smb_data"

# Reconcile
KUBECONFIG=~/kubeconfig flux reconcile kustomization flux-system --with-source
```

---

## Related Runbooks

- [Prometheus Data Migration](prometheus-data-migration.md) - Migrate existing data to new storage
- [Storage Architecture Investigation](storage-architecture-investigation.md) - Troubleshoot storage issues

---

**Tags**: prometheus, promethius, storage, gitops, k8s, kubernetes, kubernettes, pv, pvc, storageclass, separation

**Last Updated**: 2026-02-10
