# Critical VM Placement Constraints

## Overview

Certain VMs in the homelab use local storage (`local-zfs`) which only exists on specific nodes. These VMs **cannot be migrated** to other nodes and **must not be placed in Proxmox HA**.

## Why HA Doesn't Work with Local Storage

Proxmox HA assumes shared storage (Ceph, NFS, iSCSI). When a node fails, HA migrates the VM to another node. But if the VM's disk is on `local-zfs`, the disk doesn't exist on other nodes - the VM fails to start with:

```
storage 'local-zfs' is not available on node '<node-name>'
```

## Critical VMs

| VMID | Name | Storage | Valid Nodes | Purpose |
|------|------|---------|-------------|---------|
| 101 | OPNsense | `local-zfs:vm-101-disk-0` | pve, still-fawn | Network gateway, DHCP, DNS |
| 102 | UbuntuMAAS | `local-zfs:vm-102-disk-0` | pve, still-fawn | MAAS controller |

## Storage Availability

From `/etc/pve/storage.cfg`:

```
zfspool: local-zfs
    pool rpool/data
    content rootdir,images
    nodes still-fawn,pve
    sparse 1
```

**Nodes with `local-zfs`:** pve, still-fawn
**Nodes WITHOUT `local-zfs`:** chief-horse, fun-bedbug, pumped-piglet

## Rules

1. **Never add these VMs to Proxmox HA** - HA will try to migrate them to nodes without the storage
2. **Never manually move VM config** to a node without `local-zfs`
3. **Keep `onboot: 1`** so VMs auto-start when their host node boots
4. **Keep `startup: order=1`** for OPNsense so it starts before other VMs

## Checking VM Placement

```bash
# Check which node a VM is on
cat /etc/pve/nodes/*/qemu-server/101.conf 2>/dev/null | head -1

# Check VM storage
qm config 101 | grep -E 'virtio|scsi|ide'

# Check HA status (should be empty for these VMs)
cat /etc/pve/ha/resources.cfg
```

## Recovery if Misconfigured

If OPNsense ends up on wrong node:

```bash
# Move config to correct node (pve)
mv /etc/pve/nodes/<wrong-node>/qemu-server/101.conf /etc/pve/nodes/pve/qemu-server/101.conf

# Remove from HA if present
ha-manager remove vm:101

# Start the VM
qm start 101
```

## Incident Reference

**2026-01-24:** OPNsense was misconfigured to run on chief-horse (which lacks `local-zfs`). After pve.maas rebooted, OPNsense failed to start, causing network outage. Fixed by moving VM config back to pve node.

## Future Considerations

To enable true HA for critical VMs:
1. Set up shared storage (Ceph, NFS, or iSCSI)
2. Migrate VM disks to shared storage
3. Then enable HA

Crossplane can manage VM definitions via GitOps but does NOT provide failover - it only tracks desired state.

## Tags

proxmox, ha, high-availability, local-storage, opnsense, maas, vm-placement, constraint, local-zfs
