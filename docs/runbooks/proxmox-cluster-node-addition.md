# Runbook: Proxmox Cluster Node Addition

**Purpose**: Add a new node to an existing Proxmox VE cluster
**Scope**: Generic procedure for any Proxmox node joining any cluster
**Related RCAs**: [still-fawn pve-cluster Failure](../rca/2025-10-04-still-fawn-pve-cluster-failure.md)

---

## Overview

This runbook provides the complete procedure for adding a new Proxmox VE node to an existing cluster. The process includes investigation, preparation, join operation, verification, and stability testing.

**Key Success Criteria**:
- New node appears in `pvecm status` on all cluster nodes
- Cluster quorum maintained throughout the process
- pve-cluster service survives reboot on new node
- Web GUI accessible with cluster view
- No systemd ordering cycles

---

## Prerequisites

### New Node Requirements
- Proxmox VE installed (same major version as cluster)
- Node is standalone (not already in a cluster)
- SSH access configured (root or sudo user)
- Network connectivity to all cluster nodes
- Hostname set correctly

### Cluster Requirements
- Existing cluster is healthy and quorate
- Main node accessible (the node you'll use as entry point)
- Root password for main node known
- Network ports accessible:
  - TCP 8006 (Proxmox GUI)
  - UDP 5404-5405 (Corosync)
  - TCP 22 (SSH)

### Tools Required
- SSH client
- Access to cluster main node
- Browser for GUI verification

---

## Phase 1: Pre-Join Investigation

### Step 1.1: Verify Current Cluster Status

**Purpose**: Understand existing cluster state before making changes

**Commands** (run on main node):
```bash
pvecm status           # Show cluster status and quorum
pvecm nodes            # List all nodes (active and offline)
cat /etc/pve/.members  # Show active cluster members
```

**What to Check**:
- Current number of nodes
- Quorum requirements (votes needed)
- Any offline nodes
- Cluster health status

**Decision Point**: If cluster has offline nodes causing quorum issues, consider removing them first with `pvecm delnode <node-name>`.

---

### Step 1.2: Verify New Node Status

**Purpose**: Confirm new node is standalone and ready

**Commands** (run on new node):
```bash
pvecm status                        # Should show "not available"
cat /etc/hostname                   # Verify hostname
cat /etc/hosts                      # Check host resolution
systemctl status pve-cluster        # Should be stopped/inactive
pveversion                          # Verify Proxmox version
```

**Expected Results**:
- Node is standalone (no cluster config)
- Hostname set correctly
- Proxmox version compatible with cluster
- No existing cluster membership

---

### Step 1.3: Network Connectivity Tests

**Purpose**: Ensure new node can reach all cluster nodes

**Commands** (run from new node):
```bash
ping -c 3 <main-node-ip>            # Test basic connectivity
nc -zv <main-node-ip> 8006          # Test Proxmox GUI port
nc -zuv <main-node-ip> 5405         # Test Corosync port
```

**Test for Each Active Cluster Node**:
- Ping succeeds
- Port 8006 accessible
- Port 5405 accessible (UDP)

**Troubleshooting**: If connectivity fails, check firewalls, routing, and network configuration before proceeding.

---

## Phase 2: Pre-Join Preparation

### Step 2.1: Set Hostname (if needed)

**Commands** (run on new node):
```bash
hostnamectl set-hostname <node-name>
hostname                            # Verify
cat /etc/hostname                   # Confirm persisted
```

**Best Practices**:
- Use consistent naming scheme
- Avoid special characters
- Match MAAS hostname if using MAAS

---

### Step 2.2: Update /etc/hosts

**Purpose**: Ensure proper name resolution for cluster communication

**Commands** (run on new node):
```bash
# Backup first
cp /etc/hosts /etc/hosts.backup

# Add cluster nodes
cat >> /etc/hosts <<EOF
# Proxmox Cluster Nodes
<main-node-ip>   <main-node-hostname> <main-node-short>
<node2-ip>       <node2-hostname> <node2-short>
<node3-ip>       <node3-hostname> <node3-short>
<new-node-ip>    <new-node-hostname> <new-node-short>
EOF

# Verify
cat /etc/hosts
```

**Critical**: Include ALL active cluster nodes plus the new node itself.

---

## Phase 3: Cluster Join Operation

### Step 3.1: Join Cluster

**IMPORTANT**: This operation will:
1. Prompt for root password of main node
2. Ask to confirm SSL fingerprint
3. Download cluster configuration
4. Set up Corosync
5. Start pve-cluster service

**Commands** (run on new node):
```bash
pvecm add <main-node-ip-or-hostname>
```

**Interactive Prompts**:
1. **Root password**: Enter main node root password
2. **Fingerprint confirmation**: Type `yes` to accept SSL certificate

**Expected Output**:
```
Please enter superuser (root) password for 'pve': *************
Establishing API connection with host 'pve'
The authenticity of host 'pve' can't be established.
X509 SHA256 key fingerprint is XX:XX:XX:...
Are you sure you want to continue connecting (yes/no)? yes
Login succeeded.
check cluster join API version
No cluster network links passed explicitly, fallback to local node IP '<node-ip>'
Request addition of this node
Join request OK, finishing setup locally
stopping pve-cluster service
backup old database to '/var/lib/pve-cluster/backup/config-TIMESTAMP.sql.gz'
waiting for quorum...OK
(re)generate node files
generate new node certificate
merge authorized SSH keys
generated new node certificate, restart pveproxy and pvedaemon services
successfully added node '<node-name>' to cluster.
```

**Success Indicators**:
- "Login succeeded" after password entry
- "Join request OK" confirmation
- "waiting for quorum...OK" (quorum achieved)
- "successfully added node" final message
- No error messages
- Command completes without hanging

**Key Steps**:
1. API connection established
2. SSL fingerprint accepted
3. Fallback to local IP (normal behavior)
4. Database backup created
5. Node certificates generated
6. SSH keys merged
7. Services restarted (pveproxy, pvedaemon)

**Failure Recovery**:
If join fails, clean up before retry:
```bash
systemctl stop pve-cluster corosync
pmxcfs -l                           # Kill cluster filesystem
rm -rf /etc/pve /etc/corosync/*
systemctl start pve-cluster
```

---

## Phase 4: Post-Join Verification

### Step 4.1: Verify from Main Node

**Commands** (run on main node):
```bash
pvecm status              # Check cluster status
pvecm nodes               # List all nodes
pvecm expected <N>        # Adjust quorum if needed (N = total nodes)
```

**What to Verify**:
- New node appears in node list
- New node shows as "online"
- Cluster is quorate
- Quorum votes updated correctly

---

### Step 4.2: Verify from New Node

**Commands** (run on new node):
```bash
pvecm status                              # Should show cluster membership
systemctl status pve-cluster corosync     # Both should be active
ls -la /etc/pve/                          # Cluster filesystem mounted
```

**What to Verify**:
- Cluster status shows membership
- Services running without errors
- /etc/pve/ filesystem accessible
- Can see other nodes' configuration

---

## Phase 5: Post-Join Configuration

### Step 5.1: Fix Cloud-init Hosts Template (CRITICAL)

**Purpose**: Ensure hostname resolves to actual IP (not loopback) after cloud-init regeneration

**Context**: Cloud-init regenerates `/etc/hosts` from template on boot. Default Debian template uses `127.0.1.1` for hostname, which breaks pmxcfs (Proxmox cluster filesystem).

**Issue**: pmxcfs requires hostname to resolve to non-loopback IP for cluster communication. Using `127.0.1.1` causes critical errors.

**Commands** (run on new node):
```bash
# Check current template
cat /etc/cloud/templates/hosts.debian.tmpl

# Fix template to use public_ipv4
sudo tee /etc/cloud/templates/hosts.debian.tmpl <<'EOF'
## template:jinja
{#
This file (/etc/cloud/templates/hosts.debian.tmpl) is only utilized
if enabled in cloud-config.  Specifically, in order to enable it
you need to add the following to config:
   manage_etc_hosts: True
-#}
{{public_ipv4}} {{fqdn}} {{hostname}}
::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF

# Manually fix /etc/hosts for immediate effect
sudo tee /etc/hosts <<EOF
127.0.0.1 localhost
::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters

# Proxmox cluster nodes
<main-node-ip>  <main-node-fqdn> <main-node-short>
<node2-ip>      <node2-fqdn> <node2-short>
<new-node-ip>   <new-node-fqdn> <new-node-short>
EOF

# Verify hostname resolution
hostname -i  # Should return actual IP, NOT 127.0.1.1
hostname -f  # Should return FQDN

# Check for pmxcfs errors
journalctl -u pmxcfs --since '1 minute ago' | grep -i 'unable to resolve'
```

**Success Criteria**:
- ✅ Template uses `{{public_ipv4}}` instead of `127.0.1.1`
- ✅ `/etc/hosts` maps hostname to actual IP address
- ✅ `hostname -i` returns non-loopback IP (e.g., 192.168.4.x)
- ✅ No pmxcfs hostname resolution errors in logs

**Why This Matters**: Without this fix, cloud-init will reset `/etc/hosts` to use `127.0.1.1` on every reboot, causing pmxcfs to fail and breaking cluster membership.

---

### Step 5.2: Disable Ceph Services (Critical)

**Purpose**: Prevent systemd ordering cycle issues with pve-cluster

**Context**: Ceph services can create circular dependencies with pve-cluster, causing non-deterministic boot failures (documented in still-fawn RCA).

**Commands** (run on new node):
```bash
# Check if Ceph exists
systemctl list-unit-files | grep ceph

# Disable if present
systemctl disable ceph-mon@<node-name> ceph-crash ceph.target || echo "Not present"

# Remove Ceph/pve-cluster ordering drop-in
rm -f /usr/lib/systemd/system/ceph-mon@.service.d/ceph-after-pve-cluster.conf
systemctl daemon-reload

# Verify no ordering cycles
journalctl -b | grep -i 'ordering cycle'
```

**Success Criteria**:
- Ceph services disabled or not present
- No "ordering cycle" warnings in logs
- pve-cluster has clean dependency tree

**Why This Matters**: Systemd randomly chooses which service to kill when cycles exist, leading to random boot failures.

---

### Step 5.3: Verify Web GUI Access

**Manual Test**:
1. Open browser: `https://<new-node-ip>:8006`
2. Login with root credentials
3. Navigate: Datacenter → Nodes
4. Verify all cluster nodes visible

**CLI Verification** (run on new node):
```bash
systemctl status pveproxy             # Web GUI service
curl -k https://localhost:8006        # Test local access
ls -la /etc/pve/local/                # Check SSL certificates
```

**Success Criteria**:
- pveproxy service running
- Web GUI loads
- Cluster view shows all nodes
- Can navigate to other nodes from GUI

---

## Phase 6: Reboot Stability Test

### Step 6.1: Test Boot Stability

**Purpose**: Ensure pve-cluster survives reboot (critical for production use)

**Commands**:
```bash
# From new node
reboot

# Wait 2 minutes, then verify (from another machine)
ping -c 3 <new-node-ip>
ssh <new-node> "systemctl status pve-cluster"
ssh <new-node> "journalctl -b | grep -E '(ordering cycle|pve-cluster|Failed)'"
ssh <new-node> "pvecm status"

# From main node
pvecm nodes                           # Verify new node online
```

**Success Criteria**:
- Node boots successfully
- pve-cluster starts automatically
- No ordering cycle errors in logs
- Cluster membership intact
- Web GUI accessible post-reboot

**Failure Indicators**:
- pve-cluster fails to start
- "ordering cycle" in logs
- Node shows offline in cluster
- systemd degraded state

**Recovery if Boot Fails**:
1. Check boot logs: `journalctl -b -u pve-cluster -u corosync`
2. Look for ordering cycles: `journalctl -b | grep 'ordering cycle'`
3. Check Ceph services: `systemctl list-units 'ceph*'`
4. Manually start if needed: `systemctl start pve-cluster`
5. Consult still-fawn RCA for detailed troubleshooting

---

## Phase 7: Documentation

### Update Infrastructure Documentation

**Files to Update**:
- Infrastructure architecture diagrams (add new node)
- Hardware inventory (node specifications)
- Network topology (IP address, hostname)
- Quorum calculations (update vote counts)
- Disaster recovery plans (include new node)

**Create Action Log**:
- Document all commands executed
- Record any issues encountered
- Note specific configurations for this node
- Include timestamps and results

---

## Success Criteria Checklist

### Cluster Integration
- [ ] New node appears in `pvecm status` on all nodes
- [ ] Cluster quorum maintained (no votes lost)
- [ ] Corosync communication working
- [ ] Cluster filesystem (/etc/pve) mounted on new node
- [ ] Can create/migrate VMs to new node

### Service Stability
- [ ] pve-cluster service survives reboot
- [ ] No systemd ordering cycle errors
- [ ] Web GUI accessible with cluster view
- [ ] All Proxmox services running (pveproxy, pvedaemon, etc.)
- [ ] No degraded systemd state

### Network and Access
- [ ] New node reachable from all cluster nodes
- [ ] Web GUI accessible on new node
- [ ] SSH access working
- [ ] DNS/hostname resolution correct

### Documentation
- [ ] Action log completed
- [ ] Infrastructure docs updated
- [ ] Any issues documented for future reference

---

## Common Issues and Solutions

### Issue 1: "Cannot get corosync config"

**Cause**: Network connectivity or firewall blocking Corosync ports

**Solution**:
```bash
# Check firewall on main node
iptables -L -n | grep 5405
ufw status

# Test UDP connectivity
nc -zuv <main-node-ip> 5405

# Check Corosync is running
systemctl status corosync
```

---

### Issue 2: "Authentication failed"

**Cause**: Wrong root password or SSH key issues

**Solution**:
- Verify root password on main node
- Check SSH key authentication: `ssh root@<main-node>`
- Ensure root login enabled: `/etc/ssh/sshd_config`

---

### Issue 3: Ordering Cycle on Boot

**Cause**: Ceph services creating dependency cycle with pve-cluster

**Solution**:
```bash
# Disable Ceph services
systemctl disable ceph-mon@<node> ceph-crash ceph.target

# Remove ordering drop-in
rm -f /usr/lib/systemd/system/ceph-mon@.service.d/ceph-after-pve-cluster.conf

# Reload and reboot
systemctl daemon-reload
reboot
```

**Reference**: See still-fawn RCA for detailed analysis.

---

### Issue 4: Quorum Lost After Join

**Cause**: Quorum votes not properly updated

**Solution**:
```bash
# Check current quorum
pvecm status

# Force expected votes (N = total nodes)
pvecm expected <N>

# Verify
pvecm status | grep -i quorum
```

---

### Issue 5: Node Shows Offline After Reboot

**Cause**: pve-cluster or corosync not starting

**Solution**:
```bash
# Check service status
systemctl status pve-cluster corosync

# Check for errors
journalctl -u pve-cluster -u corosync -b

# Check cluster filesystem
ls /etc/pve/  # Should show cluster config

# Manually start if needed
systemctl start pve-cluster
systemctl start corosync
```

---

## Risk Assessment

### Low Risk
- Adding node to healthy cluster with 3+ existing nodes
- Node and cluster on same network
- Same Proxmox major version

### Medium Risk
- Cluster currently at exactly 2 nodes (quorum at risk)
- Network latency between nodes >10ms
- Different Proxmox minor versions

### High Risk
- Cluster currently at 1 node (must convert to cluster first)
- Mixing Proxmox major versions
- Unstable existing cluster (frequent quorum loss)
- Node has existing Ceph configuration

---

## Related Documentation

- [Proxmox Official: Cluster Manager](https://pve.proxmox.com/wiki/Cluster_Manager)
- [still-fawn pve-cluster Failure RCA](../rca/2025-10-04-still-fawn-pve-cluster-failure.md)
- [Proxmox Infrastructure Guide](../source/md/proxmox-infrastructure-guide.md)

---

**Tags**: proxmox, cluster, pvecm, runbook, cluster-join, corosync, quorum, pve-cluster, systemd
