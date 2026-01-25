# Adding a Fourth Control Plane Node: Lessons in IaC Discipline

*How a "simple" VM deployment exposed network assumptions and the value of GitOps*

---

It should have been routine.

The plan was simple: add k3s-vm-pve as a fourth control plane node to the K3s cluster. A standby node, really - something to spin up when needed, powered off the rest of the time. The infrastructure was already proven. We had templates. We had Crossplane. We had cloud-init snippets that worked flawlessly on three other nodes.

What could go wrong?

## The Confident Start

I had done this before. Just two weeks ago, fun-bedbug joined the cluster via the exact same process. The recipe was well-documented:

1. Create cloud-init snippet with K3s join token
2. Deploy snippet to Proxmox host
3. Create Crossplane EnvironmentVM manifest
4. Push to git, let Flux reconcile
5. Watch node join cluster

The fun-bedbug deployment took 15 minutes. This would be faster - I had all the templates.

I created the snippet, copying from the working fun-bedbug template:

```yaml
hostname: k3s-vm-pve
K3S_URL: 'https://192.168.4.210:6443'
K3S_TOKEN: 'K10b0cee...'
INSTALL_K3S_VERSION: 'v1.35.0+k3s1'
```

Created the Crossplane manifest. Standard configuration - 2 cores, 4GB RAM, 50GB disk on local-zfs. Network on vmbr0, just like the others.

Pushed to git. Watched Flux reconcile. Watched Crossplane create the VM.

VM started. Cloud-init ran. K3s installation began.

And then... nothing.

## "Context Deadline Exceeded"

The K3s service failed. The journal told the story:

```
failed to get CA certs: Get "https://192.168.4.210:6443/cacerts":
context deadline exceeded (Client.Timeout exceeded while awaiting headers)
```

The VM couldn't reach the K3s API server at 192.168.4.210. A network problem - but how? The snippet was identical to fun-bedbug's. The VM was configured the same way.

I checked the VM's IP address.

```
192.168.1.160
```

Wait. **192.168.1.x**? The K3s cluster lives on 192.168.4.x.

## The Assumption That Bit Me

I had assumed all Proxmox hosts were configured identically. They weren't.

On still-fawn, pumped-piglet, and fun-bedbug, `vmbr0` bridges to the 192.168.4.x network - the homelab network where K3s lives.

On pve, `vmbr0` bridges to 192.168.1.x - the WAN network. The homelab network is on a *different* bridge: `vmbr25gbe`.

```
# pve /etc/network/interfaces
auto vmbr0
iface vmbr0 inet static
    address 192.168.1.122/24   # WAN
    bridge-ports enp1s0

auto vmbr25gbe
iface vmbr25gbe inet static
    address 192.168.4.122/24   # Homelab - this is where K3s lives!
    bridge-ports enx803f5df89175
```

The VM was on the wrong network entirely. It was like trying to join a LAN party from a coffee shop across town.

## The Fix

One line change in the Crossplane manifest:

```yaml
networkDevice:
  - bridge: vmbr25gbe  # Not vmbr0!
    model: virtio
```

Commit. Push. Reconcile.

```bash
ssh root@pve.maas "qm stop 107 && sleep 5 && qm start 107"
```

New IP: 192.168.4.193. On the right network.

Within 30 seconds:

```
k3s-vm-pve    Ready    control-plane,etcd    8s    v1.35.0+k3s1
```

## What Was Different

Why did this bite me when fun-bedbug worked perfectly?

| Aspect | fun-bedbug | pve |
|--------|-----------|-----|
| Homelab bridge | vmbr0 | vmbr25gbe |
| WAN bridge | N/A | vmbr0 |
| Storage | local (dir) | local-zfs |
| Network setup | Single network | Dual network |

The pve host is the original Proxmox server - it predates the "homelab network" design. It has both networks because it runs OPNsense (the router) and MAAS (on the WAN). The other hosts were set up later, with vmbr0 directly on the homelab network.

I assumed homogeneity. The infrastructure said otherwise.

## What I Could Have Done Better

### 1. Check Network Topology Before Templating

Before copying any manifest, I should have run:

```bash
ssh root@pve.maas "grep -A5 'vmbr' /etc/network/interfaces"
```

