# RCA: Crossplane VM 200 Creation Retry Loop

**Date:** 2026-01-16
**Duration:** Unknown (retry loop running since at least 2026-01-13 based on task logs)
**Severity:** Low (no production impact, but noisy logs)
**Root Cause Category:** Orphaned ZFS datasets from failed VM creation

---

## Summary

Crossplane was stuck in a retry loop attempting to create VM 200 ("rancher-server") on pumped-piglet. Each attempt failed with:

```
unable to create VM 200 - zfs error: cannot create 'local-2TB-zfs/vm-200-cloudinit': dataset already exists
```

---

## Timeline

| Time | Event |
|------|-------|
| Unknown | Initial VM 200 creation attempted, failed partway through |
| Unknown | ZFS datasets created but VM config not finalized |
| 2026-01-13+ | Crossplane retry loop begins (visible in `/var/log/pve/tasks/`) |
| 2026-01-16 | Issue discovered, rancher-server.yaml removed from Git |

---

## Technical Details

### What Existed

**On ZFS (orphaned datasets):**
```
local-2TB-zfs/vm-200-cloudinit     76K
local-2TB-zfs/vm-200-disk-0      10.8G
```

**In Git (Crossplane resource):**
```yaml
# gitops/clusters/homelab/instances/rancher-server.yaml
apiVersion: virtualenvironmentvm.crossplane.io/v1alpha1
kind: EnvironmentVM
metadata:
  name: rancher-server
  annotations:
    crossplane.io/external-name: "200"  # Meant to adopt existing VM
spec:
  forProvider:
    nodeName: pumped-piglet
    vmId: 200
```

**Missing (the actual VM):**
```
/etc/pve/qemu-server/200.conf  # Did not exist
```

### Why It Failed

1. Previous VM 200 creation started but failed mid-process
2. ZFS datasets were created before failure
3. Proxmox VM config was never written
4. Crossplane saw no VM 200 → tried to create
5. `qm create` failed because ZFS datasets already existed
6. Crossplane retried indefinitely

### The Adoption Annotation Didn't Help

The `crossplane.io/external-name: "200"` annotation is meant to adopt an existing VM. However:
- Adoption requires the VM to actually exist in Proxmox
- Without `/etc/pve/qemu-server/200.conf`, there's no VM to adopt
- Crossplane fell back to creation, which failed on ZFS conflicts

---

## Resolution

**Immediate fix:**
```bash
# Removed from Git
git rm gitops/clusters/homelab/instances/rancher-server.yaml
git commit -m "chore: remove rancher-server VM 200 definition"
git push
```

**Cleanup needed (optional, reclaims ~11GB):**
```bash
ssh root@pumped-piglet.maas "zfs destroy local-2TB-zfs/vm-200-cloudinit && zfs destroy local-2TB-zfs/vm-200-disk-0"
```

---

## Root Cause Analysis

### RC1: No Cleanup After Failed VM Creation

**What happened:**
- VM creation failed partway through
- ZFS datasets were left orphaned
- No automatic cleanup mechanism

**Why it happened:**
- Proxmox `qm create` is not fully transactional
- ZFS dataset creation happens before VM config is finalized
- Failed creation doesn't roll back ZFS datasets

**Prevention:**
- Before creating VMs, check for orphaned datasets:
  ```bash
  zfs list | grep "vm-${VMID}-"
  ```
- Clean up orphans before retrying creation

### RC2: Crossplane Retry Without Backoff Investigation

**What happened:**
- Crossplane kept retrying the same failing operation
- No alerting or visibility into the retry loop

**Why it happened:**
- Default Crossplane reconciliation behavior
- No monitoring for Crossplane resource sync failures

**Prevention:**
- Add Prometheus alerts for Crossplane resources stuck in non-Ready state
- Consider `crossplane.io/paused: "true"` annotation for resources that need manual intervention

---

## Positive Outcome

**Crossplane is working!** The retry loop, while noisy, proved that:
- Flux → K8s CR sync works
- Crossplane → Proxmox API integration works
- The `provision-manage-vms` API user has correct permissions

This was the first real validation of the Crossplane GitOps pipeline for VM management.

---

## Action Items

| Item | Status | Owner |
|------|--------|-------|
| Remove rancher-server.yaml from Git | ✅ Done | - |
| Clean up orphaned ZFS datasets | ⬜ Optional | User |
| Add Crossplane sync failure alerting | ⬜ Future | - |
| Document VM creation pre-checks | ⬜ Future | - |

---

## Related

- OpenMemory: Crossplane provider configuration
- File: `gitops/clusters/homelab/infrastructure/crossplane/`
- Proxmox host: pumped-piglet.maas

**Tags:** crossplane, proxmox, vm, zfs, retry-loop, orphaned-datasets, pumped-piglet
