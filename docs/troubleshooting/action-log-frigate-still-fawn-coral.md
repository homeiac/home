# Action Log: Frigate Coral Migration to still-fawn

**Date**: 2025-12-13
**Operator**: Claude Code
**GitHub Issue**: N/A (power optimization task)
**Status**: Completed

## Pre-Migration State

| Component | Location | Details |
|-----------|----------|---------|
| Frigate 0.16 | k3s-vm-pumped-piglet-gpu | NVIDIA hwaccel |
| Coral USB TPU | pumped-piglet VM 105 | USB passthrough |
| GPU | RTX 3070 | NVDEC + face recognition |
| Coral inference | ~19ms | |

## Target State

| Component | Location | Details |
|-----------|----------|---------|
| Frigate 0.16 | k3s-vm-still-fawn | AMD VAAPI hwaccel |
| Coral USB TPU | still-fawn VM 108 | USB passthrough |
| GPU | AMD (VAAPI only) | Video decode only |
| Coral inference | ~32ms (actual) | |

---

## Phase 1: Cleanup pumped-piglet

### Step 1.1: Scale down Frigate
**Timestamp**: 09:00
**Status**: ✅

### Step 1.2: Remove USB passthrough from pumped-piglet
**Script**: `01-remove-usb-from-piglet.sh`
**Timestamp**: 09:13
**Output**:
```
Removing USB passthrough from pumped-piglet VM 105...
update VM 105: -delete usb0,usb1
Done. USB passthrough removed.
```
**Status**: ✅

### Step 1.3: Remove K8s node label
**Script**: `02-remove-piglet-label.sh`
**Timestamp**: 09:13
**Output**:
```
Removing coral.ai/tpu label from pumped-piglet node...
node/k3s-vm-pumped-piglet-gpu unlabeled
Done.
```
**Status**: ✅

---

## Phase 2: Physical Coral Move (USER)

**Timestamp**: ~09:15
**Coral moved from**: pumped-piglet
**Coral moved to**: still-fawn
**Status**: ✅

---

## Phase 3: Setup Coral on still-fawn

### Step 3.1: Verify Coral on host
**Script**: `03-check-coral-on-host.sh`
**Timestamp**: 09:16
**Output**:
```
Checking for Coral USB on still-fawn host...
Bus 004 Device 006: ID 18d1:9302 Google Inc.
Coral detected on host.
```
**Status**: ✅

### Step 3.2: Add USB passthrough
**Script**: `04-add-usb-passthrough.sh`
**Timestamp**: 09:16
**Output**:
```
Adding USB passthrough to still-fawn VM 108...
update VM 108: -usb0 host=1a6e:089a,usb3=1 -usb1 host=18d1:9302,usb3=1
USB passthrough configured. VM reboot required.
```
**Status**: ✅

### Step 3.3: Reboot VM
**Script**: `05-reboot-vm.sh`
**Timestamp**: 09:17
**Output**:
```
Rebooting still-fawn VM 108...
Reboot initiated.
```
**Status**: ✅

### Step 3.4: Wait for VM
**Script**: `06-wait-for-vm.sh`
**Timestamp**: 09:17-09:20
**Issue**: SSH to K3s VMs broken (connection refused)
**Workaround**: Used QEMU guest agent via Proxmox host
**Status**: ⚠️ Script failed, used workaround

### Step 3.5: Verify Coral in VM
**Script**: `07-check-coral-in-vm.sh` (updated to use guest agent)
**Timestamp**: 09:22
**Output**:
```
Checking for Coral USB inside still-fawn VM 108...
Coral detected inside VM.
Bus 010 Device 002: ID 18d1:9302 Google Inc.
```
**Status**: ✅

### Step 3.6: Install libedgetpu
**Script**: `08-install-libedgetpu.sh` (updated to use guest agent)
**Timestamp**: 09:23
**Output**:
```
Checking libedgetpu installation in VM 108...
libedgetpu already installed.
```
**Status**: ✅ (already installed)