Two minutes of verification would have saved twenty minutes of debugging.

### 2. Document Host-Specific Differences

The Crossplane manifests for fun-bedbug have comments explaining that host's quirks:

```yaml
# IMPORTANT: fun-bedbug only has 'local' directory storage active
# ZFS pools are DISABLED on this host - do not use local-zfs
```

The pve manifest now has similar documentation:

```yaml
# NOTE: pve has vmbr0 (192.168.1.x WAN) and vmbr25gbe (192.168.4.x homelab)
# This node will be powered off after initial setup (standby/spare)
```

### 3. Create a Host Capabilities Matrix

We should have a single source of truth for host differences:

| Host | Homelab Bridge | Storage | Notes |
|------|---------------|---------|-------|
| pve | vmbr25gbe | local-zfs | Dual network, runs OPNsense |
| still-fawn | vmbr0 | local-zfs | AMD GPU + Coral TPU |
| pumped-piglet | vmbr0 | local-zfs | RTX 3070 GPU |
| fun-bedbug | vmbr0 | local | ZFS disabled, thermal issues |

### 4. Test Network Connectivity in Cloud-Init

The cloud-init snippet could include an early check:

```yaml
runcmd:
  - |
    # Verify we can reach K3s API before attempting join
    if ! curl -sf --connect-timeout 5 https://192.168.4.210:6443/cacerts >/dev/null 2>&1; then
      echo "FATAL: Cannot reach K3s API - wrong network?" | tee /var/log/k3s-preflight-fail
      exit 1
    fi
```

Fail fast, fail loud.

## The Silver Lining

GitOps made the fix trivial. One line change, commit, push, reconcile. No SSH sessions modifying VM configs manually. No drift. No wondering "did I change that on all nodes?"

The Crossplane manifest is the truth. Git history shows exactly what changed and when:

```
fix(k3s): use vmbr25gbe bridge for k3s-vm-pve

pve has two bridges:
- vmbr0: 192.168.1.x (WAN)
- vmbr25gbe: 192.168.4.x (homelab, where K3s cluster is)
```

## The Result

Four control plane nodes. All at v1.35.0+k3s1. Proper etcd quorum.

```
NAME                       STATUS   ROLES                       VERSION
k3s-vm-pumped-piglet-gpu   Ready    control-plane,etcd,master   v1.35.0+k3s1
k3s-vm-still-fawn          Ready    control-plane,etcd,master   v1.35.0+k3s1
k3s-vm-fun-bedbug          Ready    control-plane,etcd,master   v1.35.0+k3s1
k3s-vm-pve                 Ready    control-plane,etcd          v1.35.0+k3s1
```

The fourth node is now powered off - a standby, ready to spin up when needed. Its Crossplane manifest has `onBoot: false` so it won't start automatically.

```bash
ssh root@pve.maas "qm status 107"
# status: stopped
```

A spare tire in the trunk. Not using resources, but ready.

## Lessons Learned

1. **Homogeneity is a myth.** Even in your own infrastructure, hosts have quirks. Document them.

2. **Templates are starting points, not solutions.** Copy-paste gets you 80% there. The last 20% is where the bugs hide.

3. **Network assumptions are the silent killer.** "It works on the other nodes" means nothing if the network topology differs.

4. **GitOps shines in recovery.** One-line fix, full audit trail, no manual state to reconcile.

5. **Fail-fast checks pay dividends.** A 5-second curl in cloud-init would have made the failure obvious immediately.

---

*k3s-vm-pve sleeps now, powered off, its brief moment of confusion forgotten. The cluster hums along with four nodes registered, three active. And somewhere in a Git commit, a one-line diff tells the whole story: `vmbr0` → `vmbr25gbe`. The infrastructure remembers what I almost forgot.*

---

**Tags:** homelab, k3s, kubernetes, crossplane, gitops, flux, proxmox, networking, infrastructure, iac, lessons-learned, kubernettes, proxmocks

**Related:** [The Case of the Phantom Load](/docs/source/md/blog-fun-bedbug-sysload-mystery.md), [K3s Cluster Configuration](/proxmox/homelab/config/k3s.yaml)
