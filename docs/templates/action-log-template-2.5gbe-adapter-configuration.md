# Action Log Template: Configure 2.5GbE USB Adapter on Proxmox Node

**Date**: [YYYY-MM-DD]
**GitHub Issue**: #[ISSUE_NUMBER]
**Node**: [NODE_NAME] ([NODE_IP])
**Operator**: [YOUR_NAME]

---

## Context and Inputs

### Node Information
- **Node Name**: [NODE_NAME]
- **Current IP**: [NODE_IP]
- **Gateway**: [GATEWAY_IP] (usually 192.168.4.1)
- **Subnet**: [SUBNET] (usually /24)

### USB Adapter Information
- **Interface Name**: [USB_INTERFACE] (e.g., enx803f5df8d628)
- **MAC Address**: [USB_MAC_ADDRESS]
- **Current State**: [DETECTED/NOT_DETECTED]
- **Link Status**: [UP/DOWN/NO_CARRIER]

### Current Network Configuration
- **Active Interface**: [CURRENT_INTERFACE] (e.g., eno1, enp1s0)
- **IP Configuration**: [DIRECT_ON_INTERFACE/BRIDGE/OTHER]
- **Existing Bridges**: [LIST_BRIDGES or NONE]

### Cluster Context (If Applicable)
- **Cluster Name**: [CLUSTER_NAME]
- **Cluster Status**: [QUORATE/NOT_QUORATE]
- **Total Nodes**: [NODE_COUNT]
- **This Node Role**: [MEMBER/STANDALONE]

### Expected Outputs
- [ ] USB 2.5GbE adapter configured with vmbr0 bridge
- [ ] Same IP address maintained ([NODE_IP])
- [ ] Cluster connectivity preserved (if applicable)
- [ ] Configuration survives reboot
- [ ] VMs can be created on vmbr0 bridge

---

## Phase 1: Pre-Configuration Investigation

### Step 1.1: Document Current Configuration

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Backup current network config
ssh root@[NODE_NAME] "cp /etc/network/interfaces /etc/network/interfaces.backup.$(date +%Y%m%d_%H%M%S)"

# Capture current configuration
ssh root@[NODE_NAME] "cat /etc/network/interfaces"
ssh root@[NODE_NAME] "ip addr show"
ssh root@[NODE_NAME] "ip route show"

# Cluster status (if applicable)
ssh root@[NODE_NAME] "pvecm status"
```

**Results**:
- Current interface: [RESULT]
- IP configuration: [RESULT]
- Gateway: [RESULT]
- Cluster status: [RESULT or N/A]

**Configuration Backup Location**: `/etc/network/interfaces.backup.[TIMESTAMP]`

---

### Step 1.2: Identify USB Adapter

**Timestamp**: [HH:MM]

**Commands**:
```bash
# List network interfaces
ssh root@[NODE_NAME] "ip link show"

# Identify USB adapter
ssh root@[NODE_NAME] "ip link show | grep enx"

# Check adapter capabilities
ssh root@[NODE_NAME] "ethtool [USB_INTERFACE]"
```

**Results**:
- USB Interface Name: [RESULT]
- MAC Address: [RESULT]
- Supports 2500baseT: [YES/NO]
- Link Status: [UP/DOWN/NO_CARRIER]
- Current Speed: [SPEED or N/A]

**Decision**: [PROCEED/NEED_TO_CONNECT_CABLE/ADAPTER_NOT_DETECTED]

---

### Step 1.3: Verify Hostname Resolution

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Check hostname resolution
ssh root@[NODE_NAME] "hostname -i"
ssh root@[NODE_NAME] "hostname -f"

# Check /etc/hosts
ssh root@[NODE_NAME] "cat /etc/hosts"

# Check cloud-init template
ssh root@[NODE_NAME] "cat /etc/cloud/templates/hosts.debian.tmpl"

# Check for pmxcfs errors
ssh root@[NODE_NAME] "journalctl -u pmxcfs --since '1 hour ago' | grep -i 'unable to resolve'"
```

