# Still-Fawn Returns: K3s etcd Rejoin After Extended Outage

*VT-d, virtualization settings, and why etcd membership doesn't wait for you*

---

```
    February 2026: still-fawn is back

    Cluster State:                              K3s Nodes:
    ┌─────────────────────────┐                 ┌──────────────────────────┐
    │  pumped-piglet  Ready   │                 │  still-fawn     Ready    │
    │  fun-bedbug     Ready   │  ←── etcd ───→  │  (rejoined after 3 weeks)│
    │  pve            Ready   │                 │  AMD RX 580 + Coral TPU  │
    └─────────────────────────┘                 └──────────────────────────┘
```

## The Situation

still-fawn went down in late January 2026 due to a ZFS root disk failure. After hardware replacement and Proxmox reinstall, the node sat idle for nearly three weeks while other priorities took over.

When I finally returned to bring it back into the K3s cluster, nothing worked. The K3s service was stuck in `activating` state, and logs showed:

```
etcd: authentication handshake failed: remote error: tls: certificate required
```

## Why Extended Outages Break etcd

etcd is a distributed consensus system. It expects all members to actively participate. When a node disappears:

1. **Short outage (minutes-hours)**: etcd waits, node can rejoin normally
2. **Extended outage (days-weeks)**: The cluster moves on. Certificates rotate, membership state diverges, and the stale node becomes an untrusted stranger

After 3 weeks, still-fawn's K3s state was completely stale. The cluster had issued new certificates, processed thousands of API requests, and the old etcd member entry was a ghost.

## The Fix: Remove and Rejoin Fresh

The solution is not to "fix" the stale node - it's to remove the corpse and add a fresh member.

### Step 1: Remove Stale etcd Member

From a healthy node (pumped-piglet):

```bash
ssh root@pumped-piglet.maas 'qm guest exec 105 -- bash -c "
export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key
etcdctl --endpoints=https://127.0.0.1:2379 member list -w table
"'
```

Find the stale member ID, then remove it:

```bash
etcdctl --endpoints=https://127.0.0.1:2379 member remove <MEMBER_ID>
```

### Step 2: Clean Uninstall on Stale Node

**Critical**: Use the official uninstall script. Don't just `rm -rf`.

```bash
ssh root@still-fawn.maas 'qm guest exec 108 -- bash -c "
sudo systemctl stop k3s || true
sudo /usr/local/bin/k3s-uninstall.sh
"'
```

The uninstall script handles:
- Systemd unit removal
- iptables cleanup
- CNI state cleanup
- Kubelet certificates

### Step 3: Fresh Install with Join Token

Get the join token from a healthy node, then reinstall:

```bash
curl -sfL https://get.k3s.io | \
  K3S_URL="https://192.168.4.210:6443" \
  K3S_TOKEN="<TOKEN>" \
  INSTALL_K3S_VERSION="v1.35.0+k3s1" \
  sh -s - server --disable servicelb
```

Within 90 seconds, the node appears as Ready:

```
NAME                       STATUS   ROLES                       AGE
k3s-vm-still-fawn          Ready    control-plane,etcd          27m
k3s-vm-pumped-piglet-gpu   Ready    control-plane,etcd,master   21d
k3s-vm-fun-bedbug          Ready    control-plane,etcd          18d
k3s-vm-pve                 Ready    control-plane,etcd          20d
```

## The VT-d Reminder (Again)

Before the K3s rejoin could work, I had to fix GPU passthrough. The VM needed the AMD RX 580 for VAAPI decode.

After reinstalling Proxmox, I forgot to re-enable VT-d in BIOS. The symptom:

```bash
ls /sys/kernel/iommu_groups/ | wc -l
# 0
```

Zero IOMMU groups = VT-d disabled = no GPU passthrough possible.

**Where to find VT-d on ASUS Intel boards:**
```
BIOS → Advanced → System Agent Configuration → VT-d → Enabled
```

This is documented in `proxmox/guides/nvidia-RTX-3070-k3s-PCI-passthrough.md` and I've now made this mistake twice. The CLAUDE.md has been updated with a **MANDATORY FIRST** check:

```bash
# Before ANY GPU passthrough troubleshooting:
ls /sys/kernel/iommu_groups/ | wc -l
# If 0 → VT-d disabled in BIOS. Stop. Fix BIOS first.
```

## Key Takeaways

### 1. etcd Membership is Time-Sensitive

If a node is down for more than a few hours, plan for a clean rejoin rather than hoping it "just works."

### 2. Use Official Uninstall Scripts

K3s (and most Kubernetes distributions) have uninstall scripts for a reason. They clean up iptables rules, CNI state, and other cruft that manual deletion misses.

### 3. Version Matching Matters

When rejoining, use the exact same K3s version as the cluster. Version mismatches cause subtle API incompatibilities.

### 4. Check VT-d First, Always

Before any GPU passthrough troubleshooting:
1. Check IOMMU groups exist
2. If zero → fix BIOS VT-d
3. Only then debug kernel parameters

## Future Plans for still-fawn

Now that still-fawn is back in the cluster, it's entering a monitoring phase. After 1-2 weeks of stability verification, the plan is:

1. **Phase 2**: Move PBS (3TB HDD physically moved from pumped-piglet)
2. **Phase 3**: Migrate Frigate with PCIe Coral TPU + AMD RX 580 VAAPI
3. **Phase 4**: Retire fun-bedbug's Frigate LXC

Goal: Reduce pumped-piglet concentration risk by distributing PBS and Frigate to still-fawn.

---

## Related Documentation

- `docs/runbooks/k3s-etcd-node-rejoin-after-outage.md` - Step-by-step rejoin procedure
- `docs/runbooks/still-fawn-recovery-2026-01.md` - Full hardware recovery runbook
- `docs/runbooks/pbs-migration-to-still-fawn.md` - Phase 2 plan
- `docs/runbooks/frigate-migration-to-still-fawn-k3s.md` - Phase 3 plan
- `proxmox/guides/nvidia-RTX-3070-k3s-PCI-passthrough.md` - VT-d and GPU passthrough

---

**Tags**: k3s, kubernetes, etcd, rejoin, still-fawn, vt-d, virtualization, bios, iommu, gpu-passthrough, recovery
