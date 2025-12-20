# RKE2 Windows tmpfs POC - Next Steps

## Current State

VMs on pumped-piglet.maas (stopped, preserved for future testing):

| VMID | Name | Purpose | Status |
|------|------|---------|--------|
| 200 | rancher-mgmt | Rancher v2.13.1 management UI | Stopped |
| 201 | windows-worker | Windows Server 2022 (golden image source) | Stopped |
| 202 | linux-control | RKE2 control plane | Stopped |

Golden image preserved at: `/var/lib/vz/template/vm/windows-server-golden.qcow2` (18GB sparse)

## To Complete the POC

### Phase 1: Recreate tmpfs Windows VM
```bash
./31-setup-tmpfs.sh          # Mount 25GB tmpfs
./32-create-tmpfs-vm.sh      # Create VM 203 from golden image
./33-benchmark-tmpfs.sh      # Verify I/O performance
```

### Phase 2: Re-register with RKE2 Cluster
1. Start control plane VMs (200, 202)
2. Start tmpfs Windows VM (203)
3. Register Windows VM with Rancher cluster
4. Verify node joins and containers run

### Phase 3: ADO Integration
1. Install ADO agent on tmpfs Windows VM
2. Register with unique capability (e.g., `tmpfs-test`)
3. Route test pipeline to this agent
4. Compare performance and reliability

### Phase 4: Validation
- Run real pipelines under concurrent load
- Compare failure rates vs current AKS-EE nodes
- Measure disk I/O metrics (should show no saturation)

## Key Finding

Production AKS-EE Windows nodes show **2000% disk IO utilization** under concurrent agent load, causing robot test failures.

tmpfs-backed VMs eliminate disk queuing - RAM handles parallel access without performance degradation.

## Goal

**Not faster builds - predictable builds at scale.**

| Load | Disk (current) | tmpfs (expected) |
|------|----------------|------------------|
| 1 agent | Fast | Fast |
| 10 agents | 2000% util, failures | No queuing, reliable |

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `30-create-golden-image.sh` | Export sparse qcow2 from Windows VM |
| `31-setup-tmpfs.sh` | Mount tmpfs on Proxmox host |
| `32-create-tmpfs-vm.sh` | Create VM with tmpfs-backed disk |
| `33-benchmark-tmpfs.sh` | Run I/O benchmark in Windows |
| `34-cleanup-tmpfs-vm.sh` | Destroy tmpfs VM and cleanup |
| `35-shutdown-cluster.sh` | Stop all RKE2 VMs |
| `36-start-cluster.sh` | Start all RKE2 VMs |

## Documentation

- Full results: [EVALUATION-RESULTS.md](./EVALUATION-RESULTS.md)
- Benchmark data: tmpfs +127% small file ops, +279% random IOPS
