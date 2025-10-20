# Action Log Template: Add P520 (pumped-piglet) to Proxmox Cluster

**Date**: October 20, 2025
**GitHub Issue**: #156
**Nodes Involved**:
- **New Node**: pumped-piglet (192.168.4.175) - Intel Xeon W-2123, 32GB RAM
- **Cluster Main**: pve.maas (192.168.4.122) - Intel N100, 16GB RAM
- **Context**: still-fawn (192.168.4.17) offline due to CPU fan failure

---

## Context and Constraints

### Hardware Replacement Context
- **Replacement**: pumped-piglet (P520) temporarily replacing still-fawn
- **still-fawn Status**: Offline (CPU fan failure) - DO NOT REMOVE from cluster
- **Future Plan**: still-fawn will return (without GPU) after fan replacement
- **Long-term**: If still-fawn issues persist, it will be permanently removed

### Inputs
- **New node hostname**: pumped-piglet
- **New node IP**: 192.168.4.175
- **Cluster main node**: pve.maas (192.168.4.122)
- **SSH access**: `ssh debian@192.168.4.175` (Debian cloud-init user)
- **Root access main node**: `ssh root@pve.maas`

### Expected Outputs
- pumped-piglet joined to cluster successfully
- Cluster quorum maintained
- pve-cluster service stable through reboot
- Web GUI accessible with cluster view
- No systemd ordering cycles

---

## Phase 1: Pre-Join Investigation

### Step 1.1: Verify Cluster Status on pve.maas

**Timestamp**: [HH:MM]

**Commands**:
```bash
ssh root@pve.maas "pvecm status"
ssh root@pve.maas "pvecm nodes"
ssh root@pve.maas "cat /etc/pve/.members"
```

**Results**:
- Current cluster name: [RESULT]
- Active nodes: [RESULT]
- Quorum status: [RESULT]
- still-fawn status in cluster: [RESULT]

**Decision**: [still-fawn removal needed? Yes/No]

---

### Step 1.2: Verify pumped-piglet Standalone Status

**Timestamp**: [HH:MM]

**Commands**:
```bash
ssh debian@192.168.4.175 "sudo pvecm status"
ssh debian@192.168.4.175 "sudo cat /etc/hostname"
ssh debian@192.168.4.175 "sudo systemctl status pve-cluster"
ssh debian@192.168.4.175 "pveversion"
```

**Results**:
- Standalone confirmed: [RESULT]
- Current hostname: [RESULT]
- pve-cluster status: [RESULT]
- Proxmox version: [RESULT]

---

### Step 1.3: Network Connectivity Tests

**Timestamp**: [HH:MM]

**Commands**:
```bash
# From pumped-piglet to pve.maas
ssh debian@192.168.4.175 "ping -c 3 192.168.4.122"
ssh debian@192.168.4.175 "sudo nc -zv 192.168.4.122 8006"
ssh debian@192.168.4.175 "sudo nc -zv 192.168.4.122 5405"

# Test to other active nodes (adjust based on Step 1.1 results)
ssh debian@192.168.4.175 "ping -c 3 192.168.4.19"    # chief-horse
ssh debian@192.168.4.175 "ping -c 3 192.168.4.172"   # fun-bedbug
```

**Results**:
- Connectivity to pve.maas: [RESULT]
- Port 8006 accessible: [RESULT]
- Port 5405 accessible: [RESULT]
- Connectivity to other nodes: [RESULT]

---

## Phase 2: Pre-Join Preparation

### Step 2.1: Set Hostname on pumped-piglet

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Check current hostname
ssh debian@192.168.4.175 "hostname"

# Set if needed
ssh debian@192.168.4.175 "sudo hostnamectl set-hostname pumped-piglet"

