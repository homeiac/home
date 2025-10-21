# etcdctl Reference for K3s Embedded etcd

**Tool**: etcdctl v3.5.12 (for K3s v1.32.x)
**Purpose**: Manage K3s embedded etcd cluster members and data
**Last Updated**: October 21, 2025

## Overview

K3s uses an embedded etcd cluster for high-availability multi-master deployments. Unlike standalone K8s clusters, K3s does NOT expose `etcdctl` as a built-in subcommand, requiring manual installation of the standalone tool.

## Installation

### Download and Install etcdctl

```bash
# On K3s master node
cd /tmp
wget -q https://github.com/etcd-io/etcd/releases/download/v3.5.12/etcd-v3.5.12-linux-amd64.tar.gz
tar xzf etcd-v3.5.12-linux-amd64.tar.gz

# Install to system path
sudo mv etcd-v3.5.12-linux-amd64/etcdctl /usr/local/bin/
sudo chmod +x /usr/local/bin/etcdctl

# Verify installation
etcdctl version
# Expected: etcdctl version: 3.5.12
```

**Version Compatibility**:
- K3s v1.32.x → etcdctl v3.5.12
- K3s v1.31.x → etcdctl v3.5.11
- Always match etcdctl version to K3s embedded etcd version

## Configuration

### Required Environment Variables

K3s etcd uses mutual TLS authentication. These environment variables MUST be set for all etcdctl operations:

```bash
export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key
```

**Certificate Locations** (K3s default paths):
- CA Certificate: `/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt`
- Client Certificate: `/var/lib/rancher/k3s/server/tls/etcd/server-client.crt`
- Client Key: `/var/lib/rancher/k3s/server/tls/etcd/server-client.key`

### Endpoint Configuration

Always use the local etcd endpoint when running on a K3s master node:

```bash
--endpoints=https://127.0.0.1:2379
```

**Why localhost**: K3s etcd listens on `127.0.0.1:2379` by default, not on external interfaces.

## Common Operations

### List Cluster Members

```bash
etcdctl --endpoints=https://127.0.0.1:2379 member list -w table
```

**Example Output**:
```
+------------------+---------+-------------------------------+----------------------------+----------------------------+------------+
|        ID        | STATUS  |             NAME              |         PEER ADDRS         |        CLIENT ADDRS        | IS LEARNER |
+------------------+---------+-------------------------------+----------------------------+----------------------------+------------+
| 1d08a1f2ab404538 | started |           k3s-vm-pve-8c33bb20 | https://192.168.4.238:2380 | https://192.168.4.238:2379 |      false |
| d14d2acf42b0f590 | started |   k3s-vm-chief-horse-aa915e5a | https://192.168.4.237:2380 | https://192.168.4.237:2379 |      false |
| e5f2a9c8b3d46618 | started | k3s-vm-pumped-piglet-gpu-9f4c | https://192.168.4.210:2380 | https://192.168.4.210:2379 |      false |
+------------------+---------+-------------------------------+----------------------------+----------------------------+------------+
```

**Output Fields**:
- **ID**: Unique member identifier (hexadecimal)
- **STATUS**: Member state (`started`, `unstarted`)
- **NAME**: K3s-generated member name (format: `<hostname>-<hash>`)
- **PEER ADDRS**: etcd peer communication address (port 2380)
- **CLIENT ADDRS**: etcd client API address (port 2379)
- **IS LEARNER**: Whether member is in learner mode during join

### Remove Stale Member

**Use Case**: Failed K3s join attempts leave stale members that block future joins

```bash
# 1. List members to find stale member ID
etcdctl --endpoints=https://127.0.0.1:2379 member list -w table

# 2. Remove member by ID
etcdctl --endpoints=https://127.0.0.1:2379 member remove <MEMBER_ID>

# Example:
etcdctl --endpoints=https://127.0.0.1:2379 member remove b3dd85b89ff68507
```

**Output**:
```
Member b3dd85b89ff68507 removed from cluster da59500fcdb413c5
```

