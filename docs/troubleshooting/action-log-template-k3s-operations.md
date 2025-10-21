# Action Log Template - K3s Operations

**Document Type**: Action Log Template
**Last Updated**: 2025-10-21
**Purpose**: Standard template for documenting K3s cluster operations

## Document Header

```
# Action Log: [Operation Name]

**Date**: YYYY-MM-DD
**Operator**: [Name/AI Agent]
**Operation Type**: [Node Addition | Node Removal | Upgrade | Migration | Recovery]
**Target**: [Node name or cluster component]
**Status**: [Planning | In Progress | Completed | Failed | Rolled Back]
```

## Pre-Operation State

### Cluster Status
```bash
# Document current cluster state
kubectl get nodes -o wide
kubectl get pods -A --field-selector spec.nodeName=<TARGET_NODE>
kubectl top nodes
```

**Output**:
```
[Paste command output here]
```

### Infrastructure Status
- **Proxmox Node**: [node name]
- **VM ID**: [VMID]
- **VM Status**: [running/stopped]
- **IP Address**: [x.x.x.x]
- **Resources**: [CPU/RAM/Storage]

### Known Issues
- [List any known issues or warnings]
- [Expected state before operation]

## Operation Plan

### Objective
[Clear statement of what this operation aims to achieve]

### Prerequisites Checklist
- [ ] Prerequisite 1
- [ ] Prerequisite 2
- [ ] Prerequisite 3

### Risk Assessment
- **Risk Level**: [Low | Medium | High]
- **Impact if Failed**: [Description]
- **Rollback Plan**: [Yes/No - describe if yes]

### Estimated Duration
- **Expected**: [time estimate]
- **Maximum**: [maximum acceptable time]

## Execution Log

### Phase 1: [Phase Name]
**Start Time**: [HH:MM:SS]

**Commands Executed**:
```bash
[command 1]
[command 2]
```

**Output**:
```
[Paste output here]
```

**Status**: ✅ Success / ❌ Failed / ⚠️ Warning
**Notes**: [Any observations or issues]
**End Time**: [HH:MM:SS]

---

### Phase 2: [Phase Name]
**Start Time**: [HH:MM:SS]

**Commands Executed**:
```bash
[command]
```

**Output**:
```
[output]
```

**Status**: ✅ / ❌ / ⚠️
**Notes**: [notes]
**End Time**: [HH:MM:SS]

---

[Repeat for all phases]

## Post-Operation State

### Cluster Status
```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl cluster-info
```

**Output**:
```
[Paste output here]
```

### Verification Checks
- [ ] All nodes showing as Ready
- [ ] System pods running on new node
- [ ] Workloads rescheduled appropriately
- [ ] Network connectivity verified
- [ ] Storage accessible

### Changes Made
1. [Change 1 - be specific]
2. [Change 2]
3. [Change 3]

## Issues Encountered

### Issue 1: [Description]
**Severity**: [Low | Medium | High | Critical]
**Time Encountered**: [HH:MM:SS]

**Symptoms**:
- [Symptom 1]
- [Symptom 2]

**Root Cause**:
[Analysis of what caused the issue]

**Resolution**:
```bash
[Commands used to resolve]
```

**Prevention**:
[How to prevent this in future operations]

---

[Repeat for each issue]

## Rollback Actions (if applicable)

**Trigger**: [What necessitated rollback]
**Rollback Start**: [HH:MM:SS]

**Steps Taken**:
1. [Rollback step 1]
2. [Rollback step 2]

**Commands**:
```bash
[rollback commands]
```

**Rollback Status**: ✅ Successful / ❌ Failed
**End Time**: [HH:MM:SS]

## Outcome Summary

**Overall Status**: [Success | Partial Success | Failed]
**Duration**: [Total time from start to finish]

**Success Criteria Met**:
- [x] Criterion 1
- [x] Criterion 2
- [ ] Criterion 3 (not met - explain why)

**Metrics**:
- **Downtime**: [duration or "None"]
- **Workloads Affected**: [number and list]
- **Data Loss**: [Yes/No - describe if yes]

## Lessons Learned

### What Went Well
1. [Positive observation 1]
2. [Positive observation 2]

### What Could Be Improved
1. [Improvement 1]
2. [Improvement 2]

### Documentation Updates Needed
- [ ] Update blueprint: [specific changes]
- [ ] Update runbook: [specific changes]
- [ ] Update architecture docs: [specific changes]

## Follow-Up Actions

- [ ] Action item 1 - [Owner] - [Due date]
- [ ] Action item 2 - [Owner] - [Due date]
- [ ] Monitor cluster for [X hours/days]
- [ ] Update related documentation

## References

- **Blueprint**: [Link to relevant blueprint]
- **Related Tickets**: [Issue numbers or links]
- **Previous Operations**: [Links to similar action logs]
- **External Docs**: [Any external references used]

## Appendix

### Full Command History
```bash
[Complete chronological list of all commands executed]
```

### Configuration Files Modified
```yaml
# filename: /path/to/file
[Content changes]
```

### Log Excerpts
```
[Relevant log excerpts from k3s, kubelet, etc.]
```

## Tags

k3s, k8s, kubernetes, kubernettes, action-log, operations, [specific operation type], [node name], homelab
