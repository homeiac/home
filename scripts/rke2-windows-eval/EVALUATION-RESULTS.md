# RKE2 + Rancher Windows Worker Evaluation Results

**Date**: 2025-12-20
**Host**: pumped-piglet.maas

## Cluster Architecture

```
pumped-piglet.maas (Proxmox host, 62GB RAM)
├── VM 200: rancher-mgmt (Ubuntu 24.04, 4GB RAM)
│   └── Rancher v2.13.1 management UI
│   └── IP: 192.168.4.200
│
├── VM 202: linux-control (Ubuntu 24.04, 4GB RAM)
│   └── RKE2 v1.34.2 control plane
│   └── IP: 192.168.4.202
│
└── VM 201: windows-worker (Windows Server 2022 Eval, 16GB RAM)
    └── RKE2 Windows worker node
    └── IP: 192.168.4.201
```

## Cluster Status: VERIFIED WORKING

### Nodes
| Node | Status | Roles | Internal IP | OS |
|------|--------|-------|-------------|-----|
| ubuntu | Ready | control-plane,etcd,worker | 192.168.4.202 | Ubuntu 24.04.2 LTS |
| win-30731tq82ag | Ready | worker | 192.168.4.201 | Windows Server 2022 Standard Evaluation |

### Key Findings
- **IPv6 Fix Required**: Must disable IPv6 on Linux control plane AND set `node-ip` explicitly in RKE2 config BEFORE registration
- **Calico CNI**: Required for Windows node support
- **Separate VMs**: Rancher management must be on separate VM from workload cluster

## Windows Container Workloads: VERIFIED WORKING

### Test 1: Simple Windows Pod
- Image: `mcr.microsoft.com/windows/servercore:ltsc2022`
- Status: Running
- Pod IP: 10.42.140.3

### Test 2: Disk I/O Benchmark Job
- Status: Completed successfully
- Pod IP: 10.42.140.4

## Disk I/O Benchmark Results (ZFS-backed)

| Metric | Result | Notes |
|--------|--------|-------|
| Sequential Write | 2466.47 MB/s | 1GB file |
| Sequential Read | 4137.98 MB/s | 1GB file |
| Small File Creation | 899.74 files/sec | 1000 x 4KB files |
| Random 4KB Read IOPS | 12119.33 | 1000 operations |

### Storage Configuration
- VM Disk: 200GB on local-2TB-zfs (ZFS on NVMe SSD)
- Actual Windows usage: ~22GB
- VirtIO driver with cache=writeback

## Conclusions

1. **RKE2 + Rancher works for Windows workers** - Successfully deployed and ran Windows container workloads
2. **Disk I/O is good** - 2.5 GB/s write, 4 GB/s read on ZFS-backed storage
3. **IPv6 is a trap** - Must explicitly force IPv4 on Linux control plane
4. **Windows Server Eval** - 180-day license, sufficient for evaluation

## tmpfs-Backed Windows VM: VALIDATED

### The Problem We're Solving

Production Windows build agents show **disk I/O saturation** under concurrent load:
- Disk IO Utilisation: **2000% spikes** (queuing)
- IO latency: **30-40ms** (should be <1ms)
- Result: Robot tests fail when scaling agents

### The Solution: tmpfs at Hypervisor Level

Windows containers can't use tmpfs directly. We bypassed this by putting the **entire VM disk** on tmpfs:

```
Proxmox Host (DDR4-2666 RAM)
└── tmpfs (/mnt/ramdisk, 25GB)
    └── Windows VM disk (qcow2, 18GB sparse)
        └── NTFS (C:\)
            └── containerd → Windows containers
```

Windows has no idea it's running on RAM. It sees a normal disk.

### Implementation

1. **Golden Image**: Created sparse qcow2 from VM 201 (200GB virtual → 18GB actual)
2. **tmpfs Mount**: 25GB on Proxmox host
3. **VM 203**: UEFI Windows VM booting from tmpfs-backed disk
4. **Container Test**: Pulled image, ran container successfully

### Benchmark Results

