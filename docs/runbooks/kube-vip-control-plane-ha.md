# kube-vip Control Plane HA Runbook

## Overview

This runbook covers the setup, operation, and troubleshooting of kube-vip for K3s control plane high availability.

**VIP Address**: `192.168.4.79`
**Port**: `6443`
**Mode**: ARP (Layer 2)

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │         VIP: 192.168.4.79:6443      │
                    │         (Floating IP)               │
                    └──────────────┬──────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
   ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
   │ k3s-vm-pve       │ │ k3s-vm-pumped-   │ │ k3s-vm-fun-      │
   │ 192.168.4.238    │ │ piglet-gpu       │ │ bedbug           │
   │                  │ │ 192.168.4.210    │ │ 192.168.4.203    │
   │ kube-vip pod     │ │ kube-vip pod     │ │ kube-vip pod     │
   │ (follower)       │ │ (LEADER)         │ │ (follower)       │
   └──────────────────┘ └──────────────────┘ └──────────────────┘
```

Only the leader node responds to the VIP. Leader election uses Kubernetes leases.

## Prerequisites

- K3s multi-server cluster with embedded etcd
- All control plane nodes must have VIP in API server certificate SANs
- MetalLB configured (kube-vip handles control plane only, not services)

## Configuration Files

| File | Purpose |
|------|---------|
| `proxmox/homelab/config/k3s.yaml` | K3s cluster config (VIP, nodes, TLS-SAN) |
| `proxmox/homelab/src/homelab/k3s_manager.py` | Python orchestrator for TLS-SAN config |
| `gitops/clusters/homelab/infrastructure/kube-vip/` | Flux manifests (RBAC, DaemonSet) |

## Initial Setup

### Step 1: Configure TLS-SAN on All Control Plane Nodes

The API server certificate must include the VIP in its Subject Alternative Names (SANs).

```bash
cd ~/code/home/proxmox/homelab

# Dry run first
poetry run python -m homelab.k3s_manager prepare-kube-vip --dry-run

# Apply (configures TLS-SAN, rotates certs one node at a time)
poetry run python -m homelab.k3s_manager prepare-kube-vip
```

This command:
1. Writes `/etc/rancher/k3s/config.yaml` on each node with `tls-san` entries
2. Deletes API server cert and restarts K3s (one node at a time)
3. Verifies VIP is in new certificate

**The script is idempotent** - it skips nodes that already have the VIP in their cert.

### Step 2: Deploy kube-vip via Flux

```bash
cd ~/code/home

# If not already committed
git add gitops/clusters/homelab/infrastructure/kube-vip/
git commit -m "feat(k3s): add kube-vip for control plane HA"
git push

# Reconcile
flux reconcile kustomization flux-system --with-source
```

### Step 3: Update kubeconfig

```bash
sed -i '' 's/OLD_IP/192.168.4.79/' ~/kubeconfig

# Verify
kubectl get nodes
```

## Operations

### Check VIP Status

```bash
# Ping the VIP
ping 192.168.4.79

# Check which node is leader
kubectl get lease kube-vip-lease -n kube-system -o jsonpath='{.spec.holderIdentity}'

# Check all kube-vip pods
kubectl get pods -n kube-system -l app.kubernetes.io/name=kube-vip -o wide
```

### Check TLS-SAN Configuration

```bash
cd ~/code/home/proxmox/homelab
poetry run python -m homelab.k3s_manager status
```

### Force Leader Election

If you need to move the VIP to a different node:

```bash
# Delete the lease (a new leader will be elected)
kubectl delete lease kube-vip-lease -n kube-system

# Check new leader
kubectl get lease kube-vip-lease -n kube-system -o jsonpath='{.spec.holderIdentity}'
```

### View kube-vip Logs

```bash
# Logs from all kube-vip pods
kubectl logs -n kube-system -l app.kubernetes.io/name=kube-vip --tail=50

