# K3s Node Rejoin After Extended Outage

## Overview

This runbook covers rejoining a K3s server node to an existing cluster after an extended outage (e.g., hardware replacement, long maintenance). During extended outages, the node's etcd membership becomes stale and certificates may expire, preventing normal rejoin.

**Symptoms:**
- K3s service stuck in `activating` state
- etcd errors: "authentication handshake failed: remote error: tls: certificate required"
- Node shows in `kubectl get nodes` but NotReady or missing

**Root Cause:** etcd requires active participation; stale members must be removed and the node must rejoin fresh.

## Prerequisites

- [ ] Healthy K3s cluster with quorum (majority of server nodes running)
- [ ] SSH/qm guest exec access to both healthy node and stale node
- [ ] Know which node is stale (this runbook: still-fawn, VMID 108)

## Procedure

### Step 1: Verify Cluster Health from Healthy Node

```bash
# Check from pumped-piglet (VMID 105)
ssh root@pumped-piglet.maas 'qm guest exec 105 -- kubectl get nodes -o wide'
```

Expect: At least one node Ready, others may show NotReady/stale.

### Step 2: List etcd Members

```bash
ssh root@pumped-piglet.maas 'qm guest exec 105 -- bash -c "
export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key
export HOME=/root
etcdctl --endpoints=https://127.0.0.1:2379 member list -w table
"'
```

Note the **MEMBER ID** (hex string like `3a9b7c8d1e2f3a4b`) for the stale node.

### Step 3: Remove Stale etcd Member

```bash
# Replace <MEMBER_ID> with actual ID from step 2
ssh root@pumped-piglet.maas 'qm guest exec 105 -- bash -c "
export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key
export HOME=/root
etcdctl --endpoints=https://127.0.0.1:2379 member remove <MEMBER_ID>
"'
```

### Step 4: Uninstall K3s on Stale Node

**CRITICAL**: Use the official uninstall script, not manual `rm`. The script handles systemd units, iptables rules, and other cleanup.

```bash
ssh root@still-fawn.maas 'qm guest exec 108 -- bash -c "
export HOME=/root
sudo systemctl stop k3s || true
sudo /usr/local/bin/k3s-uninstall.sh
"'
```

Verify clean state:
```bash
ssh root@still-fawn.maas 'qm guest exec 108 -- bash -c "
ls /var/lib/rancher/k3s 2>&1 || echo CLEAN
ls /etc/rancher/k3s 2>&1 || echo CLEAN
"'
```

### Step 5: Get Join Token from Healthy Node

```bash
ssh root@pumped-piglet.maas 'qm guest exec 105 -- cat /var/lib/rancher/k3s/server/node-token'
```

Save this token for step 7.

### Step 6: Get K3s Version

```bash
ssh root@pumped-piglet.maas 'qm guest exec 105 -- k3s --version'
```

Use exact same version for rejoining node.

### Step 7: Reinstall K3s on Stale Node

```bash
# Replace <TOKEN> with actual token from step 5
# Replace <VERSION> with version from step 6 (e.g., v1.35.0+k3s1)
ssh root@still-fawn.maas 'qm guest exec 108 -- bash -c "
export HOME=/root
curl -sfL https://get.k3s.io | \
  K3S_URL=\"https://192.168.4.210:6443\" \
  K3S_TOKEN=\"<TOKEN>\" \
  INSTALL_K3S_VERSION=\"<VERSION>\" \
  sh -s - server --disable servicelb
"'
```

**Notes:**
- `K3S_URL` points to the existing cluster API (pumped-piglet IP)
- `--disable servicelb` matches existing cluster config
- Installation takes 60-90 seconds

### Step 8: Verify Success

Wait 60-90 seconds, then verify:

```bash
# Check nodes
ssh root@pumped-piglet.maas 'qm guest exec 105 -- kubectl get nodes -o wide'

# Check etcd membership
ssh root@pumped-piglet.maas 'qm guest exec 105 -- bash -c "
export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key
export HOME=/root
etcdctl --endpoints=https://127.0.0.1:2379 member list -w table
"'
```

**Success criteria:**
- Node shows `Ready` in kubectl output
- etcd shows correct number of healthy members
- No TLS/auth errors in K3s logs

## Troubleshooting

### "member not found" when removing
The member may have already been removed or ID is wrong. Re-run `member list` to verify.

### Node joins but stays NotReady
Check K3s logs on the rejoined node:
```bash
ssh root@still-fawn.maas 'qm guest exec 108 -- journalctl -u k3s -n 50'
```

Common causes:
- CNI not ready (wait longer)
- Network connectivity issues
- Kubelet registration problems

### etcd quorum lost
If quorum is lost (majority of nodes down), standard rejoin won't work. See `docs/troubleshooting/action-log-k3s-etcd-stale-member-removal.md` for disaster recovery.

### k3s-uninstall.sh missing
If the uninstall script doesn't exist, K3s was never fully installed or was manually removed. Verify directories are clean before proceeding.

## Related Documentation

- `docs/troubleshooting/action-log-k3s-etcd-stale-member-removal.md` - etcdctl detailed procedures
- `docs/runbooks/still-fawn-recovery-2026-01.md` - Full hardware recovery
- `docs/runbooks/k3s-node-addition-blueprint.md` - Adding new nodes

## Tags

k3s, kubernetes, kubernettes, etcd, rejoin, recovery, stale-member, still-fawn, outage, certificate, tls, membership
