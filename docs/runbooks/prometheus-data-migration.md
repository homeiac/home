# Prometheus Data Migration Runbook

**Purpose**: Migrate existing Prometheus TSDB data to new storage location
**Duration**: ~10 minutes (depends on data size)
**Data at Risk**: None if followed correctly

---

## Prerequisites

- New storage path already created (see [prometheus-storage-separation.md](prometheus-storage-separation.md))
- SSH access to Proxmox host
- `kubectl` access to K3s cluster

---

## Quick Reference

| Item | Value |
|------|-------|
| Old data path | `/mnt/samba-storage/smb_data/prometheus/prometheus-db/` |
| New data path | `/mnt/prometheus/prometheus-db/` |
| Prometheus user:group | `1000:2000` |
| VMID (pumped-piglet) | `105` |

---

## Critical: SubPath Understanding

The Prometheus Operator mounts the PVC with `subPath: prometheus-db`. This means:
- PVC mounts to `/mnt/prometheus/`
- Pod sees `/prometheus/` which maps to `/mnt/prometheus/prometheus-db/`
- **Data must be placed in the `prometheus-db/` subdirectory, not the PV root**

---

## Step 1: Stop Prometheus

```bash
# Patch the Prometheus CR to scale down (not the StatefulSet!)
KUBECONFIG=~/kubeconfig kubectl patch prometheus -n monitoring kube-prometheus-stack-prometheus \
  --type='merge' -p '{"spec":{"replicas":0}}'

# Wait for pod termination
KUBECONFIG=~/kubeconfig kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus -w
# Wait until "No resources found"
```

**Why patch the CR?** The Prometheus Operator controls the StatefulSet. Scaling the StatefulSet directly will be overridden by the operator.

---

## Step 2: Check Old Data Location

```bash
# Verify old data exists
ssh root@pumped-piglet.maas "qm guest exec 105 -- ls -la /mnt/samba-storage/smb_data/prometheus/prometheus-db/"

# Check data size
ssh root@pumped-piglet.maas "qm guest exec 105 -- du -sh /mnt/samba-storage/smb_data/prometheus/prometheus-db/"
# Example: 17G
```

---

## Step 3: Ensure prometheus-db Subdirectory Exists

```bash
# Create subdirectory if not exists
ssh root@pumped-piglet.maas "qm guest exec 105 -- mkdir -p /mnt/prometheus/prometheus-db"
```

---

## Step 4: Copy Data

```bash
# Copy with archive mode (preserves permissions, timestamps)
ssh root@pumped-piglet.maas "qm guest exec 105 -- cp -a /mnt/samba-storage/smb_data/prometheus/prometheus-db/. /mnt/prometheus/prometheus-db/"
```

**Note**: This command runs via `qm guest exec` and may timeout for large datasets. Monitor progress:

```bash
# In another terminal, check copy progress
ssh root@pumped-piglet.maas "qm guest exec 105 -- du -sh /mnt/prometheus/prometheus-db/"

# Check if cp is still running
ssh root@pumped-piglet.maas "qm guest exec 105 -- pgrep -a cp"
```

For very large datasets (>50GB), use rsync instead:
```bash
ssh root@pumped-piglet.maas "qm guest exec 105 -- rsync -av --progress \
  /mnt/samba-storage/smb_data/prometheus/prometheus-db/ \
  /mnt/prometheus/prometheus-db/"
```

---

## Step 5: Fix Ownership

```bash
# Set correct ownership for Prometheus
ssh root@pumped-piglet.maas "qm guest exec 105 -- chown -R 1000:2000 /mnt/prometheus/prometheus-db"

# Verify ownership
ssh root@pumped-piglet.maas "qm guest exec 105 -- ls -la /mnt/prometheus/prometheus-db/"
# All files should show: ubuntu 2000 (uid 1000 = ubuntu)
```

---

## Step 6: Start Prometheus

```bash
# Scale Prometheus back up
KUBECONFIG=~/kubeconfig kubectl patch prometheus -n monitoring kube-prometheus-stack-prometheus \
  --type='merge' -p '{"spec":{"replicas":1}}'

# Wait for pod to be ready
KUBECONFIG=~/kubeconfig kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus -w
```