# Logs from specific node
kubectl logs -n kube-system -l app.kubernetes.io/name=kube-vip --field-selector spec.nodeName=k3s-vm-pumped-piglet-gpu
```

## Troubleshooting

### VIP Not Responding

1. **Check kube-vip pods are running:**
   ```bash
   kubectl get pods -n kube-system -l app.kubernetes.io/name=kube-vip
   ```

2. **Check leader election:**
   ```bash
   kubectl get lease kube-vip-lease -n kube-system
   ```

3. **Check kube-vip logs for errors:**
   ```bash
   kubectl logs -n kube-system -l app.kubernetes.io/name=kube-vip | grep -i error
   ```

4. **Verify VIP is bound on leader node:**
   ```bash
   # SSH to leader node and check
   ssh root@<proxmox-host>.maas "qm guest exec <vmid> -- ip addr show eth0"
   ```

### "no subnet provided" Error

Add `vip_cidr` to the DaemonSet environment:

```yaml
- name: vip_cidr
  value: "24"
```

### Certificate Error When Connecting to VIP

The API server cert doesn't have the VIP in SANs. Run:

```bash
cd ~/code/home/proxmox/homelab
poetry run python -m homelab.k3s_manager prepare-kube-vip
```

### kube-vip Pod CrashLoopBackOff

1. Check logs: `kubectl logs -n kube-system <pod-name>`
2. Common causes:
   - Missing `vip_cidr`
   - Wrong interface name (`vip_interface`)
   - Network policy blocking ARP

### Adding a New Control Plane Node

1. Add the node to `proxmox/homelab/config/k3s.yaml`:
   ```yaml
   control_plane_nodes:
     - name: k3s-vm-new-node
       proxmox_host: hostname
       vmid: 123
       ip: 192.168.4.xxx
   ```

2. Add its IP to `tls_san` list

3. Run the prepare script:
   ```bash
   poetry run python -m homelab.k3s_manager prepare-kube-vip
   ```
   (Only the new node will be configured; existing nodes are skipped)

4. kube-vip DaemonSet will automatically deploy to the new node

## Recovery Procedures

### Full Cluster Recreation

1. Deploy K3s on control plane nodes

2. Configure TLS-SAN:
   ```bash
   cd ~/code/home/proxmox/homelab
   poetry run python -m homelab.k3s_manager prepare-kube-vip
   ```

3. Bootstrap Flux (it will deploy kube-vip automatically):
   ```bash
   flux bootstrap github \
     --owner=homeiac \
     --repository=home \
     --path=gitops/clusters/homelab
   ```

4. Update kubeconfig to use VIP

### Single Node Recovery

If a control plane node is rebuilt:

1. Join it to the K3s cluster
2. Run `prepare-kube-vip` - it will configure TLS-SAN on the new node only
3. kube-vip DaemonSet auto-deploys via Flux

## Configuration Reference

### k3s.yaml

```yaml
cluster:
  control_plane_vip: 192.168.4.79
  vip_interface: eth0
  api_port: 6443

kube_vip:
  enabled: true
  version: "v0.8.7"
  mode: arp
  leader_election: true

control_plane_nodes:
  - name: k3s-vm-pve
    proxmox_host: pve
    vmid: 107
    ip: 192.168.4.238
    is_primary: true
  # ... more nodes

tls_san:
  - 192.168.4.79  # VIP - required!
  - 192.168.4.238
  - 192.168.4.210
  - 192.168.4.203
  - k3s.homelab
```

### DaemonSet Environment Variables

| Variable | Value | Description |
|----------|-------|-------------|
| `vip_address` | `192.168.4.79` | The floating VIP |
| `vip_cidr` | `24` | Subnet mask |
| `vip_interface` | `eth0` | Network interface |
| `vip_arp` | `true` | Use ARP for L2 networks |
| `cp_enable` | `true` | Control plane mode |
| `svc_enable` | `false` | Disable service LB (MetalLB handles this) |
| `vip_leaderelection` | `true` | Use lease-based leader election |

## Related Documentation

- [kube-vip Official Docs](https://kube-vip.io/docs/)
- [K3s HA with Embedded etcd](https://docs.k3s.io/datastore/ha-embedded)
- Blog post: `docs/source/md/blog-kube-vip-k3s-control-plane-ha.md`
