# K3s Node Addition Blueprint

**Document Type**: Blueprint
**Last Updated**: 2025-10-21
**Status**: Active

## Purpose

Minimal working procedure for adding K3s control plane nodes to the homelab cluster.

## Prerequisites

- [ ] Proxmox VM created with Ubuntu 24.04 LTS
- [ ] VM accessible via SSH: `ssh ubuntu@<NEW_NODE_IP>`
- [ ] kubectl configured with working kubeconfig

## Procedure: Add Control Plane Node

### Step 1: Get K3s Version and Token

```bash
# Check cluster version
kubectl get nodes -o wide
# Note the VERSION column (e.g., v1.32.4+k3s1)

# Get join token from existing master (using qm guest exec if SSH fails)
ssh root@<PROXMOX_HOST>.maas "qm guest exec <VM_ID> -- cat /var/lib/rancher/k3s/server/node-token"
```

### Step 2: Manual K3s Installation on New Node

**THIS IS THE COMMAND THAT WORKS:**

```bash
ssh ubuntu@<NEW_NODE_IP> "curl -sfL https://get.k3s.io | \
  K3S_URL=https://<MASTER_IP>:6443 \
  K3S_TOKEN='<TOKEN_FROM_STEP_1>' \
  INSTALL_K3S_VERSION=<VERSION_FROM_STEP_1> \
  sh -s - server"
```

**Example (actual working command from 2025-10-21):**
```bash
ssh -i ~/.ssh/id_ed25519_pve ubuntu@192.168.4.208 "curl -sfL https://get.k3s.io | \
  K3S_URL=https://192.168.4.237:6443 \
  K3S_TOKEN='K103e5597417ab93ecbc26766cdd781a42e2150b1bc2aa844149f1307c8a8656148::server:4b29815ba0333c8cc08d6bc71f063bc0' \
  INSTALL_K3S_VERSION=v1.32.4+k3s1 \
  sh -s - server"
```

### Step 3: Remove Failed Node (if replacing)

```bash
# Delete old failed node to unblock etcd
kubectl delete node <OLD_NODE_NAME>
```

### Step 4: Verify Success

```bash
# Check node appears and is Ready
kubectl get nodes -o wide

# Verify system pods scheduled on new node
kubectl get pods -A -o wide | grep <NEW_NODE_NAME>
```

**Expected result:** Node appears with `control-plane,etcd,master` roles and `Ready` status within 60 seconds.

## Rollback

```bash
# Remove from cluster
kubectl delete node <NODE_NAME>

# Uninstall on VM
ssh ubuntu@<NODE_IP> "/usr/local/bin/k3s-server-uninstall.sh"
```

## Related Documents

- Action Log Template: `docs/troubleshooting/action-log-template-k3s-operations.md`
- VM Creation Blueprint: `docs/migrations/pumped-piglet-k3s-vm-creation.md`
- K3s Cluster Architecture: `docs/architecture/k3s-cluster-topology.md`

## Tags

k3s, k8s, kubernetes, kubernettes, cluster, node, join, worker, control-plane, master, k3sup, homelab, proxmox
