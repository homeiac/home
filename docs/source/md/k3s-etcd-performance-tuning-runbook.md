# K3s etcd Performance Tuning Runbook

This runbook documents the performance tuning applied to the K3s cluster to reduce etcd sync write latency and improve cluster stability.

## Problem Statement

K3s clusters running on ZFS-backed Proxmox VMs can experience etcd performance issues due to:
- Default VM disk cache settings (writethrough) causing slow fsync operations
- ZFS transaction group timeout adding latency to sync writes
- Guest OS memory management not optimized for database workloads

Symptoms include:
- `slow fdatasync` warnings in K3s logs
- Leader election instability
- API server latency spikes

## Architecture

```
+------------------+     +------------------+     +------------------+
|   Proxmox Host   |     |   Proxmox Host   |     |   Proxmox Host   |
|   (pve.maas)     |     | (pumped-piglet)  |     | (still-fawn)     |
+--------+---------+     +--------+---------+     +--------+---------+
         |                        |                        |
   ZFS Pool                 ZFS Pool                 ZFS Pool
   txg_timeout=3            txg_timeout=3            txg_timeout=3
         |                        |                        |
+--------+---------+     +--------+---------+     +--------+---------+
|    K3s VM 107    |     |    K3s VM 105    |     |    K3s VM 108    |
| cache=writeback  |     | cache=writeback  |     | cache=writeback  |
| iothread=1       |     | iothread=1       |     | iothread=1       |
| sysctl tuned     |     | sysctl tuned     |     | sysctl tuned     |
+--------+---------+     +--------+---------+     +--------+---------+
         |                        |                        |
         +------------------------+------------------------+
                                  |
                          etcd cluster
                        (embedded in K3s)
```

## Tuning Applied

### 1. VM Disk Cache Settings

**Change:** Enable writeback cache and dedicated I/O thread

```bash
# On Proxmox host
qm set <VMID> -scsi0 <storage>:<disk>,cache=writeback,iothread=1
```

**Rationale:**
- `cache=writeback`: Uses host page cache, reduces sync write latency
- `iothread=1`: Dedicated I/O thread prevents blocking on disk operations

### 2. Guest OS Sysctl Tuning

**Change:** Optimize memory management for database workloads

```bash
# /etc/sysctl.d/99-etcd.conf
vm.swappiness=10
vm.dirty_ratio=5
vm.dirty_background_ratio=3
```

**Rationale:**
- Lower swappiness keeps etcd data in memory
- Aggressive dirty page flushing reduces write latency spikes

### 3. ZFS Transaction Group Timeout

**Change:** Reduce txg_timeout from 5s to 3s

```bash
# Runtime
echo 3 > /sys/module/zfs/parameters/zfs_txg_timeout

# Persistent
echo "options zfs zfs_txg_timeout=3" > /etc/modprobe.d/zfs-etcd.conf
```

**Rationale:**
- Shorter transaction groups = faster sync acknowledgment
- Trade-off: Slightly more CPU overhead for ZFS

## Automation Script

A reusable script is available at `proxmox/homelab/scripts/tune-k3s-vm.sh`:

```bash
./tune-k3s-vm.sh <proxmox_host> <vmid> "<disk_spec>"

# Example:
./tune-k3s-vm.sh still-fawn.maas 108 "local-2TB-zfs:vm-108-disk-0,size=700G"
```

The script:
1. Applies sysctl tuning
2. Enables disk cache + iothread
3. Reboots the VM
4. Verifies cluster health
5. Confirms settings applied

## Monitoring

Check for etcd performance issues:

```bash
# Watch for slow sync warnings
journalctl -u k3s -f | grep -i "slow fdatasync"

# Check etcd leader stability
kubectl get lease -n kube-system k3s -o yaml

# Monitor ZFS sync queue
zpool iostat -lq <pool> 1
```

## Rollback

If issues occur, revert each change:

```bash
# VM disk cache (requires reboot)
qm set <VMID> -scsi0 <storage>:<disk>,size=<size>

# Guest sysctl
rm /etc/sysctl.d/99-etcd.conf
sysctl -p

# ZFS txg_timeout
echo 5 > /sys/module/zfs/parameters/zfs_txg_timeout
rm /etc/modprobe.d/zfs-etcd.conf
```

## References

- [etcd Hardware Recommendations](https://etcd.io/docs/v3.5/op-guide/hardware/)
- [K3s High Availability](https://docs.k3s.io/datastore/ha-embedded)
- [ZFS on Linux Tuning](https://openzfs.github.io/openzfs-docs/Performance%20and%20Tuning/Workload%20Tuning.html)