**When to Remove Members**:
- Node failed to join K3s cluster (error: "unhealthy cluster")
- Old member with same hostname/IP exists
- Member shows incorrect IP after node reconfiguration
- Member stuck in `unstarted` state

**CRITICAL**: Do NOT remove active, healthy members. Always verify cluster has quorum before removals.

### Check Cluster Health

```bash
etcdctl --endpoints=https://127.0.0.1:2379 endpoint health -w table
```

**Example Output (Healthy)**:
```
+--------------------+--------+-------------+-------+
|      ENDPOINT      | HEALTH |    TOOK     | ERROR |
+--------------------+--------+-------------+-------+
| 127.0.0.1:2379     |   true | 10.452871ms |       |
+--------------------+--------+-------------+-------+
```

**Example Output (Unhealthy)**:
```
+--------------------+--------+-------------+-----------------------------------+
|      ENDPOINT      | HEALTH |    TOOK     |              ERROR                |
+--------------------+--------+-------------+-----------------------------------+
| 127.0.0.1:2379     |  false | 5.002s      | context deadline exceeded         |
+--------------------+--------+-------------+-----------------------------------+
```

### Check Cluster Status

```bash
etcdctl --endpoints=https://127.0.0.1:2379 endpoint status -w table
```

**Example Output**:
```
+--------------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+
|      ENDPOINT      |        ID        | VERSION | DB SIZE | IS LEADER | IS LEARNER | RAFT TERM | RAFT INDEX | RAFT APPLIED INDEX | ERRORS |
+--------------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+
| 127.0.0.1:2379     | 1d08a1f2ab404538 |  3.5.12 |   20 MB |      true |      false |         8 |      45632 |              45632 |        |
+--------------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+
```

**Key Fields**:
- **IS LEADER**: One member must be leader (true)
- **DB SIZE**: etcd database size (monitor for excessive growth)
- **RAFT INDEX**: Raft consensus log index (should increment)
- **ERRORS**: Any errors preventing normal operation

### Snapshot Database (Backup)

```bash
etcdctl --endpoints=https://127.0.0.1:2379 snapshot save /backup/etcd-snapshot.db

# Example output:
# {"level":"info","ts":1729560245.123,"caller":"snapshot/v3_snapshot.go:65","msg":"created temporary db file","path":"/backup/etcd-snapshot.db.part"}
# {"level":"info","ts":1729560245.789,"caller":"snapshot/v3_snapshot.go:73","msg":"fetching snapshot","endpoint":"127.0.0.1:2379"}
# Snapshot saved at /backup/etcd-snapshot.db
```

**Best Practices**:
- Take snapshots before major cluster changes
- Store snapshots on separate storage from etcd data directory
- Automate daily snapshots with cron
- Test restoration periodically

### Restore from Snapshot

**WARNING**: Restoration requires cluster downtime and coordination across all nodes.

```bash
# Stop K3s on ALL nodes
sudo systemctl stop k3s

# On first node, restore snapshot
sudo etcdctl snapshot restore /backup/etcd-snapshot.db \
  --name <node-name> \
  --initial-cluster <node1-name>=https://<node1-ip>:2380,<node2-name>=https://<node2-ip>:2380 \
  --initial-advertise-peer-urls https://<this-node-ip>:2380 \
  --data-dir /var/lib/rancher/k3s/server/db/etcd

# Repeat on all nodes with appropriate parameters
# Start K3s: sudo systemctl start k3s
```

**Refer to Official Docs**: K3s backup/restore has specific requirements beyond standard etcd.

## Wrapper Script for Convenience

Create `/usr/local/bin/k3s-etcdctl` to avoid setting environment variables every time:

```bash
#!/bin/bash
# k3s-etcdctl - Wrapper for etcdctl with K3s TLS configuration

export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key

exec /usr/local/bin/etcdctl --endpoints=https://127.0.0.1:2379 "$@"
```

