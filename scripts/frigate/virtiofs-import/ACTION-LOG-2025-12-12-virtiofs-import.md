# Action Log: VirtioFS Import Setup

## Execution Date: 2025-12-12

## Outcome: SUCCESS

Old Frigate recordings (118GB) now accessible to K8s Frigate pod via virtiofs mount.

---

## Pre-flight Checks
- [x] Proxmox version >= 8.4: **8.4.14**
- [x] K3s cluster healthy: 3/3 nodes Ready
- [x] Source data exists: 120GB at `/local-3TB-backup/subvol-113-disk-0/frigate/`

---

## Key Decision: No Data Copy Needed

**Original plan**: Create new ZFS dataset, copy 120GB of recordings.

**Revised approach**: Mount the existing `subvol-113-disk-0` dataset directly via virtiofs. Pod accesses `/mnt/frigate-import/frigate/` subdirectory.

**Result**: Zero copy time, instant access.

---

## Step 1: Create ZFS Dataset
- **Script**: `./01-create-zfs-dataset.sh`
- **Status**: SKIPPED - using existing dataset instead

---

## Step 2: Copy Recordings
- **Script**: `./02-copy-recordings.sh`
- **Status**: SKIPPED - no copy needed
- **Note**: Initially started rsync (~5MB/s), then cp -a (~30MB/s), but cancelled after realizing we can mount existing dataset directly.

---

## Step 3: Create Directory Mapping
- **Script**: Manual `pvesh` command (script not updated for existing dataset)
- **Status**: SUCCESS
- **Command**:
```bash
ssh root@pumped-piglet.maas "pvesh create /cluster/mapping/dir --id frigate-import --map node=pumped-piglet,path=/local-3TB-backup/subvol-113-disk-0"
```

---

## Step 4: Attach VirtioFS to VM
- **Script**: `./04-attach-virtiofs-to-vm.sh`
- **Status**: SUCCESS
- **VM downtime**: 68 seconds
- **K3s rejoin time**: Immediate (node was Ready when checked)

---

## Step 5: Mount in VM
- **Script**: `./05-mount-in-vm.sh`
- **Status**: SUCCESS (after troubleshooting)

### Issues Encountered:

**Issue 1: SSH not working to VM**
- Direct SSH to `ubuntu@192.168.4.210` failed (port 22 connection refused)
- `qm guest exec` also failed - guest agent not installed

**Solution**: Created `00-install-guest-agent.sh` to install qemu-guest-agent via privileged pod with nsenter.

**Issue 2: Mount point existed but empty**
- `/mnt/frigate-import` existed from previous 9p attempt but virtiofs wasn't mounted
- Old 9p fstab entry needed updating

**Solution**:
```bash
ssh root@pumped-piglet.maas "qm guest exec 105 -- mount -t virtiofs frigate-import /mnt/frigate-import"
ssh root@pumped-piglet.maas "qm guest exec 105 -- sed -i 's/9p trans=virtio,version=9p2000.L/virtiofs defaults,nofail/' /etc/fstab"
```

---

## Step 5a: Update Deployment
- **Script**: `./05a-update-deployment.sh`
- **Status**: SUCCESS
- **Change**: hostPath `/mnt/frigate-import` → `/mnt/frigate-import/frigate`

---

## Step 6: Verify Frigate Access
- **Script**: `./06-verify-frigate-access.sh`
- **Status**: SUCCESS (after fixing stale pods)

### Issues Encountered:

**Issue 1: Pods in Unknown state**
- Old pods stuck in Unknown status after VM restart

**Solution**: Force delete pods, let deployment recreate them.
```bash
kubectl delete pods -n frigate --all --force --grace-period=0
```

**Issue 2: Service endpoints empty**
- Service selector had kustomize labels (`app.kubernetes.io/name`, etc.)
- Pod only had `app: frigate` label

**Solution**: Created `07-fix-service-selector.sh` to delete and recreate services.

---

## Step 7: Fix Service Selector
- **Script**: `./07-fix-service-selector.sh`
- **Status**: SUCCESS
- **Result**: `frigate.app.homelab` now working

---

## Final Status
- **Overall**: SUCCESS
- **K3s cluster**: 3/3 nodes Ready
- **Frigate pod**: Running v0.16.0
- **Old recordings**: 118GB accessible at `/import/recordings`
- **LoadBalancer IP**: 192.168.4.83
- **Ingress**: `frigate.app.homelab` working

---

## Scripts Created/Modified

| Script | Purpose |
|--------|---------|
| `00-install-guest-agent.sh` | Install qemu-guest-agent via privileged pod |
| `04-attach-virtiofs-to-vm.sh` | Attach virtiofs to VM (worked) |
| `05-mount-in-vm.sh` | Mount virtiofs via qm guest exec |
| `05a-update-deployment.sh` | Update hostPath to include /frigate |
| `06-verify-frigate-access.sh` | Verify pod can see recordings |
| `07-fix-service-selector.sh` | Fix service selector mismatch |

---

## Lessons Learned

1. **Don't copy when you can mount** - Existing dataset can be mounted directly, no need to copy 120GB.

2. **qemu-guest-agent not installed by default** - K3s VM 105 didn't have it; needed privileged pod to install.

3. **Service selector mismatch from kustomize** - When applying manifests directly (not via kustomize), services may have extra labels in selector that pods don't have.

4. **SSH may not be available** - VM may not have SSH server running; qm guest exec is more reliable if guest agent is installed.

---

## References
- [Proxmox 8.4 VirtioFS Tutorial](https://forum.proxmox.com/threads/proxmox-8-4-virtiofs-virtiofs-shared-host-folder-for-linux-and-or-windows-guest-vms.167435/)
- [VirtioFS vs 9p Performance](https://www.phoronix.com/news/Linux-5.4-VirtIO-FS)
- Plan: `/Users/10381054/.claude/plans/wiggly-percolating-sunrise.md`