**Results**:
- `hostname -i` output: [RESULT]
- Resolves to loopback (127.0.1.1): [YES/NO]
- /etc/hosts correct: [YES/NO]
- Cloud-init template issue: [YES/NO]
- pmxcfs errors: [YES/NO]

**Issues Identified**:
- [ ] hostname -i returns 127.0.1.1 (CRITICAL)
- [ ] /etc/hosts has incorrect mapping
- [ ] Cloud-init template uses 127.0.1.1
- [ ] pmxcfs hostname resolution errors

---

## Phase 2: Physical Connection Verification

### Step 2.1: Verify Cable Connection

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Check physical link status
ssh root@[NODE_NAME] "ip link show [USB_INTERFACE]"
ssh root@[NODE_NAME] "ethtool [USB_INTERFACE] | grep 'Link detected'"
```

**Results**:
- Link State: [UP/DOWN]
- Carrier: [DETECTED/NO_CARRIER]
- Link Detected: [yes/no]

**Action Taken**: [NONE/CONNECTED_CABLE/RECONNECTED_CABLE/OTHER]

---

### Step 2.2: Verify Speed Negotiation

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Check negotiated speed
ssh root@[NODE_NAME] "ethtool [USB_INTERFACE] | grep -E '(Speed|Duplex|Auto-negotiation)'"
```

**Results**:
- Speed: [RESULT] (Expected: 2500Mb/s)
- Duplex: [RESULT] (Expected: Full)
- Auto-negotiation: [on/off]

**Issues**: [LIST_ANY_ISSUES or NONE]

---

## Phase 3: Network Configuration

### Step 3.1: Create vmbr0 Bridge Configuration

**Timestamp**: [HH:MM]

**Configuration to Apply**:
```
auto lo
iface lo inet loopback

# Built-in ethernet (backup)
iface [BUILTIN_INTERFACE] inet manual

# USB 2.5GbE adapter
auto [USB_INTERFACE]
iface [USB_INTERFACE] inet manual

# Bridge for cluster and VM networking
auto vmbr0
iface vmbr0 inet static
    address [NODE_IP]/24
    gateway [GATEWAY_IP]
    bridge-ports [USB_INTERFACE]
    bridge-stp off
    bridge-fd 0
```

**Commands**:
```bash
# Backup again before modification
ssh root@[NODE_NAME] "cp /etc/network/interfaces /etc/network/interfaces.before-vmbr0"

# Apply configuration
ssh root@[NODE_NAME] "tee /etc/network/interfaces" <<'EOF'
[PASTE_FULL_CONFIG_HERE]
EOF
```

**Verification**:
```bash
# Verify configuration written
ssh root@[NODE_NAME] "cat /etc/network/interfaces"
```

**Result**: [CONFIG_WRITTEN/FAILED]

---

## Phase 4: Cloud-init Hostname Fix

### Step 4.1: Fix Cloud-init Template

**Timestamp**: [HH:MM]

**Purpose**: Prevent cloud-init from overwriting /etc/hosts with 127.0.1.1

**Commands**:
```bash
# Update cloud-init template
ssh root@[NODE_NAME] "tee /etc/cloud/templates/hosts.debian.tmpl" <<'EOF'
## template:jinja
{#
This file (/etc/cloud/templates/hosts.debian.tmpl) is only utilized
if enabled in cloud-config.  Specifically, in order to enable it
you need to add the following to config:
   manage_etc_hosts: True
-#}
{{public_ipv4}} {{fqdn}} {{hostname}}
# The following lines are desirable for IPv6 capable hosts
::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF

# Verify template
ssh root@[NODE_NAME] "cat /etc/cloud/templates/hosts.debian.tmpl | grep public_ipv4"
```

**Result**: [TEMPLATE_UPDATED/FAILED]

---

### Step 4.2: Fix /etc/hosts

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Backup /etc/hosts
ssh root@[NODE_NAME] "cp /etc/hosts /etc/hosts.backup.$(date +%Y%m%d_%H%M%S)"

