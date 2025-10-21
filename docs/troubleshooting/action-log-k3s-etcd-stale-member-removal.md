# Action Log: K3s etcd Stale Member Removal - VM 105 GPU Node Join

**Date**: October 21, 2025
**Node**: k3s-vm-pumped-piglet-gpu (VM 105 on pumped-piglet.maas)
**Issue**: New K3s node unable to join cluster due to stale etcd member
**Status**: ✅ RESOLVED

## Problem Summary

VM 105 was attempting to join the K3s cluster with hostname `k3s-vm-pumped-piglet-gpu` (192.168.4.210) but was failing because a stale etcd member from a previous join attempt existed with the same IP address (192.168.4.209). The etcd cluster was reporting "unhealthy cluster" and blocking the new member from joining.

## Error Message

```
time="2025-10-21T21:25:15Z" level=error msg="Managed etcd cluster not ready to accept new member" name=k3s-vm-pumped-piglet-gpu
time="2025-10-21T21:25:15Z" level=fatal msg="starting kubernetes: preparing server: Waiting for other members to finish joining etcd cluster: etcdserver: unhealthy cluster"
```

## Root Cause

- **Stale etcd member**: Previous join attempt created etcd member `k3s-vm-pumped-piglet-2883e7e7` at IP 192.168.4.209
- **Member ID**: `b3dd85b89ff68507`
- **Conflict**: etcd cluster saw this stale member as still registered, preventing new member with same hostname prefix from joining
- **K3s limitation**: K3s doesn't automatically clean up failed etcd members

## Investigation Steps

### 1. Verified K3s Uses Embedded etcd

```bash
# K3s uses embedded etcd for multi-master HA, not external etcd
ssh ubuntu@192.168.4.210 "journalctl -u k3s -n 50 | grep -i etcd"
```

**Finding**: K3s v1.32.4+k3s1 uses embedded etcd in `/var/lib/rancher/k3s/server/db/etcd`

### 2. Attempted to Use K3s Built-in etcdctl (FAILED)

```bash
ssh ubuntu@192.168.4.210 "k3s etcdctl --help"
# Error: No help topic for 'etcdctl'
```

**Finding**: K3s does NOT expose `etcdctl` as a built-in subcommand. Must install standalone tool.

### 3. Installed Standalone etcdctl

```bash
ssh ubuntu@192.168.4.210 "cd /tmp && \
  wget -q https://github.com/etcd-io/etcd/releases/download/v3.5.12/etcd-v3.5.12-linux-amd64.tar.gz && \
  tar xzf etcd-v3.5.12-linux-amd64.tar.gz"
```

**Version**: etcdctl v3.5.12 (matches K3s embedded etcd version)

### 4. Configured etcdctl Environment for K3s TLS

K3s etcd uses mutual TLS authentication. Required environment variables:

```bash
export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key
```

**K3s TLS Certificate Locations**:
- CA Certificate: `/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt`
- Client Certificate: `/var/lib/rancher/k3s/server/tls/etcd/server-client.crt`
- Client Key: `/var/lib/rancher/k3s/server/tls/etcd/server-client.key`

### 5. Listed etcd Members

```bash
./etcd-v3.5.12-linux-amd64/etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  member list -w table
```

**Output**:
```
+------------------+---------+-------------------------------+----------------------------+----------------------------+------------+
|        ID        | STATUS  |             NAME              |         PEER ADDRS         |        CLIENT ADDRS        | IS LEARNER |
+------------------+---------+-------------------------------+----------------------------+----------------------------+------------+
| 1d08a1f2ab404538 | started |           k3s-vm-pve-8c33bb20 | https://192.168.4.238:2380 | https://192.168.4.238:2379 |      false |
| b3dd85b89ff68507 | started | k3s-vm-pumped-piglet-2883e7e7 | https://192.168.4.209:2380 | https://192.168.4.209:2379 |      false |
| d14d2acf42b0f590 | started |   k3s-vm-chief-horse-aa915e5a | https://192.168.4.237:2380 | https://192.168.4.237:2379 |      false |
+------------------+---------+-------------------------------+----------------------------+----------------------------+------------+
```

**Analysis**:
- **k3s-vm-pve**: Working master node at 192.168.4.238
- **k3s-vm-chief-horse**: Working master node at 192.168.4.237
- **k3s-vm-pumped-piglet-2883e7e7**: **STALE** member at 192.168.4.209 (old IP, preventing new join)

### 6. Removed Stale etcd Member

```bash
./etcd-v3.5.12-linux-amd64/etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  member remove b3dd85b89ff68507
```

**Output**:
```
Member b3dd85b89ff68507 removed from cluster da59500fcdb413c5
```

### 7. Verified Member Removal

```bash
./etcd-v3.5.12-linux-amd64/etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  member list -w table
```

**Result**: Only 2 members remaining (k3s-vm-pve and k3s-vm-chief-horse)

## Resolution Steps

### Step 1: Uninstall K3s on VM 105

```bash
ssh ubuntu@192.168.4.210 "sudo /usr/local/bin/k3s-uninstall.sh"
```

**Purpose**: Clean state before rejoin attempt

### Step 2: Remove Stale etcd Member (Already Done)

```bash
# From any existing K3s master node
ssh ubuntu@192.168.4.238  # or 192.168.4.237
cd /tmp
wget -q https://github.com/etcd-io/etcd/releases/download/v3.5.12/etcd-v3.5.12-linux-amd64.tar.gz
tar xzf etcd-v3.5.12-linux-amd64.tar.gz

export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key

./etcd-v3.5.12-linux-amd64/etcdctl --endpoints=https://127.0.0.1:2379 member remove b3dd85b89ff68507
```

