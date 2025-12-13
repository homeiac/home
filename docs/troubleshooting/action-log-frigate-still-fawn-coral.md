# Action Log: Frigate Coral Migration to still-fawn

**Date**: 2025-12-13
**Operator**: Claude Code
**GitHub Issue**: TBD
**Status**: In Progress

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
| Coral inference | ~20-30ms (expected) | |

---

## Phase 1: Cleanup pumped-piglet

### Step 1.1: Scale down Frigate
**Timestamp**: [DONE - prior to planning]
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

**Timestamp**:
**Coral moved from**: pumped-piglet
**Coral moved to**: still-fawn
**Status**:

---

## Phase 3: Setup Coral on still-fawn

### Step 3.1: Verify Coral on host
**Script**: `03-check-coral-on-host.sh`
**Timestamp**:
**Output**:
```
[PASTE]
```
**Status**:

### Step 3.2: Add USB passthrough
**Script**: `04-add-usb-passthrough.sh`
**Timestamp**:
**Output**:
```
[PASTE]
```
**Status**:

### Step 3.3: Reboot VM
**Script**: `05-reboot-vm.sh`
**Timestamp**:
**Output**:
```
[PASTE]
```
**Status**:

### Step 3.4: Wait for VM
**Script**: `06-wait-for-vm.sh`
**Timestamp**:
**Output**:
```
[PASTE]
```
**Status**:

### Step 3.5: Verify Coral in VM
**Script**: `07-check-coral-in-vm.sh`
**Timestamp**:
**Output**:
```
[PASTE]
```
**Status**:

### Step 3.6: Install libedgetpu
**Script**: `08-install-libedgetpu.sh`
**Timestamp**:
**Output**:
```
[PASTE]
```
**Status**:

### Step 3.7: Label K8s node
**Script**: `09-label-node.sh`
**Timestamp**:
**Output**:
```
[PASTE]
```
**Status**:

---

## Phase 4: GitOps Updates

### Step 4.1: Update deployment.yaml
**File**: `gitops/clusters/homelab/apps/frigate/deployment.yaml`
**Changes**:
- [ ] Remove runtimeClassName: nvidia
- [ ] Change nodeSelector to k3s-vm-still-fawn
- [ ] Remove nvidia.com/gpu limit
**Status**:

### Step 4.2: Update configmap.yaml
**File**: `gitops/clusters/homelab/apps/frigate/configmap.yaml`
**Changes**:
- [ ] hwaccel_args: preset-nvidia-h264 → preset-vaapi
**Status**:

### Step 4.3: Commit and push
**Timestamp**:
**Commit hash**:
**Status**:

---

## Phase 5: Deploy & Verify

### Step 5.1: Flux reconcile and verify
**Script**: `10-deploy-and-verify.sh`
**Timestamp**:
**Pod location**:
**Coral inference speed**:
**Cameras working**:
**Output**:
```
[PASTE]
```
**Status**:

---

## Post-Migration State

| Metric | Before | After |
|--------|--------|-------|
| Coral inference | 19ms | |
| Pod location | pumped-piglet | |
| hwaccel | NVIDIA | |
| Face recognition | GPU | |

---

## Issues Encountered

(none yet)

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | |
| **Start Time** | |
| **End Time** | |
| **Total Duration** | |

---

## Tags

frigate, coral, tpu, migration, k8s, still-fawn, pumped-piglet, vaapi, nvidia, gitops
