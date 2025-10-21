# Pumped-Piglet Migration Guide

**Date**: 2025-10-20
**Author**: Claude Code
**Status**: Production Ready

## Overview

This guide documents the idempotent, Python-based migration of K3s workloads from the failed `still-fawn` node (CPU fan failure) to the new `pumped-piglet` node (Intel Xeon W-2135, 64GB RAM, RTX 3070 GPU).

## Migration Architecture

### Python Modules

The migration is implemented as a set of idempotent Python modules in `proxmox/homelab/src/homelab/`:

1. **`storage_manager.py`** - ZFS pool management
2. **`gpu_passthrough_manager.py`** - GPU configuration
3. **`k3s_migration_manager.py`** - K3s cluster operations
4. **`pumped_piglet_migration.py`** - Main orchestrator

### Key Features

- ✅ **Idempotent**: Safe to re-run after failures
- ✅ **Resumable**: State persisted to JSON file
- ✅ **Comprehensive Logging**: All operations logged
- ✅ **Version Controlled**: All logic in Git
- ✅ **Testable**: Unit tests for each module

## Prerequisites

### Hardware

- **pumped-piglet** node online and accessible
- **Hardware**:
  - CPU: Intel Xeon W-2135 (6 cores, 12 threads @ 3.70GHz)
  - RAM: 64GB
  - Storage:
    - nvme0n1 (256GB): Proxmox OS
    - nvme1n1 (2TB): For K3s VMs (to be configured as ZFS)
    - sda (21.8TB): Moved from still-fawn, contains PBS backups
  - GPU: RTX 3070 8GB (PCI: 0000:b3:00.0)

### Software

- Proxmox VE installed on pumped-piglet
- Python 3.11+ with Poetry
- SSH access to pumped-piglet
- Existing K3s cluster accessible

### Environment Variables

Required in `proxmox/homelab/.env`:

```bash
API_TOKEN=user!token=secret
NODE_1=pumped-piglet
STORAGE_1=local-2TB-zfs
IMG_STORAGE_1=local-2TB-zfs
CPU_RATIO_1=0.83  # 10 of 12 cores
MEMORY_RATIO_1=0.75  # 48GB of 64GB
```

## Execution

### Step 1: SSH to pumped-piglet Host

```bash
# From Mac
ssh root@pumped-piglet.maas
```

### Step 2: Clone Repository

```bash
cd /root
git clone https://github.com/homeiac/home.git
cd home/proxmox/homelab
```

### Step 3: Install Dependencies

```bash
# Install Poetry if not present
curl -sSL https://install.python-poetry.org | python3 -

# Install project dependencies
poetry install
```

### Step 4: Run Migration

```bash
# Execute complete migration (all phases)
poetry run python -m homelab.pumped_piglet_migration

# Or start from specific phase (if resuming)
poetry run python -m homelab.pumped_piglet_migration --start-from=k3s
```

### Step 5: Monitor Progress

```bash
# Check state file
cat /tmp/pumped_piglet_migration.json

# Check logs
tail -f /tmp/pumped_piglet_migration_*.log
```

## Migration Phases

### Phase 1: Storage Setup

**What it does**:
- Creates `local-2TB-zfs` pool on `/dev/nvme1n1` (fresh)
- Registers 2TB pool with Proxmox
- Imports `local-20TB-zfs` pool from `/dev/sda`
- Registers 20TB pool with Proxmox

**Verification**:
```bash
ssh root@pumped-piglet.maas "zpool list"
ssh root@pumped-piglet.maas "pvesm status"
```

**Expected Output**:
```
local-2TB-zfs   1.82T   ...   ONLINE
local-20TB-zfs  21.8T   ...   ONLINE
```

### Phase 2: GPU Passthrough

**What it does**:
- Detects NVIDIA RTX 3070 GPU and audio device
- Configures VFIO modules (/etc/modules)
- Blacklists nouveau driver
- Updates initramfs

