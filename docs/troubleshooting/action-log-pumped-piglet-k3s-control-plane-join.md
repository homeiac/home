# Action Log: Add k3s-vm-pumped-piglet as Control Plane Node

**Date**: 2025-10-21
**Operator**: Claude Code (AI Agent)
**Operation Type**: Node Addition - Control Plane
**Target**: k3s-vm-pumped-piglet (192.168.4.208)
**Status**: Planning

## Pre-Operation State

### Cluster Status
```bash
# Current cluster topology
kubectl get nodes -o wide
```

**Output**:
```
NAME                 STATUS     ROLES                       AGE    VERSION        INTERNAL-IP     EXTERNAL-IP   OS-IMAGE             KERNEL-VERSION     CONTAINER-RUNTIME
k3s-vm-chief-horse   Ready      control-plane,etcd,master   161d   v1.32.4+k3s1   192.168.4.237   <none>        Ubuntu 24.04.2 LTS   6.8.0-85-generic   containerd://2.0.4-k3s2
k3s-vm-pve           Ready      control-plane,etcd,master   159d   v1.32.4+k3s1   192.168.4.238   <none>        Ubuntu 24.04.2 LTS   6.8.0-85-generic   containerd://2.0.4-k3s2
k3s-vm-still-fawn    NotReady   control-plane,etcd,master   15d    v1.33.5+k3s1   192.168.4.236   <none>        Ubuntu 24.04.2 LTS   6.8.0-83-generic   containerd://2.1.4-k3s1
```

### Infrastructure Status
- **Proxmox Node**: pumped-piglet.maas (192.168.4.175)
- **VM ID**: 105
- **VM Name**: k3s-vm-pumped-piglet
- **VM Status**: running
- **IP Address**: 192.168.4.208
- **Resources**: 10 CPU cores, 48GB RAM, 1800GB NVMe storage
- **Storage Pools**: local-2TB-zfs (NVMe), local-20TB-zfs (HDD)

### Known Issues
- k3s-vm-still-fawn is NotReady (failed hardware - still-fawn.maas)
- Cluster needs replacement control plane node
- still-fawn running different K3s version (v1.33.5+k3s1) - will use v1.32.4+k3s1 to match working nodes

## Operation Plan

### Objective
Add k3s-vm-pumped-piglet as third control plane node to replace failed still-fawn, maintaining 3-node HA control plane configuration.

### Prerequisites Checklist
- [x] VM 105 created and running
- [x] Cloud-init configured with SSH keys and qemu-guest-agent
- [x] Network connectivity verified (192.168.4.0/24)
- [x] Kubeconfig pointing to working master (192.168.4.237)
- [ ] k3sup installed on VM 105
- [ ] SSH access verified to ubuntu@192.168.4.208

### Risk Assessment
- **Risk Level**: Medium
- **Impact if Failed**: Temporary loss of HA until issue resolved, but 2 existing masters keep cluster running
- **Rollback Plan**: Yes - remove from cluster, uninstall k3s, clean state

### Estimated Duration
- **Expected**: 10-15 minutes
- **Maximum**: 30 minutes

## Execution Log

### Phase 1: Verify VM Readiness
**Start Time**: [To be filled]

**Commands Executed**:
```bash
# Test SSH access
ssh ubuntu@192.168.4.208 "hostname && uptime"

# Verify k3sup installed
ssh ubuntu@192.168.4.208 "which k3sup || curl -sLS https://get.k3sup.dev | sh"

# Check network to existing masters
ssh ubuntu@192.168.4.208 "ping -c 3 192.168.4.237 && ping -c 3 192.168.4.238"

# Verify resources
ssh ubuntu@192.168.4.208 "free -h && df -h && nproc"
```

**Output**:
```
[To be filled during execution]
```

**Status**: [Pending]
**Notes**: [To be filled]
**End Time**: [To be filled]

---

### Phase 2: Join as Control Plane Node
**Start Time**: [To be filled]

**Commands Executed**:
```bash
# Join as control plane (server) node
k3sup join \
  --ip 192.168.4.208 \
  --user ubuntu \
  --server-ip 192.168.4.237 \
  --server \
  --k3s-version v1.32.4+k3s1
```

**Output**:
```
[To be filled during execution]
```

**Status**: [Pending]
**Notes**: Using --server flag to join as control plane, not worker
**End Time**: [To be filled]

---