### Step 3.7: Label K8s node
**Script**: `09-label-node.sh`
**Timestamp**: 09:24
**Output**:
```
Labeling k3s-vm-still-fawn with coral.ai/tpu=usb...
node/k3s-vm-still-fawn not labeled
Node labeled.
```
**Status**: ✅

---

## Phase 4: GitOps Updates

### Step 4.1: Update deployment.yaml
**File**: `gitops/clusters/homelab/apps/frigate/deployment.yaml`
**Changes**:
- [x] Remove runtimeClassName: nvidia
- [x] Change nodeSelector to k3s-vm-still-fawn
- [x] Remove nvidia.com/gpu limit
**Status**: ✅

### Step 4.2: Update configmap.yaml
**File**: `gitops/clusters/homelab/apps/frigate/configmap.yaml`
**Changes**:
- [x] hwaccel_args: preset-nvidia-h264 → preset-vaapi
**Status**: ✅

### Step 4.3: Commit and push
**Timestamp**: 09:25
**Commit hash**: 1bae49f
**Status**: ✅

---

## Phase 5: Deploy & Verify

### Step 5.1: Initial deploy attempt
**Script**: `10-deploy-and-verify.sh`
**Timestamp**: 09:26
**Issue**: Pod stuck in Pending - PV node affinity to pumped-piglet
**Status**: ❌

### Step 5.2: Recreate PVCs
**Script**: `11-recreate-pvcs.sh` (created during troubleshooting)
**Timestamp**: 09:30
**Output**:
```
=== Recreating Frigate PVCs for still-fawn ===
Deleting existing PVCs (if any)...
Waiting for PVs to be cleaned up...
Reconciling Flux to recreate PVCs...
PVCs created.
```
**Status**: ✅

### Step 5.3: Final verification
**Timestamp**: 09:31
**Pod location**: k3s-vm-still-fawn ✅
**Coral inference speed**: 32.6ms ✅
**Cameras working**: 3/3 (old_ip_camera, trendnet_ip_572w, reolink_doorbell) ✅
**Status**: ✅

---

## Post-Migration State

| Metric | Before | After |
|--------|--------|-------|
| Coral inference | 19ms | 32.6ms |
| Pod location | pumped-piglet | still-fawn |
| hwaccel | NVIDIA | VAAPI |
| Face recognition | GPU | CPU |
| Cameras | 3 | 3 |

---

## Issues Encountered

### Issue 1: SSH to K3s VMs Broken
**Severity**: Medium
**Time Lost**: ~10 minutes
**Symptoms**:
- `ssh ubuntu@k3s-vm-still-fawn` returned "Connection refused"
- Scripts 06-08 using SSH failed

**Root Cause**: Unknown (SSH service issue in K3s VMs, needs investigation)

**Workaround**:
- Updated scripts 07-08 to use QEMU guest agent via Proxmox host
- `ssh root@still-fawn.maas "qm guest exec 108 -- <command>"`

**Prevention**:
- Check SSH connectivity before migration
- Always have guest agent fallback in scripts
- Store in OpenMemory for future reference

---

### Issue 2: PVC Node Affinity
**Severity**: High
**Time Lost**: ~15 minutes
**Symptoms**:
- Pod stuck in `Pending` state
- Events: `0/3 nodes are available: 1 node(s) didn't match PersistentVolume's node affinity`

**Root Cause**:
- local-path storage class creates PVs with node affinity
- Existing PVs were bound to k3s-vm-pumped-piglet-gpu
- Cannot schedule pod on still-fawn with pumped-piglet PVs

**Resolution**:
- Created `11-recreate-pvcs.sh` (idempotent)
- Delete PVCs, let Flux recreate them
- New PVs created on still-fawn with correct node affinity

**Prevention**:
- **ALWAYS check PVC/PV node affinity when migrating workloads between nodes**
- Add PVC recreation step to migration blueprint
- Consider using shared storage (NFS, Longhorn) for portable workloads