```bash
# Make executable
sudo chmod +x /usr/local/bin/k3s-etcdctl

# Usage examples
k3s-etcdctl member list -w table
k3s-etcdctl endpoint health
k3s-etcdctl member remove <ID>
```

## Troubleshooting

### Error: "client: etcd cluster is unavailable or misconfigured"

**Causes**:
- K3s service not running: `sudo systemctl status k3s`
- Wrong TLS certificates: verify `ETCDCTL_CACERT`, `ETCDCTL_CERT`, `ETCDCTL_KEY`
- Wrong endpoint: use `https://127.0.0.1:2379`, NOT external IP

**Resolution**:
```bash
# Verify K3s running
sudo systemctl status k3s

# Check etcd process
ps aux | grep etcd

# Verify certificate files exist
ls -l /var/lib/rancher/k3s/server/tls/etcd/

# Test with verbose output
etcdctl --endpoints=https://127.0.0.1:2379 endpoint health --write-out=json
```

### Error: "context deadline exceeded"

**Causes**:
- etcd not responding (overloaded, crashed, or restarting)
- Network connectivity issues
- TLS handshake timeout

**Resolution**:
```bash
# Check K3s logs for etcd errors
sudo journalctl -u k3s -n 100 | grep -i etcd

# Check etcd data directory space
df -h /var/lib/rancher/k3s/server/db/etcd

# Restart K3s if safe
sudo systemctl restart k3s
```

### Error: "etcdserver: unhealthy cluster"

**Cause**: Cluster has lost quorum or has conflicting members

**Resolution**: See [K3s etcd Stale Member Removal Action Log](../troubleshooting/action-log-k3s-etcd-stale-member-removal.md)

## Quorum Requirements

etcd requires majority (quorum) of members to be online:

| Cluster Size | Quorum Required | Max Failures Tolerated |
|--------------|-----------------|------------------------|
| 1 member     | 1               | 0                      |
| 3 members    | 2               | 1                      |
| 5 members    | 3               | 2                      |
| 7 members    | 4               | 3                      |

**Best Practice**: Use odd numbers of members (3, 5, 7) for optimal fault tolerance.

## K3s-Specific Notes

### Member Names

K3s generates member names automatically:
- Format: `<node-hostname>-<8-character-hash>`
- Example: `k3s-vm-pve-8c33bb20`
- Hash is deterministic based on node configuration

### Data Directory

K3s etcd data location:
- Path: `/var/lib/rancher/k3s/server/db/etcd`
- Snapshots: `/var/lib/rancher/k3s/server/db/snapshots/` (automatic K3s snapshots)

### Auto-Snapshots

K3s automatically creates etcd snapshots:
- Frequency: Every 12 hours (configurable with `--etcd-snapshot-schedule-cron`)
- Retention: Last 5 snapshots (configurable with `--etcd-snapshot-retention`)
- Location: `/var/lib/rancher/k3s/server/db/snapshots/`

## Security Considerations

- **TLS Required**: All etcd communication uses mutual TLS
- **Certificate Permissions**: Protect certificate files (0600 recommended)
- **API Access**: Only K3s master nodes have etcd client certificates
- **Backup Encryption**: Encrypt etcd snapshots when storing externally

## Related Documentation

- [K3s etcd Stale Member Removal Action Log](../troubleshooting/action-log-k3s-etcd-stale-member-removal.md)
- [K3s Cluster Troubleshooting Guide](../runbooks/k3s-cluster-troubleshooting.md)
- [Official etcd Documentation](https://etcd.io/docs/v3.5/op-guide/)
- [K3s High Availability](https://docs.k3s.io/datastore/ha-embedded)

## Tags

etcd, etcdctl, k3s, kubernetes, k8s, kubernettes, cluster-management, member-management, tls, backup, snapshot, quorum, high-availability, ha, embedded-etcd

## Version History

- **v1.0** (Oct 2025): Initial reference based on K3s v1.32.4 troubleshooting
- etcdctl version: 3.5.12
- K3s version: v1.32.4+k3s1