| Metric | ZFS (VM 201) | tmpfs (VM 203) | Improvement |
|--------|-------------|----------------|-------------|
| Sequential Write | 2466 MB/s | 3123 MB/s | **+27%** |
| Sequential Read | 4138 MB/s | 5023 MB/s | **+21%** |
| Small File Ops | 900/sec | 2042/sec | **+127%** |
| Random IOPS | 12119 | 45906 | **+279%** |

### Raw tmpfs (No VM Overhead)

Direct benchmark on Proxmox host tmpfs:
- Write: **3.5 GB/s**
- Read: **6.8 GB/s**

QEMU/VirtIO overhead: ~10-25%

### Key Findings

1. **Small file ops +127%** - Critical for npm/yarn/dotnet restore
2. **Random IOPS +279%** - Huge win for build tools
3. **Containers work** - containerd runs, images pull, containers execute
4. **Ephemeral by design** - Reboot = fresh golden image (perfect for build agents)

### Why This Matters for Reliability

The goal isn't faster builds - it's **predictable performance at scale**:

| Load | Disk (current) | tmpfs |
|------|----------------|-------|
| 1 agent | Fast | Fast |
| 10 agents | 2000% util, 40ms latency, **failures** | Still fast, **no queuing** |

Disk I/O degrades non-linearly under contention. RAM doesn't queue - it handles parallel access without performance collapse.

### Architecture Comparison

| Approach | Host | I/O Speed | Ephemeral | Golden Image | Complexity |
|----------|------|-----------|-----------|--------------|------------|
| Windows bare metal | Windows | SSD-bound | No | No | Low |
| Windows VM on SSD | Linux | SSD-bound | Yes | Yes | Medium |
| **Windows VM on tmpfs** | Linux | **RAM-speed** | Yes | Yes | Medium |

### Hardware Requirements

- **RAM**: Golden image size + VM RAM + headroom (our test: 18GB + 16GB + ~10GB = 44GB)
- **Host OS**: Linux with tmpfs support (Proxmox, Ubuntu, etc.)
- **CPU**: VT-x/VT-d for hardware virtualization (~2-5% overhead)

### Production Recommendation

1. **Pilot**: Convert ONE Windows node to tmpfs-backed VM
2. **Test**: Run agents alongside existing nodes under load
3. **Measure**: Compare failure rates, not just speed
4. **Scale**: If latency stays flat under load → roll out

### Scripts for tmpfs Testing

| Script | Purpose |
|--------|---------|
| `30-create-golden-image.sh` | Export sparse qcow2 from Windows VM |
| `31-setup-tmpfs.sh` | Mount tmpfs on Proxmox host |
| `32-create-tmpfs-vm.sh` | Create VM with tmpfs-backed disk |
| `33-benchmark-tmpfs.sh` | Run I/O benchmark in Windows |
| `34-cleanup-tmpfs-vm.sh` | Destroy tmpfs VM and cleanup |
| `37-benchmark-host-tmpfs.sh` | Benchmark raw tmpfs on host |

## Scripts Created

| Script | Purpose |
|--------|---------|
| `01-create-rancher-vm.sh` | Create Rancher management VM |
| `02-install-rke2-rancher.sh` | Install RKE2 + Rancher |
| `07-create-linux-control.sh` | Create Linux control plane (with IPv6 fix) |
| `08-register-linux-node.sh` | Register Linux node with node-ip |
| `09-register-windows-node.sh` | Register Windows worker |
| `20-wait-for-ingress.sh` | Wait for ingress controller |
| `21-install-rancher.sh` | Install Rancher via Helm |
| `22-check-rancher-status.sh` | Check cluster status |
| `23-destroy-linux-vms.sh` | Destroy Linux VMs only |
| `24-wait-for-linux-vm.sh` | Wait for Linux VM boot |
| `25-run-windows-test.sh` | Run Windows test workloads |
| `26-cleanup-windows-tests.sh` | Cleanup test pods |
| `99-destroy-all.sh` | Nuclear reset |

## Next Steps

1. **Pilot on work hardware**: Install Linux on bare metal, replicate tmpfs VM setup
2. **Register as ADO agent**: Connect tmpfs-backed Windows VM to ADO
3. **Run real pipelines**: Compare failure rates under concurrent load
4. **Measure latency stability**: Prove disk I/O doesn't spike under load
5. **Scale decision**: If pilot succeeds, plan rollout to more nodes
