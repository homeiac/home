# Runbook: Disable K3s Servicelb (Klipper)

## Purpose

Disable K3s built-in servicelb when using MetalLB for LoadBalancer services.

## When to Use

- Setting up new K3s cluster with MetalLB
- Seeing pending svclb-* pods in kube-system namespace
- Port conflicts between svclb DaemonSet pods

## Prerequisites

- MetalLB installed and configured
- SSH access to Proxmox hosts (K3s VMs don't allow direct SSH)
- Proxmox QEMU guest agent running in VMs

## Procedure

### 1. Identify K3s VMs and Their Hosts

| K3s VM | VMID | Proxmox Host | Host IP |
|--------|------|--------------|---------|
| k3s-vm-still-fawn | 108 | still-fawn | 192.168.4.17 |
| k3s-vm-pumped-piglet-gpu | 105 | pumped-piglet | 192.168.4.175 |
| k3s-vm-pve | 107 | pve | 192.168.4.122 |

### 2. Add Config to Each Node

For each K3s VM, run via the Proxmox host:

```bash
# Still-fawn
ssh root@192.168.4.17 'qm guest exec 108 -- bash -c "echo \"disable:
- servicelb\" > /etc/rancher/k3s/config.yaml"'

# Pumped-piglet
ssh root@192.168.4.175 'qm guest exec 105 -- bash -c "echo \"disable:
- servicelb\" > /etc/rancher/k3s/config.yaml"'

# PVE
ssh root@192.168.4.122 'qm guest exec 107 -- bash -c "echo \"disable:
- servicelb\" > /etc/rancher/k3s/config.yaml"'
```

### 3. Verify Config

```bash
ssh root@192.168.4.17 'qm guest exec 108 -- cat /etc/rancher/k3s/config.yaml' | jq -r '."out-data"'
# Should show:
# disable:
# - servicelb
```

### 4. Restart K3s on All Nodes

```bash
ssh root@192.168.4.17 'qm guest exec 108 -- systemctl restart k3s'
ssh root@192.168.4.175 'qm guest exec 105 -- systemctl restart k3s'
ssh root@192.168.4.122 'qm guest exec 107 -- systemctl restart k3s'
```

### 5. Verify Cluster Health

```bash
# Wait 15-30 seconds for cluster to stabilize
KUBECONFIG=~/kubeconfig kubectl get nodes
# All nodes should be Ready

# Verify no svclb pods remain
KUBECONFIG=~/kubeconfig kubectl get pods -n kube-system | grep svclb
# Should return empty

# Verify LoadBalancer services still have IPs
KUBECONFIG=~/kubeconfig kubectl get svc -A | grep LoadBalancer
# All should have EXTERNAL-IP from MetalLB
```

## Rollback

To re-enable servicelb:

```bash
ssh root@<HOST_IP> 'qm guest exec <VMID> -- rm /etc/rancher/k3s/config.yaml'
ssh root@<HOST_IP> 'qm guest exec <VMID> -- systemctl restart k3s'
```

## Related

- [RCA: svclb Pending Pods](../rca/2025-12-27-svclb-pending-pods.md)
- [MetalLB Configuration](../../gitops/clusters/homelab/infrastructure/metallb/)

## Tags

k3s, servicelb, metallb, loadbalancer, klipper, runbook
