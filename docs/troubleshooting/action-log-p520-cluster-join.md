# Action Log: Add P520 (pumped-piglet) to Proxmox Cluster

**Date**: October 20, 2025
**Issue**: Add pumped-piglet to Proxmox cluster while still-fawn is temporarily offline
**Node Being Added**: pumped-piglet (192.168.4.175)
**Cluster Main Node**: pve.maas (192.168.4.122)
**GitHub Issue**: #156

---

## Initial Plan

- **Goal**: Successfully add pumped-piglet (Intel Xeon P520) to existing Proxmox cluster
- **Approach**: Follow blueprint phases - investigation → preparation → join → verification → reboot test
- **Success Criteria**:
  - pumped-piglet appears in `pvecm status` on all cluster nodes
  - Cluster quorum maintained
  - pve-cluster service survives reboot
  - Web GUI accessible with cluster view
  - No systemd ordering cycles

- **Context**: still-fawn is temporarily offline (CPU fan failure), will be added back later
  - Do NOT remove still-fawn from cluster
  - pumped-piglet is being added as additional node
  - Cluster will temporarily have one offline node (still-fawn)

---

## Investigation Phase

| Time | Command/Action | Result | Impact on Plan |
|------|---------------|--------|---------------|
| [HH:MM] | Ready to start investigation | Documentation complete | ✓ Proceed with Phase 1 |

**Note**: Will begin with cluster status investigation on pve.maas

---

## Phase 1: Pre-Join Investigation

### Step 1.1: Verify Cluster Status on pve.maas

**Timestamp**: [To be filled during execution]

**Commands**: [To be executed]

**Results**: [To be filled]

---

## Phase 2: Pre-Join Preparation

[To be filled during execution]

---

## Phase 3: Cluster Join Operation

### Step 3.1: Join Cluster from pumped-piglet

**Timestamp**: 10:15 AM

**Command**:
```bash
ssh root@pumped-piglet "pvecm add pve"
```

**Interactive Prompts**:
- Root password for pve: ************* (entered)
- X509 SHA256 fingerprint confirmation: yes (typed)

**Actual Output**:
```
Please enter superuser (root) password for 'pve': *************
Establishing API connection with host 'pve'
The authenticity of host 'pve' can't be established.
X509 SHA256 key fingerprint is 94:A1:CC:1A:58:97:4D:08:96:F7:61:2E:84:F1:B1:DE:62:14:48:07:B3:00:37:1B:2B:0D:B7:31:82:A1:9A:16.
Are you sure you want to continue connecting (yes/no)? yes
Login succeeded.
check cluster join API version
No cluster network links passed explicitly, fallback to local node IP '192.168.4.175'
Request addition of this node
Join request OK, finishing setup locally
stopping pve-cluster service
backup old database to '/var/lib/pve-cluster/backup/config-1760986308.sql.gz'
waiting for quorum...OK
(re)generate node files
generate new node certificate
merge authorized SSH keys
generated new node certificate, restart pveproxy and pvedaemon services
successfully added node 'pumped-piglet' to cluster.
```

**Result**: ✅ Success

**Key Steps Observed**:
1. API connection established to pve
2. SSL fingerprint verified and accepted
3. Fallback to local IP (192.168.4.175) - expected behavior
4. Join request accepted by cluster
5. Database backup created
6. Quorum achieved successfully
7. Node certificates generated
8. SSH keys merged
9. Services restarted (pveproxy, pvedaemon)
10. Join completed successfully

---

## Phase 4: Post-Join Verification

[To be filled during execution]

---

## Phase 5: Post-Join Configuration

[To be filled during execution]

---

## Phase 6: Reboot Stability Test

[To be filled during execution]

---

## Summary

### Overall Status
- [ ] All Phases Complete
- [ ] All Critical Steps Verified
- [ ] GitHub Issue Updated
- [ ] Documentation Committed

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
[To be filled during execution]

### Lessons Learned
[To be filled during execution]

---

**Tags**: action-log, p520, pumped-piglet, proxmox, cluster, pvecm, cluster-join, still-fawn-offline