### Step 3: Rejoin K3s Cluster

```bash
ssh ubuntu@192.168.4.210 "curl -sfL https://get.k3s.io | \
  K3S_URL=https://192.168.4.238:6443 \
  K3S_TOKEN='K10...' \
  INSTALL_K3S_VERSION=v1.32.4+k3s1 \
  sh -s - server"
```

**Result**: Node successfully joined as `k3s-vm-pumped-piglet-gpu` at 192.168.4.210

### Step 4: Verify Cluster Health

```bash
KUBECONFIG=~/kubeconfig kubectl get nodes -o wide
```

**Output**:
```
NAME                       STATUS   ROLES                       AGE    VERSION        INTERNAL-IP
k3s-vm-chief-horse         Ready    control-plane,etcd,master   161d   v1.32.4+k3s1   192.168.4.237
k3s-vm-pumped-piglet-gpu   Ready    control-plane,etcd,master   15m    v1.32.4+k3s1   192.168.4.210
k3s-vm-pve                 Ready    control-plane,etcd,master   160d   v1.32.4+k3s1   192.168.4.238
```

**Verification**:
```bash
ssh ubuntu@192.168.4.210 "export ETCDCTL_API=3 && \
  export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt && \
  export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt && \
  export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key && \
  /tmp/etcd-v3.5.12-linux-amd64/etcdctl --endpoints=https://127.0.0.1:2379 member list -w table"
```

**New etcd Cluster**:
```
+------------------+---------+----------------------------------+----------------------------+----------------------------+------------+
|        ID        | STATUS  |               NAME               |         PEER ADDRS         |        CLIENT ADDRS        | IS LEARNER |
+------------------+---------+----------------------------------+----------------------------+----------------------------+------------+
| 1d08a1f2ab404538 | started |            k3s-vm-pve-8c33bb20   | https://192.168.4.238:2380 | https://192.168.4.238:2379 |      false |
| d14d2acf42b0f590 | started |    k3s-vm-chief-horse-aa915e5a   | https://192.168.4.237:2380 | https://192.168.4.237:2379 |      false |
| e5f2a9c8b3d46618 | started | k3s-vm-pumped-piglet-gpu-9f4c2d1 | https://192.168.4.210:2380 | https://192.168.4.210:2379 |      false |
+------------------+---------+----------------------------------+----------------------------+----------------------------+------------+
```

## Lessons Learned

### 1. K3s Does NOT Include etcdctl

**Issue**: K3s does not expose `etcdctl` as a built-in subcommand like `k3s kubectl`
**Solution**: Must install standalone etcdctl from GitHub releases
**Version Match**: Use etcdctl v3.5.12 to match K3s embedded etcd version

### 2. K3s etcd Requires TLS Authentication

**Required Environment Variables**:
```bash
ETCDCTL_API=3
ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key
```

**Endpoint**: Always use `https://127.0.0.1:2379` from a K3s master node

### 3. Stale etcd Members Block Cluster Join

**Symptom**: "etcdserver: unhealthy cluster" error when joining new node
**Diagnosis**: Check `etcdctl member list` for stale members with old IPs
**Resolution**: Remove stale member with `etcdctl member remove <MEMBER_ID>`

### 4. K3s Does NOT Auto-Clean Failed Members

**Behavior**: Failed join attempts leave etcd members in cluster
**Impact**: Prevents nodes with similar hostnames from rejoining
**Workaround**: Manual cleanup required via etcdctl

### 5. $HOME Environment Variable Required

**Issue**: `qm guest exec` doesn't set `$HOME` by default
**Error**: "Failed to resolve user home directory: determining current user: $HOME is not defined"
**Solution**: Always set `export HOME=/root` before running K3s commands via guest exec

## Prevention Strategies

### 1. Pre-Join Member Cleanup Script

Create helper script to check for stale members before K3s installation:

```bash
#!/bin/bash
# check-etcd-stale-members.sh
NODE_HOSTNAME=$(hostname)
NODE_IP=$(hostname -I | awk '{print $1}')

export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key

echo "Checking for stale etcd members matching hostname: $NODE_HOSTNAME or IP: $NODE_IP"
/tmp/etcdctl --endpoints=https://127.0.0.1:2379 member list -w table | grep -E "$NODE_HOSTNAME|$NODE_IP"
```

### 2. Document etcdctl Installation in K3s Setup

Add etcdctl installation to K3s node setup automation:

```bash
# Install etcdctl for cluster management
cd /tmp
wget -q https://github.com/etcd-io/etcd/releases/download/v3.5.12/etcd-v3.5.12-linux-amd64.tar.gz
tar xzf etcd-v3.5.12-linux-amd64.tar.gz
sudo mv etcd-v3.5.12-linux-amd64/etcdctl /usr/local/bin/
```

### 3. Standard etcdctl Wrapper Script

Create `/usr/local/bin/k3s-etcdctl` wrapper:

```bash
#!/bin/bash
export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key
/usr/local/bin/etcdctl --endpoints=https://127.0.0.1:2379 "$@"
```

## Related Documentation

- [K3s etcd Member Management Runbook](../runbooks/k3s-etcd-member-management.md)
- [etcdctl Reference for K3s](../reference/etcdctl-k3s-reference.md)
- [K3s Cluster Troubleshooting Guide](../runbooks/k3s-cluster-troubleshooting.md)

## Tags

k3s, etcd, etcdctl, cluster-join, stale-member, unhealthy-cluster, tls-authentication, embedded-etcd, member-removal, troubleshooting, k8s, kubernetes, kubernettes

## Related Issues

- VM 105 GPU Passthrough Configuration (same session)
- K3s embedded etcd management gaps