# Create correct /etc/hosts
ssh root@[NODE_NAME] "tee /etc/hosts" <<'EOF'
127.0.0.1 localhost
::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters

# Proxmox cluster nodes (adjust for your cluster)
[LIST_ALL_CLUSTER_NODES_WITH_IPS]
EOF

# Verify
ssh root@[NODE_NAME] "cat /etc/hosts"
```

**Verification**:
```bash
# Check hostname resolution
ssh root@[NODE_NAME] "hostname -i"
ssh root@[NODE_NAME] "hostname -f"
```

**Results**:
- `hostname -i`: [RESULT] (Should be [NODE_IP], NOT 127.0.1.1)
- `hostname -f`: [RESULT] (Should be [NODE_FQDN])
- /etc/hosts correct: [YES/NO]

**Result**: [SUCCESS/FAILED]

---

### Step 4.3: Handle MAAS/Netplan Network Configuration (For MAAS-deployed nodes)

**Timestamp**: [HH:MM]

**Purpose**: Prevent duplicate IP addresses from MAAS cloud-init netplan configuration

**Problem**: If node deployed via MAAS, cloud-init creates netplan configuration that configures the built-in ethernet interface with the node's IP address. This creates duplicate IP situation when you also configure vmbr0 bridge.

**Solution Options**:

**Option A: Unplug built-in ethernet cable (RECOMMENDED)**:
```bash
# Physically unplug the 1GbE cable from built-in ethernet port
# This prevents MAAS netplan from configuring it
# Result: Clean single-IP configuration on vmbr0 only
```

**Option B: Disable cloud-init network configuration**:
```bash
# Create cloud-init disable file
ssh root@[NODE_NAME] "tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg" <<'EOF'
network: {config: disabled}
EOF

# Note: May not work if MAAS provides config via vendordata
```

**Option C: Disable systemd-networkd**:
```bash
# Disable systemd-networkd service
ssh root@[NODE_NAME] "systemctl disable systemd-networkd"
ssh root@[NODE_NAME] "systemctl mask systemd-networkd"

# Note: May be re-enabled by cloud-init on reboot
```

**Decision Made**: [OPTION_A/OPTION_B/OPTION_C/NOT_APPLICABLE]

**Action Taken**: [DESCRIPTION]

**Verification After Reboot**:
```bash
# Check for duplicate IPs
ssh root@[NODE_NAME] "ip addr show | grep 'inet '"

# Verify only vmbr0 has IP
ssh root@[NODE_NAME] "ip addr show vmbr0 | grep 'inet '"
ssh root@[NODE_NAME] "ip addr show [BUILTIN_INTERFACE] | grep 'inet '"

# Check systemd state
ssh root@[NODE_NAME] "systemctl is-system-running"
```

**Results**:
- Built-in interface has IP: [YES/NO]
- vmbr0 has IP: [YES/NO]
- Duplicate IP detected: [YES/NO]
- systemd state: [RESULT]

**Additional Actions If Needed**:
```bash
# If systemd-networkd-wait-online.service fails after unplugging cable
ssh root@[NODE_NAME] "systemctl mask systemd-networkd-wait-online.service"
```

**Result**: [CLEAN_CONFIGURATION/DUPLICATE_IPS_REMAINING/FAILED]

---

## Phase 5: Apply Network Configuration

### Step 5.1: Apply Configuration Method

**Timestamp**: [HH:MM]

**Method Chosen**: [IFRELOAD/REBOOT]

**If using ifreload**:
```bash
# Apply new network config
ssh root@[NODE_NAME] "ifreload -a"

# Verify network still accessible
ping -c 4 [NODE_IP]
```

**If using reboot**:
```bash
# Reboot node
ssh root@[NODE_NAME] "reboot"

# Wait for boot
sleep 120

# Verify node came back
ping -c 4 [NODE_IP]
```

**Result**: [APPLIED_SUCCESSFULLY/LOST_CONNECTION/FAILED]

---

### Step 5.2: Verify vmbr0 Configuration

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Check vmbr0 exists with IP
ssh root@[NODE_NAME] "ip addr show vmbr0"

# Check routing
ssh root@[NODE_NAME] "ip route show"

# Verify gateway reachable
ssh root@[NODE_NAME] "ping -c 4 [GATEWAY_IP]"
```