---

### Issue 3: Using One-Liners Instead of Scripts
**Severity**: Low (process violation)
**Time Lost**: ~5 minutes
**Symptoms**:
- Initially ran commands directly instead of using prepared scripts
- User had to remind to use scripts

**Root Cause**:
- Expedience over process discipline
- Scripts existed but were bypassed

**Prevention**:
- **ALWAYS use scripts, even for one-liners**
- Scripts provide: documentation, idempotency, repeatability, audit trail

---

### Issue 4: Forgot to Check Secrets
**Severity**: Low (got lucky)
**Symptoms**:
- Did not verify K8s secrets existed for still-fawn

**Root Cause**:
- Assumed secrets would "just work"
- Did not include secrets check in plan

**Resolution**: Secrets are namespace-scoped, not node-scoped, so they worked anyway

**Prevention**:
- Add secrets verification step to migration checklist
- `kubectl get secret -n <namespace>` before migration

---

## Lessons Learned

### What Went Wrong

1. **Did not verify SSH connectivity** before creating scripts that depend on SSH
2. **Did not consider PVC node affinity** - local-path creates node-bound PVs
3. **Ran one-liners** instead of using prepared scripts (process violation)
4. **Skipped secrets verification** (got lucky this time)
5. **Plan was incomplete** - missing critical steps like PVC handling

### What Went Right

1. **Coral detection worked immediately** - USB 3.0 passthrough configured correctly
2. **libedgetpu already installed** - no manual intervention needed
3. **GitOps/Flux worked smoothly** - manifests applied correctly
4. **Created idempotent script** for PVC recreation during troubleshooting
5. **User caught mistakes** - enforced script usage and proper planning

### Additions to Blueprint

For future node migrations, add these steps:

1. **Pre-flight checks**:
   - [ ] Verify SSH connectivity to target VM
   - [ ] Have QEMU guest agent fallback ready
   - [ ] Check PVC/PV node affinity
   - [ ] Verify secrets exist in namespace

2. **PVC handling**:
   - [ ] If using local-path: delete and recreate PVCs
   - [ ] If using shared storage: no action needed
   - [ ] Script: `11-recreate-pvcs.sh`

3. **Post-migration**:
   - [ ] Verify pod scheduled on correct node
   - [ ] Check all services (Coral, cameras, MQTT)
   - [ ] Update DNS if needed

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | ✅ Completed |
| **Start Time** | 09:00 |
| **End Time** | 09:35 |
| **Total Duration** | 35 minutes |
| **Issues Encountered** | 4 |
| **Scripts Created** | 11 |

---

## Files Modified

| File | Change |
|------|--------|
| `gitops/clusters/homelab/apps/frigate/deployment.yaml` | nodeSelector, remove NVIDIA |
| `gitops/clusters/homelab/apps/frigate/configmap.yaml` | preset-vaapi |
| `scripts/frigate/still-fawn-coral/*.sh` | 11 migration scripts |

## Commits

- `1bae49f` - feat(frigate): migrate Coral TPU from pumped-piglet to still-fawn
- `cafbf62` - feat(frigate): add idempotent PVC recreation script for node migration

---

## TODO: Home Assistant DNS for frigate.app.homelab

**Not yet resolved**: Home Assistant needs to resolve `frigate.app.homelab` to reach Frigate via Traefik.

This is a **Home Assistant DNS issue**, NOT OPNsense. Need to investigate:
- Home Assistant's DNS configuration
- Whether HA container can resolve `.homelab` domain
- May need to add entry to HA's /etc/hosts or configure DNS server

**Reference**: Review existing docs on DNS setup (noted as "not straightforward")

---

## Tags

frigate, coral, tpu, migration, k8s, still-fawn, pumped-piglet, vaapi, nvidia, gitops, pvc, local-path, node-affinity, ssh, qemu-guest-agent, lessons-learned