**⚠️ REBOOT REQUIRED**:
If VFIO modules are added, the script will exit with instructions to reboot:

```bash
ssh root@pumped-piglet.maas reboot
# Wait for reboot, then re-run migration
```

**Verification**:
```bash
ssh root@pumped-piglet.maas "lsmod | grep vfio"
```

### Phase 3: VM Creation

**What it does**:
- Downloads Ubuntu 24.04 cloud image
- Creates VM with VMID (auto-assigned)
- Configures:
  - 10 CPU cores (host passthrough)
  - 48GB RAM
  - 1.8TB disk on `local-2TB-zfs`
  - RTX 3070 GPU passthrough
  - Cloud-init with SSH keys
- Starts VM and waits for IP address

**Verification**:
```bash
ssh root@pumped-piglet.maas "qm list"
ssh root@pumped-piglet.maas "qm config <VMID>"
```

### Phase 4: K3s Bootstrap

**What it does**:
- Retrieves join token from existing node (192.168.4.238)
- Installs K3s on new VM
- Joins cluster as server node
- Applies node labels: `gpu=nvidia`, `memory=high`
- Verifies GPU availability (`nvidia-smi`)
- Waits for node to register in cluster

**Verification**:
```bash
# From Mac or working K3s node
kubectl get nodes -o wide

# Should show:
# k3s-vm-pumped-piglet   Ready   control-plane,etcd,master   <age>   v1.32.4+k3s1
```

### Phase 5: Workload Migration

**What it does**:
- Cordons `k3s-vm-still-fawn` (prevents new pods)
- Deletes stuck pods in Terminating/Pending state
- Flux GitOps automatically reschedules pods to available nodes

**Verification**:
```bash
# Check pod distribution
kubectl get pods -A -o wide

# GPU workloads should be on pumped-piglet
kubectl get pods -n ollama -o wide
kubectl get pods -n webtop -o wide
kubectl get pods -A -o wide | grep pumped-piglet
```

## State File Format

The migration state is saved to `/tmp/pumped_piglet_migration.json`:

```json
{
  "started_at": "2025-10-20T10:00:00",
  "last_updated": "2025-10-20T10:45:00",
  "steps": {
    "create_2tb_nvme_pool": {
      "completed_at": "2025-10-20T10:05:00",
      "result": {"exists": true, "created": true}
    },
    "bootstrap_k3s": {
      "completed_at": "2025-10-20T10:30:00",
      "result": true
    }
  },
  "vm_info": {
    "vmid": 110,
    "ip": "192.168.4.xxx"
  },
  "gpu_info": {
    "pci_address": "0000:b3:00.0",
    "description": "GeForce RTX 3070"
  }
}
```

## Troubleshooting

### Issue: VFIO Modules Not Loading

**Symptoms**: Phase 2 completes but `lsmod | grep vfio` shows nothing

**Solution**:
```bash
ssh root@pumped-piglet.maas "cat /etc/modules"
# Ensure vfio, vfio_pci, vfio_iommu_type1, vfio_virqfd are present

ssh root@pumped-piglet.maas "update-initramfs -u -k all"
ssh root@pumped-piglet.maas reboot
```

### Issue: VM Creation Fails

**Symptoms**: Phase 3 fails with disk import error

**Solution**:
```bash
# Check ZFS pool is accessible
ssh root@pumped-piglet.maas "zpool status local-2TB-zfs"

# Check Proxmox storage configuration
ssh root@pumped-piglet.maas "pvesm status"

# Manually create VM if needed, then re-run (it will detect existing VM)
```

### Issue: K3s Join Fails

**Symptoms**: Phase 4 fails to retrieve join token

**Solution**:
```bash
# Verify existing K3s node is accessible
ssh ubuntu@192.168.4.238 "sudo systemctl status k3s"

# Manually get token
ssh ubuntu@192.168.4.238 "sudo cat /var/lib/rancher/k3s/server/node-token"

# Update state file with token (optional)
```