**Results**:
- vmbr0 exists: [YES/NO]
- vmbr0 has IP [NODE_IP]: [YES/NO]
- Bridge ports include [USB_INTERFACE]: [YES/NO]
- Default route via gateway: [YES/NO]
- Gateway reachable: [YES/NO]

**Result**: [SUCCESS/PARTIAL/FAILED]

---

### Step 5.3: Verify Cluster Connectivity (If Applicable)

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Check cluster status
ssh root@[NODE_NAME] "pvecm status"

# Verify corosync
ssh root@[NODE_NAME] "corosync-cfgtool -s"

# Check cluster filesystem
ssh root@[NODE_NAME] "ls -la /etc/pve/"

# Check pve-cluster service
ssh root@[NODE_NAME] "systemctl status pve-cluster"

# Test connectivity to other nodes
ssh root@[NODE_NAME] "ping -c 4 [OTHER_NODE_IP]"
```

**Results**:
- Cluster quorate: [YES/NO]
- Node in member list: [YES/NO]
- Corosync connected: [YES/NO]
- /etc/pve accessible: [YES/NO]
- pve-cluster running: [YES/NO]
- Can reach other nodes: [YES/NO]

**Result**: [CLUSTER_HEALTHY/ISSUES_DETECTED/N/A]

---

## Phase 6: Web GUI Verification

### Step 6.1: Test Web GUI Access

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Check pveproxy service
ssh root@[NODE_NAME] "systemctl status pveproxy"

# Test HTTPS access
curl -k https://[NODE_IP]:8006
```

**Manual Browser Test**:
- URL: https://[NODE_IP]:8006
- Login successful: [YES/NO]
- Cluster view visible: [YES/NO or N/A]
- All nodes listed: [YES/NO or N/A]

**Result**: [GUI_ACCESSIBLE/FAILED]

---

## Phase 7: Reboot Stability Test

### Step 7.1: Reboot Test

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Reboot node
ssh root@[NODE_NAME] "reboot"

# Wait for boot
sleep 180

# Verify boot completed
ping -c 4 [NODE_IP]
```

**Boot Duration**: [X minutes Y seconds]

**Result**: [BOOTED_SUCCESSFULLY/FAILED_TO_BOOT/TIMEOUT]

---

### Step 7.2: Post-Reboot Verification

**Timestamp**: [HH:MM]

**Commands**:
```bash
# Check vmbr0 configuration persisted
ssh root@[NODE_NAME] "ip addr show vmbr0"
ssh root@[NODE_NAME] "ip route show"

# Verify hostname resolution
ssh root@[NODE_NAME] "hostname -i"
ssh root@[NODE_NAME] "cat /etc/hosts | grep [NODE_NAME]"

# Check cluster membership (if applicable)
ssh root@[NODE_NAME] "pvecm status"
ssh root@[NODE_NAME] "systemctl status pve-cluster"

# Check for pmxcfs errors
ssh root@[NODE_NAME] "journalctl -b | grep -i pmxcfs | grep -i 'unable to resolve'"