### Phase 3: Verify Node Join
**Start Time**: [To be filled]

**Commands Executed**:
```bash
# Wait for node to appear
kubectl get nodes -w

# Check node status
kubectl get nodes -o wide

# Verify etcd member added
kubectl get pods -n kube-system | grep etcd

# Check control plane components
kubectl get pods -n kube-system -o wide | grep <NODE_NAME>
```

**Output**:
```
[To be filled during execution]
```

**Status**: [Pending]
**Notes**: [To be filled]
**End Time**: [To be filled]

---

### Phase 4: Remove Failed still-fawn Node
**Start Time**: [To be filled]

**Commands Executed**:
```bash
# Attempt to drain (may fail if node unreachable)
kubectl drain k3s-vm-still-fawn --ignore-daemonsets --delete-emptydir-data --force --timeout=60s

# Delete node from cluster
kubectl delete node k3s-vm-still-fawn

# Verify removal
kubectl get nodes
```

**Output**:
```
[To be filled during execution]
```

**Status**: [Pending]
**Notes**: [To be filled]
**End Time**: [To be filled]

---

### Phase 5: Label and Configure New Node
**Start Time**: [To be filled]

**Commands Executed**:
```bash
# Verify automatic labels
kubectl get nodes k3s-vm-pumped-piglet --show-labels

# Add custom labels if needed
# (e.g., kubectl label nodes k3s-vm-pumped-piglet node-role=master)

# Verify node can schedule workloads
kubectl describe node k3s-vm-pumped-piglet | grep -A 5 Taints
```

**Output**:
```
[To be filled during execution]
```

**Status**: [Pending]
**Notes**: [To be filled]
**End Time**: [To be filled]

---

### Phase 6: Verify Cluster Health
**Start Time**: [To be filled]

**Commands Executed**:
```bash
# Check all nodes
kubectl get nodes -o wide

# Check system pods
kubectl get pods -A -o wide

# Verify etcd cluster
kubectl get pods -n kube-system -l component=etcd

# Check cluster info
kubectl cluster-info
```

**Output**:
```
[To be filled during execution]
```

**Status**: [Pending]
**Notes**: [To be filled]
**End Time**: [To be filled]

---

## Post-Operation State

### Cluster Status
```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl cluster-info
```

**Output**:
```
[To be filled after operation]
```

### Verification Checks
- [ ] k3s-vm-pumped-piglet showing as Ready
- [ ] Node has control-plane,etcd,master roles
- [ ] System pods running on new node
- [ ] Etcd cluster healthy with 3 members
- [ ] still-fawn removed from cluster
- [ ] All workloads running normally

### Changes Made
1. [To be filled after operation]
2. [To be filled]
3. [To be filled]

## Issues Encountered

[To be filled during execution - use template format from action log template]

## Rollback Actions (if applicable)

[To be filled if rollback needed]

## Outcome Summary

**Overall Status**: [To be filled]
**Duration**: [To be filled]

**Success Criteria Met**:
- [ ] Node joined as control plane
- [ ] Node shows Ready status
- [ ] Etcd cluster has 3 healthy members
- [ ] still-fawn removed cleanly
- [ ] No workload disruption
- [ ] Cluster fully functional

**Metrics**:
- **Downtime**: [To be filled]
- **Workloads Affected**: [To be filled]
- **Data Loss**: No

## Lessons Learned

[To be filled after operation]

## Follow-Up Actions

- [ ] Monitor new control plane node for 24 hours
- [ ] Verify etcd backup includes new member
- [ ] Update monitoring dashboards with new node
- [ ] Update documentation with current cluster topology
- [ ] Consider rebalancing workloads across nodes

## References

- **Blueprint**: `docs/runbooks/k3s-node-addition-blueprint.md`
- **Template**: `docs/troubleshooting/action-log-template-k3s-operations.md`
- **VM Creation**: `docs/migrations/pumped-piglet-k3s-vm-creation.md`
- **Related Issue**: Replacing failed still-fawn control plane node

## Appendix

### Full Command History
```bash
[To be filled during execution - complete chronological list]
```

### Configuration Files Modified
```yaml
[To be filled if any config changes needed]
```

### Log Excerpts
```
[To be filled with relevant k3s/kubelet logs]
```

## Tags

k3s, k8s, kubernetes, kubernettes, action-log, control-plane, master, etcd, node-addition, pumped-piglet, still-fawn, migration, high-availability, ha, homelab
