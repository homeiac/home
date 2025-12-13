# Action Log Template: K8s Workload Node Migration

**Document Type**: Action Log Template
**Last Updated**: December 2025
**Blueprint**: `docs/troubleshooting/blueprint-k8s-workload-node-migration.md`

---

## Document Header

```markdown
# Action Log: <WORKLOAD> Migration from <SOURCE> to <TARGET>

**Date**: YYYY-MM-DD
**Operator**: [Name/AI Agent]
**GitHub Issue**: #XXX
**Status**: [Planning | In Progress | Completed | Failed | Rolled Back]
```

---

## CRITICAL: Pre-Flight Checklist

**THESE CHECKS ARE MANDATORY - DO NOT SKIP!**

### Checklist (verify BEFORE starting)

| Check | Command | Status |
|-------|---------|--------|
| SSH to target VM | `ssh ubuntu@k3s-vm-<target> uptime` | ✅/❌ |
| Guest agent fallback ready | `ssh root@<host>.maas "qm guest exec <VMID> -- uptime"` | ✅/❌ |
| PVC node affinity checked | `kubectl get pv -o json \| jq ...` | ✅/❌ |
| Secrets exist | `kubectl get secret -n <namespace>` | ✅/❌ |
| Hardware on target | `ssh root@<target>.maas "lsusb"` | ✅/❌ |

**If SSH broken**: All VM-access scripts must use QEMU guest agent via Proxmox host.

**If using local-path storage**: PVCs MUST be deleted and recreated on target node.

---

## Pre-Migration State

| Component | Location | Details |
|-----------|----------|---------|
| Workload | [SOURCE_NODE] | [DETAILS] |
| Hardware | [SOURCE_VM VMID] | USB passthrough |
| Storage | [STORAGE_CLASS] | [Node affinity: YES/NO] |
| Performance | [METRICS] | |

## Target State

| Component | Location | Details |
|-----------|----------|---------|
| Workload | [TARGET_NODE] | [DETAILS] |
| Hardware | [TARGET_VM VMID] | USB passthrough |
| Storage | [STORAGE_CLASS] | |
| Performance | [EXPECTED_METRICS] | |

---

## Phase 0: Pre-Flight Checks (CRITICAL!)

### Step 0.1: Verify SSH or Guest Agent
**Script**: `00-preflight-checks.sh`
**Timestamp**: [HH:MM]
**SSH Works**: [Yes/No]
**Guest Agent Fallback**: [Ready/Not Ready]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

### Step 0.2: Check PVC Node Affinity
**Storage Class**: [local-path/nfs/longhorn]
**PVCs Need Recreation**: [Yes/No]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

### Step 0.3: Verify Secrets
**Secrets Found**: [List]
**Status**: ✅/❌/⚠️

---

## Phase 1: Cleanup Source Node

### Step 1.1: Scale Down Workload
**Script**: `01-scale-down.sh` (or manual)
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

### Step 1.2: Remove USB Passthrough from Source
**Script**: `02-remove-usb-from-source.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

### Step 1.3: Remove K8s Node Label
**Script**: `03-remove-source-label.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

## Phase 2: Physical Hardware Move (USER ACTION)

**Timestamp**: [HH:MM]
**Hardware moved from**: [SOURCE]
**Hardware moved to**: [TARGET]
**Status**: ✅/❌

---

## Phase 3: Setup Target Node

### Step 3.1: Verify Hardware on Host
**Script**: `04-check-hardware-on-host.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

### Step 3.2: Add USB Passthrough
**Script**: `05-add-usb-passthrough.sh`
**Timestamp**: [HH:MM]
**Note**: Include `usb3=1` flag for USB 3.0 devices
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

### Step 3.3: Reboot VM
**Script**: `06-reboot-vm.sh`
**Timestamp**: [HH:MM]
**Status**: ✅/❌/⚠️

### Step 3.4: Wait for VM
**Script**: `07-wait-for-vm.sh`
**Timestamp**: [HH:MM]
**Method Used**: [SSH / Guest Agent]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

### Step 3.5: Verify Hardware in VM
**Script**: `08-check-hardware-in-vm.sh`
**Timestamp**: [HH:MM]
**Method Used**: [SSH / Guest Agent]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

### Step 3.6: Install Drivers (if needed)
**Script**: `09-install-drivers.sh`
**Timestamp**: [HH:MM]
**Already Installed**: [Yes/No]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️/Skipped

### Step 3.7: Label K8s Node
**Script**: `10-label-node.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

## Phase 4: Handle PVCs (CRITICAL for local-path!)

### Step 4.1: Recreate PVCs
**Script**: `11-recreate-pvcs.sh`
**Timestamp**: [HH:MM]
**PVCs Deleted**: [List]
**PVCs Recreated**: [List]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️/Skipped (if not using local-path)

---

## Phase 5: GitOps Updates

### Step 5.1: Update deployment.yaml
**File**: [PATH]
**Changes**:
- [ ] Change removed: [e.g., runtimeClassName: nvidia]
- [ ] nodeSelector updated: [OLD] → [NEW]
- [ ] Resource limits removed: [e.g., nvidia.com/gpu]
**Status**: ✅/❌

### Step 5.2: Update configmap.yaml
**File**: [PATH]
**Changes**:
- [ ] hwaccel updated: [OLD] → [NEW]
**Status**: ✅/❌

### Step 5.3: Commit and Push
**Timestamp**: [HH:MM]
**Commit Hash**: [HASH]
**Status**: ✅/❌

---

## Phase 6: Deploy & Verify

### Step 6.1: Flux Reconcile
**Script**: `12-deploy-and-verify.sh`
**Timestamp**: [HH:MM]
**Pod Location**: [NODE]
**Hardware Working**: [Yes/No]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

## Post-Migration State

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| [Metric 1] | [VALUE] | [VALUE] | [+/-] |
| [Metric 2] | [VALUE] | [VALUE] | [+/-] |
| Node | [SOURCE] | [TARGET] | Migrated |

---

## Issues Encountered

### Issue 1: [Title]
**Severity**: [Low/Medium/High/Critical]
**Time Lost**: [X minutes]
**Symptoms**:
- [Symptom 1]
- [Symptom 2]

**Root Cause**: [Analysis]

**Resolution**:
```bash
[Commands used]
```

**Prevention**: [How to prevent in future]

---

## Lessons Learned

### What Went Wrong
1. [Issue 1]
2. [Issue 2]

### What Went Right
1. [Success 1]
2. [Success 2]

### Additions to Blueprint
- [ ] [New check/step to add]
- [ ] [Process improvement]

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | [✅ Completed / ❌ Failed / ⚠️ Partial] |
| **Start Time** | [HH:MM] |
| **End Time** | [HH:MM] |
| **Total Duration** | [X minutes] |
| **Issues Encountered** | [N] |
| **Scripts Created/Used** | [N] |

---

## Files Modified

| File | Change |
|------|--------|
| [PATH] | [DESCRIPTION] |

## Commits

- `[HASH]` - [MESSAGE]

---

## Follow-Up Actions

- [ ] Monitor stability for 24 hours
- [ ] Update documentation
- [ ] Close GitHub issue
- [ ] Store lessons in OpenMemory

---

## Tags

[workload], [hardware], migration, k8s, [source-node], [target-node], [storage-class], lessons-learned