# Check systemd state
ssh root@[NODE_NAME] "systemctl is-system-running"
```

**Results**:
- vmbr0 has IP: [YES/NO]
- Routing correct: [YES/NO]
- hostname -i correct: [YES/NO]
- /etc/hosts persisted: [YES/NO]
- Cluster rejoined: [YES/NO or N/A]
- pve-cluster running: [YES/NO or N/A]
- pmxcfs errors: [YES/NO]
- systemd state: [RESULT]

**Result**: [ALL_CHECKS_PASSED/ISSUES_DETECTED]

---

## Summary

### Overall Status
- [ ] All phases completed successfully
- [ ] USB 2.5GbE adapter configured
- [ ] vmbr0 bridge operational
- [ ] Cluster connectivity maintained (if applicable)
- [ ] Configuration survives reboot

### Execution Time
- **Start Time**: [HH:MM]
- **End Time**: [HH:MM]
- **Total Duration**: [X hours Y minutes]

### Success Criteria Met
- [ ] USB 2.5GbE adapter in vmbr0 bridge
- [ ] Same IP address maintained ([NODE_IP])
- [ ] Speed: 2500Mb/s confirmed
- [ ] Gateway reachable
- [ ] Cluster quorate (if applicable)
- [ ] hostname -i returns actual IP (not 127.0.1.1)
- [ ] Configuration survives reboot
- [ ] Web GUI accessible
- [ ] No systemd degraded state

### Issues Encountered
[LIST ALL ISSUES AND THEIR RESOLUTIONS]

1. **Issue**: [DESCRIPTION]
   - **Root Cause**: [ANALYSIS]
   - **Resolution**: [STEPS_TAKEN]
   - **Result**: [RESOLVED/WORKAROUND/ONGOING]

### Configuration Changes Made

**Network Configuration**:
- Migrated from: [OLD_INTERFACE] → vmbr0 bridge on [USB_INTERFACE]
- IP: [NODE_IP] (unchanged)
- Gateway: [GATEWAY_IP]
- Speed: [OLD_SPEED] → 2500Mb/s

**Files Modified**:
- `/etc/network/interfaces` - Bridge configuration
- `/etc/hosts` - Hostname to IP mapping
- `/etc/cloud/templates/hosts.debian.tmpl` - Cloud-init template fix

**Services Restarted**:
- [LIST_SERVICES_RESTARTED]

---

## Lessons Learned

### What Went Well
[LIST_POSITIVE_OUTCOMES]

### Challenges Encountered
[LIST_CHALLENGES]

### Improvements for Next Time
[LIST_IMPROVEMENTS]

### Documentation Updates Needed
- [ ] Update infrastructure diagram with new network config
- [ ] Update hardware inventory with USB adapter details
- [ ] Update disaster recovery procedures
- [ ] Update monitoring checks

---

## Next Steps

1. **Immediate** (Next 24 hours):
   - [ ] Monitor node stability
   - [ ] Check cluster logs for any anomalies
   - [ ] Verify VM creation works on vmbr0

2. **Short-term** (Next week):
   - [ ] Performance testing (iperf3 throughput test)
   - [ ] Update documentation with actual results
   - [ ] Close GitHub issue #[ISSUE_NUMBER]

3. **Long-term**:
   - [ ] Apply same configuration to other nodes (if applicable)
   - [ ] Document standard node configuration pattern
   - [ ] Create monitoring alerts for USB adapter status

---

## Validation Checklist

### Network Layer
- [ ] USB adapter link UP and CARRIER detected
- [ ] Speed negotiated: 2500Mb/s Full Duplex
- [ ] vmbr0 bridge exists with correct IP
- [ ] Gateway reachable via ping
- [ ] External connectivity working

### System Layer
- [ ] hostname -i returns [NODE_IP] (not 127.0.1.1)
- [ ] /etc/hosts maps hostname correctly
- [ ] Cloud-init template uses {{public_ipv4}}
- [ ] No pmxcfs hostname resolution errors
- [ ] systemd state: running (not degraded)

### Proxmox Layer
- [ ] pve-cluster service active and running
- [ ] pveproxy service active and running
- [ ] Web GUI accessible at https://[NODE_IP]:8006
- [ ] Can login to web interface
- [ ] Storage visible in GUI

### Cluster Layer (If Applicable)
- [ ] Node appears in pvecm status
- [ ] Cluster is quorate
- [ ] Corosync communication working
- [ ] /etc/pve filesystem mounted
- [ ] Can see other cluster nodes in GUI

### Persistence
- [ ] Configuration survives reboot
- [ ] vmbr0 comes up automatically after boot
- [ ] Hostname resolution persists after reboot
- [ ] Cluster rejoins automatically (if applicable)

---

**Tags**: action-log, proxmox, 2.5gbe, usb-adapter, vmbr0, network-configuration, [NODE_NAME]
