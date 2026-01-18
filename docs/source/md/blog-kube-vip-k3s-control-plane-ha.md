# Adding Control Plane HA to K3s with kube-vip

**Date**: 2026-01-17
**Tags**: k3s, kubernetes, kube-vip, high-availability, homelab, proxmox

## The Problem

My K3s cluster runs on 4 VMs across Proxmox hosts. I had a 3-node etcd quorum for data HA, but my kubeconfig pointed directly to one node's IP (`192.168.4.210`). If that node went down, kubectl stopped working even though the cluster was still healthy.

```
~/kubeconfig:
  server: https://192.168.4.210:6443  # Single point of failure!
```

## The Solution: kube-vip

kube-vip provides a floating Virtual IP (VIP) for the Kubernetes API server. It runs as a DaemonSet on control plane nodes and uses leader election - only the leader responds to the VIP. When the leader fails, another node takes over within seconds.

```
Before:                          After:
┌─────────────────┐              ┌─────────────────┐
│ kubectl         │              │ kubectl         │
│ → 192.168.4.210 │              │ → 192.168.4.79  │ (VIP)
└────────┬────────┘              └────────┬────────┘
         │                                │
         ▼                       ┌────────┴────────┐
   ┌──────────┐                  ▼        ▼        ▼
   │ node-1   │               node-1   node-2   node-3
   │ (SPOF!)  │               (leader floats between nodes)
   └──────────┘
```

## Why Not Just Use a Load Balancer?

You could put HAProxy or nginx in front of the API servers, but that adds:
- Another component to manage
- Another potential failure point
- More infrastructure complexity

kube-vip runs inside the cluster itself, using native Kubernetes primitives (leases) for leader election. No external dependencies.

## Implementation

### Step 1: The Certificate Problem

This is the part that trips people up. When you connect to `https://192.168.4.79:6443`, the API server presents its TLS certificate. Your client checks if the IP you're connecting to is in the certificate's Subject Alternative Names (SANs).

K3s generates the API server cert at install time. The VIP didn't exist then, so it's not in the cert. Result:

```
$ kubectl --server=https://192.168.4.79:6443 get nodes
Unable to connect to the server: x509: certificate is valid for
192.168.4.210, not 192.168.4.79
```

### Step 2: Adding VIP to TLS-SAN

I wrote a Python orchestrator that:
1. Writes the VIP to `/etc/rancher/k3s/config.yaml` on each node
2. Deletes the API server cert and restarts K3s (one node at a time!)
3. Verifies the new cert includes the VIP

The config file approach:

```yaml
# /etc/rancher/k3s/config.yaml
tls-san:
  - 192.168.4.79    # The VIP
  - 192.168.4.238   # Node IPs
  - 192.168.4.210
  - 192.168.4.203
  - k3s.homelab     # Optional DNS names
```

The orchestrator is idempotent - it checks if the VIP is already in the cert and skips nodes that don't need updating:

```bash
$ poetry run python -m homelab.k3s_manager prepare-kube-vip
=== Preparing cluster for kube-vip ===
Control plane VIP: 192.168.4.79

Step 1: Configuring TLS-SAN on all nodes...
  k3s-vm-pve: TLS-SAN already configured correctly
  k3s-vm-pumped-piglet-gpu: TLS-SAN already configured correctly
  k3s-vm-fun-bedbug: TLS-SAN configured
  k3s-vm-still-fawn: TLS-SAN configured

Step 2: Rotating certificates (only for nodes that need it)...
  Skipping k3s-vm-pve (VIP already in cert)
  Skipping k3s-vm-pumped-piglet-gpu (VIP already in cert)
  Processing k3s-vm-fun-bedbug...
  Processing k3s-vm-still-fawn...

=== Cluster ready for kube-vip! ===
```

### Step 3: Deploying kube-vip via Flux

The kube-vip DaemonSet is deployed via GitOps:

```yaml
# gitops/clusters/homelab/infrastructure/kube-vip/daemonset.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: kube-vip
  namespace: kube-system
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: node-role.kubernetes.io/control-plane
                    operator: Exists
      hostNetwork: true
      containers:
        - name: kube-vip
          image: ghcr.io/kube-vip/kube-vip:v0.8.7
          env:
            - name: vip_address
              value: "192.168.4.79"
            - name: vip_cidr
              value: "24"
            - name: vip_interface
              value: "eth0"
            - name: vip_arp
              value: "true"
            - name: cp_enable
              value: "true"
            - name: svc_enable
              value: "false"  # MetalLB handles services
            - name: vip_leaderelection
              value: "true"
```