# Verify
ssh debian@192.168.4.175 "hostname && cat /etc/hostname"
```

**Results**:
- Previous hostname: [RESULT]
- New hostname: [RESULT]
- Hostname change needed: [Yes/No]

---

### Step 2.2: Update /etc/hosts on pumped-piglet

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Backup
ssh debian@192.168.4.175 "sudo cp /etc/hosts /etc/hosts.backup"

# Add cluster nodes (adjust based on Phase 1 findings)
ssh debian@192.168.4.175 "sudo tee -a /etc/hosts" <<EOF
# Proxmox Cluster Nodes
192.168.4.122  pve.maas pve
192.168.4.19   chief-horse.maas chief-horse
192.168.4.172  fun-bedbug.maas fun-bedbug
192.168.4.175  pumped-piglet.maas pumped-piglet
EOF

# Verify
ssh debian@192.168.4.175 "cat /etc/hosts | grep -E '(pve|chief|bedbug|piglet)'"
```

**Results**:
- /etc/hosts entries added: [RESULT]
- Name resolution verified: [RESULT]

---

## Phase 3: Cluster Join Operation

### Step 3.1: Join Cluster from pumped-piglet

**Timestamp**: [HH:MM]

**Commands**:
```bash
ssh debian@192.168.4.175 "sudo pvecm add 192.168.4.122"
```

**Interactive Prompts**:
- Root password for pve.maas: [Entered]
- Fingerprint confirmation: [yes typed]

**Expected Output**:
```
Please enter superuser (root) password for 'pve': *************
Establishing API connection with host 'pve'
The authenticity of host 'pve' can't be established.
X509 SHA256 key fingerprint is XX:XX:XX:...
Are you sure you want to continue connecting (yes/no)? yes
Login succeeded.
check cluster join API version
No cluster network links passed explicitly, fallback to local node IP '192.168.4.175'
Request addition of this node
Join request OK, finishing setup locally
stopping pve-cluster service
backup old database to '/var/lib/pve-cluster/backup/config-XXXXXXXXXX.sql.gz'
waiting for quorum...OK
(re)generate node files
generate new node certificate
merge authorized SSH keys
generated new node certificate, restart pveproxy and pvedaemon services
successfully added node 'pumped-piglet' to cluster.
```

**Actual Output**: [PASTE FULL OUTPUT]

**Key Steps to Verify**:
1. API connection established
2. SSL fingerprint accepted (type 'yes')
3. Fallback to local IP confirmed
4. Join request accepted
5. Database backup created
6. Quorum achieved
7. Node certificates generated
8. SSH keys merged
9. Services restarted
10. Success message displayed

**Result**: [Success/Failed]

**Issues Encountered**: [DESCRIBE ANY]

---

## Phase 4: Post-Join Verification

### Step 4.1: Verify from pve.maas

**Timestamp**: [HH:MM]

**Commands**:
```bash
ssh root@pve.maas "pvecm status"
ssh root@pve.maas "pvecm nodes"
```

**Results**:
- pumped-piglet in node list: [Yes/No]
- Cluster quorate: [Yes/No]
- pumped-piglet status: [online/offline]
- Current node count: [RESULT]

---

### Step 4.2: Verify from pumped-piglet

**Timestamp**: [HH:MM]

**Commands**:
```bash
ssh debian@192.168.4.175 "sudo pvecm status"
ssh debian@192.168.4.175 "sudo systemctl status pve-cluster corosync"
ssh debian@192.168.4.175 "sudo ls -la /etc/pve/"
```

**Results**:
- Cluster membership confirmed: [RESULT]
- pve-cluster service: [RESULT]
- corosync service: [RESULT]
- /etc/pve filesystem: [RESULT]

---

## Phase 5: Post-Join Configuration

### Step 5.1: Disable Ceph Services on pumped-piglet

**Timestamp**: [HH:MM]

**Context**: Prevent systemd ordering cycles (lesson from still-fawn RCA)