---

## Step 7: Verify Data Loaded

```bash
# Check Prometheus logs for block loading
KUBECONFIG=~/kubeconfig kubectl logs -n monitoring prometheus-kube-prometheus-stack-prometheus-0 \
  -c prometheus 2>&1 | grep -E "block|TSDB"

# Expected output (one line per historical block):
# msg="Found healthy block" component=tsdb ulid=01KF6ECRXE0TBMNFJSFBXYRHC2
# msg="Found healthy block" component=tsdb ulid=01KFC7TEBWQV9EMZP32Q3ZR2DA
# ...
# msg="TSDB started"
```

---

## Step 8: Query Historical Data

```bash
# Query a historical timestamp (adjust epoch for your data range)
# Example: Jan 27, 2026 = 1769500000

KUBECONFIG=~/kubeconfig kubectl exec -n monitoring prometheus-kube-prometheus-stack-prometheus-0 \
  -c prometheus -- wget -qO- "http://localhost:9090/api/v1/query?query=count(up)&time=1769500000"

# Should return result with data, e.g.:
# {"status":"success","data":{"result":[{"value":[1769500000,"5"]}]}}
```

---

## Step 9: Clean Up Old Data (Optional)

Only after verifying historical data is accessible:

```bash
# Remove old data
ssh root@pumped-piglet.maas "qm guest exec 105 -- rm -rf /mnt/samba-storage/smb_data/prometheus"

# Verify removed
ssh root@pumped-piglet.maas "qm guest exec 105 -- ls /mnt/samba-storage/smb_data/"
```

---

## Troubleshooting

### Prometheus Shows Empty Data After Migration

**Symptom**: Historical queries return empty results

**Cause**: Data placed in wrong directory (PV root instead of `prometheus-db/` subdir)

**Fix**:
```bash
# Stop Prometheus
KUBECONFIG=~/kubeconfig kubectl patch prometheus -n monitoring kube-prometheus-stack-prometheus \
  --type='merge' -p '{"spec":{"replicas":0}}'

# Move data to correct subdirectory
ssh root@pumped-piglet.maas "qm guest exec 105 -- mv /mnt/prometheus/01K* /mnt/prometheus/prometheus-db/"

# Fix ownership
ssh root@pumped-piglet.maas "qm guest exec 105 -- chown -R 1000:2000 /mnt/prometheus/prometheus-db"

# Start Prometheus
KUBECONFIG=~/kubeconfig kubectl patch prometheus -n monitoring kube-prometheus-stack-prometheus \
  --type='merge' -p '{"spec":{"replicas":1}}'
```

### "TSDB lock: resource busy" Error

**Cause**: Prometheus didn't shut down cleanly, lock file remains

**Fix**:
```bash
# Remove stale lock file
ssh root@pumped-piglet.maas "qm guest exec 105 -- rm -f /mnt/prometheus/prometheus-db/lock"
```

### Permission Denied Errors in Logs

**Cause**: Wrong ownership on data files

**Fix**:
```bash
ssh root@pumped-piglet.maas "qm guest exec 105 -- chown -R 1000:2000 /mnt/prometheus/prometheus-db"
```

---

## Data Structure Reference

A healthy Prometheus data directory contains:

```
/mnt/prometheus/prometheus-db/
├── 01KF6ECRXE0TBMNFJSFBXYRHC2/  # Historical block (ULID)
│   ├── chunks/
│   ├── index
│   ├── meta.json
│   └── tombstones
├── 01KFC7TEBWQV9EMZP32Q3ZR2DA/  # Another historical block
├── ...
├── chunks_head/                  # Current active data
├── lock                          # Exclusive lock file
├── queries.active               # Active query tracking
└── wal/                          # Write-ahead log
    ├── 00000000
    └── checkpoint.00000000/
```

---

## Related Runbooks

- [Prometheus Storage Separation](prometheus-storage-separation.md) - Set up new storage
- [Storage Architecture Investigation](storage-architecture-investigation.md) - Troubleshoot storage issues

---

**Tags**: prometheus, promethius, data-migration, tsdb, storage, backup, restore, historical-data, k8s, kubernetes, kubernettes

**Last Updated**: 2026-02-10
