# RCA: K3s svclb Pods Pending After Traefik PostgreSQL Port Addition

**Date**: 2025-12-27
**Duration**: 6 days (unnoticed until investigation)
**Impact**: No user impact - MetalLB was handling LoadBalancer services correctly
**Severity**: Low (cosmetic - pending pods in kube-system)

## Summary

After adding PostgreSQL port 5432 to Traefik on 2025-12-20, K3s servicelb (Klipper) created new svclb DaemonSet pods that couldn't schedule due to port conflicts with existing svclb pods.

## Timeline

| Time | Event |
|------|-------|
| 2025-12-20 | Commit `8db3d3b` added PostgreSQL TCP ingress to Traefik (port 5432) |
| 2025-12-20 | K3s servicelb controller recreated svclb-traefik DaemonSet with new port |
| 2025-12-20 | New svclb pods failed to schedule - port conflict |
| 2025-12-27 | Issue discovered during routine check |
| 2025-12-27 | Disabled K3s servicelb on all nodes, resolved |

## Root Cause

K3s ships with two load balancer solutions:
1. **Klipper (servicelb)** - Built-in, creates DaemonSet pods that bind host ports
2. **MetalLB** - External, uses ARP/BGP to advertise IPs

Both were enabled. MetalLB was correctly assigning external IPs, but servicelb was also trying to create svclb pods. When Traefik's service ports changed (added 5432), servicelb created a new DaemonSet generation that conflicted with the old pods still binding ports 80/443.

The scheduling error: "1 node(s) didn't have free ports for the requested pod ports, 2 node(s) didn't satisfy plugin(s) [NodeAffinity]"

## Resolution

Disabled K3s servicelb on all 3 nodes since MetalLB handles all LoadBalancer services:

```bash
# On each K3s VM via qm guest exec
echo "disable:
- servicelb" > /etc/rancher/k3s/config.yaml

systemctl restart k3s
```

Nodes updated:
- k3s-vm-still-fawn (VMID 108 on still-fawn/192.168.4.17)
- k3s-vm-pumped-piglet-gpu (VMID 105 on pumped-piglet/192.168.4.175)
- k3s-vm-pve (VMID 107 on pve/192.168.4.122)

## Verification

After restart, all svclb pods and DaemonSets were automatically removed. LoadBalancer services retained their MetalLB-assigned IPs:

| Service | External IP |
|---------|-------------|
| traefik | 192.168.4.80 |
| frigate | 192.168.4.81 |
| frigate-coral | 192.168.4.83 |
| ollama-lb | 192.168.4.85 |
| samba-lb | 192.168.4.120 |

## Lessons Learned

1. **Don't run two LB solutions** - K3s servicelb and MetalLB are redundant; disable one
2. **Check kube-system pods periodically** - Pending pods went unnoticed for 6 days
3. **MetalLB is sufficient** - Provides all needed LoadBalancer functionality

## Prevention

- K3s servicelb now permanently disabled via config
- MetalLB is sole LoadBalancer provider
- Added to cluster setup runbook

## Tags

k3s, servicelb, metallb, loadbalancer, traefik, pending-pods, port-conflict, klipper