Key settings:
- `cp_enable: true` - Control plane mode (VIP for API server)
- `svc_enable: false` - Don't handle LoadBalancer services (MetalLB does that)
- `vip_arp: true` - Layer 2 mode using ARP announcements
- `vip_cidr: 24` - Required! kube-vip needs to know the subnet

### Step 4: Update kubeconfig

```bash
sed -i '' 's/192.168.4.210/192.168.4.79/' ~/kubeconfig
```

## The Result

```bash
$ ping 192.168.4.79
PING 192.168.4.79: 64 bytes from 192.168.4.79: icmp_seq=0 ttl=64 time=0.9 ms

$ kubectl get lease kube-vip-lease -n kube-system -o jsonpath='{.spec.holderIdentity}'
k3s-vm-pumped-piglet-gpu

$ kubectl get nodes
NAME                       STATUS   ROLES                       AGE
k3s-vm-fun-bedbug          Ready    control-plane,etcd,master   2h
k3s-vm-pumped-piglet-gpu   Ready    control-plane,etcd,master   88d
k3s-vm-pve                 Ready    control-plane,etcd,master   248d
k3s-vm-still-fawn          Ready    control-plane,etcd,master   30m
```

Now if `k3s-vm-pumped-piglet-gpu` goes down, the VIP moves to another node and kubectl keeps working.

## Lessons Learned

### 1. The Script Must Be Idempotent

My first version re-rotated certs on ALL nodes whenever ANY node needed updating. This caused unnecessary K3s restarts. The fix was simple:

```python
# Only update if VIP is missing from current cert
vip_in_current = self.config.control_plane_vip in current_san
needs_update = not vip_in_current
```

### 2. SSH Doesn't Work to K3s VMs

My K3s VMs run on Proxmox with cloud-init networking that doesn't play well with direct SSH. The solution is `qm guest exec`:

```python
def _run_qm_exec(self, proxmox_host, vmid, command):
    ssh_cmd = [
        "ssh", f"root@{proxmox_host}.maas",
        f"qm guest exec {vmid} -- bash -c '{command}'"
    ]
```

### 3. Don't Forget vip_cidr

kube-vip 0.8.x requires the subnet mask. Without it:

```
level=fatal msg="no subnet provided for IP 192.168.4.79"
```

### 4. Keep MetalLB and kube-vip Separate

kube-vip can also handle LoadBalancer services, but I already have MetalLB for that. Running both in service mode causes conflicts. Set `svc_enable: false` on kube-vip.

## Files for Reproducibility

Everything needed to recreate this setup:

| File | Purpose |
|------|---------|
| `proxmox/homelab/config/k3s.yaml` | VIP, nodes, TLS-SAN config |
| `proxmox/homelab/src/homelab/k3s_manager.py` | TLS-SAN orchestrator |
| `gitops/clusters/homelab/infrastructure/kube-vip/` | Flux manifests |
| `docs/runbooks/kube-vip-control-plane-ha.md` | Operations runbook |

To recreate from scratch:

```bash
# 1. Configure TLS-SAN
cd proxmox/homelab
poetry run python -m homelab.k3s_manager prepare-kube-vip

# 2. Deploy kube-vip (Flux does this automatically)
flux reconcile kustomization flux-system --with-source

# 3. Update kubeconfig
sed -i '' 's/OLD_IP/192.168.4.79/' ~/kubeconfig
```

## Conclusion

kube-vip is a clean solution for K3s control plane HA. The main complexity is the TLS certificate dance, but once you automate that, it's a one-command setup. The VIP just works, and failover is automatic.

Total time to implement: ~2 hours (mostly figuring out the cert rotation).

---

**Related**:
- [kube-vip Documentation](https://kube-vip.io/)
- [K3s HA with Embedded etcd](https://docs.k3s.io/datastore/ha-embedded)
- Runbook: `docs/runbooks/kube-vip-control-plane-ha.md`