**Commands**:
```bash
# Check if Ceph services exist
ssh debian@192.168.4.175 "sudo systemctl list-unit-files | grep ceph"

# Disable if present
ssh debian@192.168.4.175 "sudo systemctl disable ceph-mon@pumped-piglet ceph-crash ceph.target" || echo "Not present"

# Remove ordering drop-in
ssh debian@192.168.4.175 "sudo rm -f /usr/lib/systemd/system/ceph-mon@.service.d/ceph-after-pve-cluster.conf"
ssh debian@192.168.4.175 "sudo systemctl daemon-reload"

# Check for ordering cycles
ssh debian@192.168.4.175 "sudo journalctl -b | grep -i 'ordering cycle'"
```

**Results**:
- Ceph services present: [Yes/No]
- Ceph services disabled: [RESULT]
- Ordering cycles detected: [Yes/No]

---

### Step 5.2: Test Web GUI Access

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Test from command line
curl -k https://192.168.4.175:8006

# Check pveproxy service
ssh debian@192.168.4.175 "sudo systemctl status pveproxy"
```

**Manual Browser Test**:
- URL: https://192.168.4.175:8006
- Login successful: [Yes/No]
- Cluster view visible: [Yes/No]
- All nodes listed: [List nodes visible]

**Results**:
- pveproxy service: [RESULT]
- Web GUI accessible: [RESULT]
- Cluster view working: [RESULT]

---

## Phase 6: Reboot Stability Test

### Step 6.1: Reboot pumped-piglet

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Reboot
ssh debian@192.168.4.175 "sudo reboot"

# Wait 2 minutes
sleep 120

# Verify boot
ping -c 3 192.168.4.175
```

**Result**: [Node came back online: Yes/No]

---

### Step 6.2: Post-Reboot Verification

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Check pve-cluster service
ssh debian@192.168.4.175 "sudo systemctl status pve-cluster"

# Check for errors
ssh debian@192.168.4.175 "sudo journalctl -b | grep -E '(ordering cycle|pve-cluster|Failed to start)'"

# Verify cluster membership
ssh debian@192.168.4.175 "sudo pvecm status"
ssh root@pve.maas "pvecm nodes"

# Check systemd state
ssh debian@192.168.4.175 "sudo systemctl is-system-running"
```

**Results**:
- pve-cluster started: [RESULT]
- Ordering cycles: [Yes/No]
- Cluster membership intact: [RESULT]
- systemd state: [RESULT]
- Boot duration: [RESULT]

---

## Summary

### Overall Status
- [ ] All phases completed successfully
- [ ] pumped-piglet in cluster and operational
- [ ] No ordering cycle issues detected
- [ ] Reboot test passed

### Execution Time
- **Start Time**: [HH:MM]
- **End Time**: [HH:MM]
- **Total Duration**: [X hours Y minutes]

### Success Criteria Met
- [ ] pumped-piglet in pvecm status on all nodes
- [ ] Cluster quorum maintained
- [ ] pve-cluster survives reboot
- [ ] Web GUI with cluster view working
- [ ] No systemd ordering cycles

### Issues Encountered
[List any problems and their resolutions]

### Configuration Details
- **Final node count**: [RESULT]
- **Quorum requirement**: [RESULT]
- **Ceph services disabled**: [Yes/No]
- **still-fawn status**: [In cluster but offline/Removed/Other]

---

## Next Steps

1. **Documentation Updates**:
   - [ ] Update `docs/source/md/proxmox-infrastructure-guide.md` with pumped-piglet
   - [ ] Commit action log instance with results
   - [ ] Close GitHub Issue #156 with commit reference

2. **Future Actions**:
   - [ ] Monitor pumped-piglet stability over 24-48 hours
   - [ ] When still-fawn CPU fan replaced, add it back to cluster
   - [ ] Decide on still-fawn long-term status based on stability

3. **Related Tasks**:
   - [ ] Update network documentation with pumped-piglet
   - [ ] Update disaster recovery procedures
   - [ ] Consider GPU passthrough to pumped-piglet (if needed)

---

**Tags**: action-log-template, p520, pumped-piglet, proxmox, cluster, pvecm, cluster-join, still-fawn-offline
