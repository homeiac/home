# K3s Node Addition Blueprint

**Document Type**: Blueprint
**Last Updated**: 2025-10-21
**Status**: Active

## Purpose

Standard procedure for adding new K3s nodes to the homelab cluster, whether as control plane masters or worker nodes.

## Prerequisites

### Infrastructure Requirements
- [ ] Proxmox VM created with Ubuntu 24.04 LTS
- [ ] VM has adequate resources (CPU, RAM, storage)
- [ ] Cloud-init configured with qemu-guest-agent
- [ ] Network connectivity to existing cluster nodes
- [ ] SSH keys deployed for passwordless access

### Software Requirements
- [ ] k3sup installed locally or on target VM
- [ ] kubectl configured with working kubeconfig
- [ ] Existing K3s cluster accessible
- [ ] K3s version compatibility verified

### Network Requirements
- [ ] Static IP assigned to new node
- [ ] DNS resolution working for cluster nodes
- [ ] Ports accessible: 6443 (API), 10250 (kubelet), 8472 (flannel)
- [ ] Firewall rules allow cluster traffic

## Decision Matrix

### Control Plane vs Worker Node

**Add as Control Plane (Master) when:**
- Cluster has < 3 control plane nodes
- High availability is priority
- Node has sufficient resources (8GB+ RAM, 4+ cores)
- Etcd quorum needs to be maintained

**Add as Worker Node when:**
- Cluster already has 3+ control plane nodes
- Node is for workload execution only
- Resources are limited
- Simplicity is preferred

### K3s Version Selection

**Use SAME version** as existing nodes:
```bash
# Check existing versions
kubectl get nodes -o wide

# Match the version (e.g., v1.32.4+k3s1)
```

**Upgrade cluster first** if versions are mixed or outdated.

## Standard Procedure

### Phase 1: Verify VM Readiness

```bash
# Check VM is accessible
ssh ubuntu@<NEW_NODE_IP> "hostname && uptime"

# Verify k3sup is installed
ssh ubuntu@<NEW_NODE_IP> "which k3sup || curl -sLS https://get.k3sup.dev | sh"

# Check network connectivity to master
ssh ubuntu@<NEW_NODE_IP> "ping -c 3 <MASTER_IP>"
```

### Phase 2: Join Node to Cluster

**For Worker Node:**
```bash
k3sup join \
  --ip <NEW_NODE_IP> \
  --user ubuntu \
  --server-ip <MASTER_IP> \
  --k3s-version <MATCHING_VERSION>
```

**For Control Plane Node:**
```bash
k3sup join \
  --ip <NEW_NODE_IP> \
  --user ubuntu \
  --server-ip <MASTER_IP> \
  --server \
  --k3s-version <MATCHING_VERSION>
```

### Phase 3: Verify Node Join

```bash
# Wait for node to appear (may take 30-60 seconds)
kubectl get nodes -w

# Check node becomes Ready
kubectl get nodes -o wide

# Verify node labels
kubectl get nodes --show-labels | grep <NEW_NODE_NAME>

# Check kubelet is running
ssh ubuntu@<NEW_NODE_IP> "sudo systemctl status k3s-agent"
```

### Phase 4: Post-Join Configuration

**Label nodes for workload placement:**
```bash
# Example: Label for GPU workloads
kubectl label nodes <NODE_NAME> gpu=nvidia-rtx-3070

# Example: Label for storage node
kubectl label nodes <NODE_NAME> storage=local-zfs

# Example: Taint for specialized workloads
kubectl taint nodes <NODE_NAME> workload=ai:NoSchedule
```

**Verify cluster health:**
```bash
# Check all nodes Ready
kubectl get nodes

# Check system pods running
kubectl get pods -n kube-system -o wide

# Verify etcd health (for control plane)
kubectl get pods -n kube-system | grep etcd
```

### Phase 5: Workload Verification

```bash
# Deploy test workload
kubectl run test-nginx --image=nginx --restart=Never

# Verify pod scheduled on new node
kubectl get pods -o wide | grep <NODE_NAME>

# Clean up test workload
kubectl delete pod test-nginx
```

## Common Issues and Solutions

### Issue: Node Stuck in NotReady

**Diagnosis:**
```bash
kubectl describe node <NODE_NAME>
ssh ubuntu@<NODE_IP> "sudo journalctl -u k3s-agent -n 100"
```

**Common Causes:**
- CNI plugin not ready (wait 2-3 minutes)
- Network connectivity issues
- K3s service failed to start
- Disk space full

**Solutions:**
```bash
# Restart k3s service
ssh ubuntu@<NODE_IP> "sudo systemctl restart k3s-agent"

# Check disk space
ssh ubuntu@<NODE_IP> "df -h"

# Verify network
ssh ubuntu@<NODE_IP> "ip route show && ip addr show"
```

### Issue: Cannot Connect to Master

**Diagnosis:**
```bash
# Test connectivity
ssh ubuntu@<NODE_IP> "curl -k https://<MASTER_IP>:6443"

# Check firewall
ssh ubuntu@<MASTER_IP> "sudo ufw status"
```

**Solutions:**
```bash
# Allow k3s ports on master
ssh ubuntu@<MASTER_IP> "sudo ufw allow 6443/tcp"
ssh ubuntu@<MASTER_IP> "sudo ufw allow 10250/tcp"
```

### Issue: Version Mismatch

**Error**: "K3s version mismatch between nodes"

**Solution**:
```bash
# Remove node
kubectl delete node <NODE_NAME>

# Reinstall with correct version
k3sup join \
  --ip <NODE_IP> \
  --user ubuntu \
  --server-ip <MASTER_IP> \
  --k3s-version v1.32.4+k3s1  # Match existing version
```

## Rollback Procedure

If node join fails or causes issues:

```bash
# 1. Remove from cluster
kubectl delete node <NODE_NAME>

# 2. Uninstall k3s on target VM
ssh ubuntu@<NODE_IP> "/usr/local/bin/k3s-agent-uninstall.sh"

# 3. Clean up files
ssh ubuntu@<NODE_IP> "sudo rm -rf /var/lib/rancher/k3s"

# 4. Verify cluster health
kubectl get nodes
kubectl get pods -A
```

## Post-Addition Checklist

- [ ] Node shows as Ready in `kubectl get nodes`
- [ ] System pods running on new node
- [ ] Node has appropriate labels
- [ ] Workloads can schedule on new node
- [ ] Network connectivity verified
- [ ] Documentation updated with new node

## Reference Commands

```bash
# Get kubeconfig from master (if needed)
k3sup install \
  --ip <MASTER_IP> \
  --user ubuntu \
  --merge \
  --local-path ~/.kube/config \
  --context homelab

# View cluster info
kubectl cluster-info
kubectl get nodes -o wide
kubectl top nodes  # requires metrics-server

# Check k3s service status
ssh ubuntu@<NODE_IP> "sudo systemctl status k3s-agent"

# View k3s logs
ssh ubuntu@<NODE_IP> "sudo journalctl -u k3s-agent -f"

# Remove node cleanly
kubectl drain <NODE_NAME> --ignore-daemonsets --delete-emptydir-data
kubectl delete node <NODE_NAME>
```

## Related Documents

- Action Log Template: `docs/troubleshooting/action-log-template-k3s-operations.md`
- VM Creation Blueprint: `docs/migrations/pumped-piglet-k3s-vm-creation.md`
- K3s Cluster Architecture: `docs/architecture/k3s-cluster-topology.md`

## Tags

k3s, k8s, kubernetes, kubernettes, cluster, node, join, worker, control-plane, master, k3sup, homelab, proxmox