### Issue: GPU Not Available in VM

**Symptoms**: `nvidia-smi` fails in K3s VM

**Solution**:
```bash
# Check VM GPU configuration
ssh root@pumped-piglet.maas "qm config <VMID> | grep hostpci"

# Check IOMMU groups
ssh root@pumped-piglet.maas "find /sys/kernel/iommu_groups -type l"

# Verify VFIO modules loaded on HOST
ssh root@pumped-piglet.maas "lsmod | grep vfio"
```

## Post-Migration Tasks

### 1. Remove Failed Node from Cluster

**⚠️ Only after verifying all workloads are running on new node:**

```bash
# Delete still-fawn from K3s cluster
kubectl delete node k3s-vm-still-fawn

# Power off still-fawn host (if accessible)
ssh root@still-fawn.maas "shutdown -h now"
```

### 2. Update Prometheus Storage

Prometheus has node affinity to `k3s-vm-still-fawn`. Update to use `pumped-piglet`:

```bash
# Edit Prometheus PV
kubectl edit pv prometheus-2tb-pv

# Change nodeAffinity:
#   matchExpressions:
#   - key: kubernetes.io/hostname
#     operator: In
#     values:
#     - k3s-vm-pumped-piglet  # Changed from still-fawn

# Force Prometheus pod restart
kubectl delete pod -n monitoring prometheus-kube-prometheus-stack-prometheus-0
```

### 3. Migrate PBS Container

Proxmox Backup Server (LXC 103) was on still-fawn. Migrate to pumped-piglet:

```bash
# Option A: Migrate LXC (if still-fawn is accessible)
pct migrate 103 pumped-piglet --online

# Option B: Create new PBS container
# Use PVE Helper Script or manual creation
```

### 4. Update Documentation

Update these files:
- `docs/source/md/proxmox-infrastructure-guide.md`
- `docs/architecture/storage-architecture.md`
- `README.md`

Mark still-fawn as OFFLINE, add pumped-piglet specs.

## Rollback Procedure

If critical issues occur:

### 1. Cordon pumped-piglet Node
```bash
kubectl cordon k3s-vm-pumped-piglet
```

### 2. Migrate Workloads Back
```bash
# Delete pods on pumped-piglet
kubectl delete pod -n ollama --all
kubectl delete pod -n webtop --all

# They will reschedule to pve/chief-horse
```

### 3. Attempt to Revive still-fawn
- Replace CPU fan
- Power on still-fawn
- Uncordon node: `kubectl uncordon k3s-vm-still-fawn`

## Success Criteria

- ✅ New K3s node `k3s-vm-pumped-piglet` joins cluster
- ✅ RTX 3070 GPU accessible in VM (`nvidia-smi` works)
- ✅ GPU workloads running: Ollama, Stable Diffusion, Webtop
- ✅ Monitoring stack operational: Prometheus, Grafana
- ✅ 20TB ZFS pool imported, PBS accessible
- ✅ 2TB NVMe ZFS pool active for VM storage
- ✅ Flux GitOps reconciling successfully
- ✅ MetalLB LoadBalancers operational
- ✅ Services accessible via Traefik ingress

## Related Documentation

- [Proxmox Infrastructure Guide](../source/md/proxmox-infrastructure-guide.md)
- [Storage Architecture](../architecture/storage-architecture.md)
- [K3s Migration Runbook](../source/md/runbooks/too-many-open-files-k3s.md)
- [GPU Passthrough Guide](../source/md/proxmox_guides_nvidia-RTX-3070-k3s-PCI-passthrough.md)

## Tags

migration, pumped-piglet, still-fawn, k3s, kubernetes, kubernettes, gpu, gpu-passthrough, zfs, storage, idempotent, python, automation, orchestration, rtx-3070, intel-xeon
