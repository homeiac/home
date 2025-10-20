# Runbook: Configure 2.5GbE USB Adapter on Proxmox Node

**Purpose**: Migrate a Proxmox cluster node from built-in Ethernet to USB 2.5GbE adapter
**Scope**: Generic procedure for any Proxmox node using USB network adapter
**Related Guides**: [2.5GbE Network Migration Guide](../../proxmox/guides/2.5gbe-migration.md)

---

## Overview

This runbook provides the complete procedure for configuring a Proxmox cluster node to use a USB 2.5GbE network adapter instead of built-in Ethernet. This migration maintains the same IP address and ensures cluster communication over the faster 2.5GbE network.

**Key Success Criteria**:
- USB 2.5GbE adapter configured with vmbr0 bridge
- Same IP address maintained
- Cluster connectivity preserved
- Configuration survives reboot
- VMs can be created on vmbr0 bridge

---

## Prerequisites

### Hardware Requirements
- USB 2.5GbE adapter physically connected to node
- Network cable connected to 2.5GbE switch
- Adapter supports 2500baseT speed

### Software Requirements
- Proxmox VE installed and operational
- Node already in cluster (or standalone)
- SSH access to node
- Root privileges

### Network Requirements
- IP address assigned and accessible
- Cluster communication working (if in cluster)
- Gateway reachable at 192.168.4.1 (adjust for your network)

### Pre-Configuration Checks
```bash
# Verify USB adapter detected
lspci | grep -i ethernet  # Check built-in adapters
ip link show              # Check all network interfaces

# Identify USB adapter (usually enx followed by MAC address)
ip link show | grep -E '^[0-9]+:' | grep enx

# Verify cluster status (if in cluster)
pvecm status
```

---

## Phase 1: Pre-Configuration Investigation

### Step 1.1: Document Current Network Configuration

**Purpose**: Record existing configuration for rollback if needed

**Commands**:
```bash
# Backup current network config
cp /etc/network/interfaces /etc/network/interfaces.backup.$(date +%Y%m%d_%H%M%S)

# Document current configuration
cat /etc/network/interfaces
ip addr show
ip route show

# Save cluster configuration (if in cluster)
pvecm status > /tmp/cluster-status-before.txt
cat /etc/corosync/corosync.conf > /tmp/corosync-before.txt
```

**What to Document**:
- Current IP address and subnet
- Gateway configuration
- Interface currently used (e.g., eno1, enp1s0)
- Any existing bridges (vmbr0, vmbr1)
- Cluster ring0_addr (if in cluster)

---

### Step 1.2: Identify USB Adapter

**Purpose**: Find the USB 2.5GbE adapter interface name and MAC address

**Commands**:
```bash
# List all network interfaces
ip link show

# Check USB adapter details
ip link show | grep enx
ethtool enx<MAC_ADDRESS> | grep -E "(Speed|Link detected)"

# Verify adapter supports 2500baseT
ethtool enx<MAC_ADDRESS> | grep "2500baseT"
```

**Expected Output**:
- Interface name: `enx803f5df8xxxx` (enx + MAC address)
- Supported modes include: `2500baseT/Full`
- Link detected: `yes` (if cable connected)
- Speed: `2500Mb/s` (if cable connected and link up)

**Common Issues**:
- **NO CARRIER**: Cable not connected or bad connection
- **10Mb/s Half**: Autonegotiation failed, check cable and switch
- **Not found**: USB adapter not recognized, check USB connection

---

### Step 1.3: Verify Cloud-init Configuration

**Purpose**: Ensure hostname resolution works correctly for cluster filesystem

**Commands**:
```bash
# Check current hostname resolution
hostname -i
hostname -f

# Check /etc/hosts
cat /etc/hosts

# Check cloud-init template
cat /etc/cloud/templates/hosts.debian.tmpl
```

**Critical Check**:
- `hostname -i` should return the node's actual IP, NOT 127.0.1.1
- `/etc/hosts` should map hostname to actual IP
- Cloud-init template should use `{{public_ipv4}}` NOT `127.0.1.1`

**Why This Matters**: Proxmox cluster filesystem (pmxcfs) requires hostname to resolve to a non-loopback IP. Using 127.0.1.1 causes cluster filesystem failures.

---

## Phase 2: Physical Connection Verification

### Step 2.1: Verify Physical Cable Connection

**Purpose**: Ensure USB adapter is connected to network switch

**Commands**:
```bash
# Check link status
ip link show <usb-adapter-name>

# Check if link is UP and has CARRIER
ethtool <usb-adapter-name> | grep "Link detected"
```

**Expected Results**:
- Interface state: `UP`
- Link detected: `yes`
- Carrier: `LOWER_UP` (in ip link output)

**If NO CARRIER**:
1. Verify cable is plugged into USB adapter
2. Verify cable is plugged into switch
3. Check switch port is enabled
4. Try different cable
5. Check USB adapter is firmly seated

---

### Step 2.2: Verify Speed Negotiation

**Purpose**: Confirm adapter negotiated 2.5GbE speed

**Commands**:
```bash
ethtool <usb-adapter-name> | grep -E "(Speed|Duplex|Auto-negotiation)"
```

**Expected Output**:
```
Speed: 2500Mb/s
Duplex: Full
Auto-negotiation: on
```

**Common Issues**:
- **1000Mb/s**: Switch port only supports 1GbE (still works, just slower)
- **100Mb/s or 10Mb/s**: Autonegotiation problem, check cable quality
- **Half duplex**: Cable or switch issue, check physical connection

---

## Phase 3: Network Configuration

### Step 3.1: Create vmbr0 Bridge Configuration

**Purpose**: Configure bridge with USB adapter as port

**Standard Pattern** (used by chief-horse, fun-bedbug):
```
auto <usb-adapter-name>
iface <usb-adapter-name> inet manual

auto vmbr0
iface vmbr0 inet static
    address <node-ip>/24
    gateway 192.168.4.1
    bridge-ports <usb-adapter-name>
    bridge-stp off
    bridge-fd 0
```

**Example for node at 192.168.4.175**:
```bash
# Edit /etc/network/interfaces
nano /etc/network/interfaces

# Add this configuration:
auto lo
iface lo inet loopback

# Built-in ethernet (set to manual, unused)
iface eno1 inet manual

# USB 2.5GbE adapter
auto enx803f5df8d628
iface enx803f5df8d628 inet manual

# Bridge for cluster and VM networking
auto vmbr0
iface vmbr0 inet static
    address 192.168.4.175/24
    gateway 192.168.4.1
    bridge-ports enx803f5df8d628
    bridge-stp off
    bridge-fd 0
```

**Configuration Notes**:
- `auto <interface>`: Bring up interface automatically at boot
- `inet manual`: Interface managed by bridge, no IP directly on it
- `bridge-stp off`: Spanning tree protocol disabled (simple topology)
- `bridge-fd 0`: No forwarding delay
- **Keep same IP address** to avoid cluster reconfiguration

---

### Step 3.2: Set Built-in Ethernet to Manual

**Purpose**: Disable IP on built-in ethernet, available as backup

**Pattern**:
```
iface eno1 inet manual
```

**Why**:
- Prevents duplicate IP addresses
- Keeps interface available for emergency access
- Clean configuration with single active path

---

## Phase 4: Cloud-init Hostname Fix (CRITICAL)

### Step 4.1: Fix Cloud-init Hosts Template

**Purpose**: Prevent cloud-init from overwriting /etc/hosts with loopback IP

**Problem**: Default Debian cloud-init template uses `127.0.1.1` for hostname, which breaks pmxcfs.

**Solution Options**:

**Option A: Hardcode IP in Template (RECOMMENDED - works even if MAAS metadata broken)**:
```bash
# Update cloud-init template with actual node IP
sudo tee /etc/cloud/templates/hosts.debian.tmpl <<'EOF'
## template:jinja
{#
This file (/etc/cloud/templates/hosts.debian.tmpl) is only utilized
if enabled in cloud-config.  Specifically, in order to enable it
you need to add the following to config:
   manage_etc_hosts: True
-#}
<node-ip> {{fqdn}} {{hostname}}
# The following lines are desirable for IPv6 capable hosts
::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF

# Example for node at 192.168.4.175:
192.168.4.175 {{fqdn}} {{hostname}}
```

**Option B: Use Jinja Variable (requires MAAS metadata working)**:
```bash
# Update cloud-init template to use public_ipv4 variable
sudo tee /etc/cloud/templates/hosts.debian.tmpl <<'EOF'
## template:jinja
{{public_ipv4}} {{fqdn}} {{hostname}}
::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF
```

**Option C: Disable cloud-init manage_etc_hosts**:
```bash
# Edit cloud-init config
sudo nano /etc/cloud/cloud.cfg
# Change: manage_etc_hosts: true
# To:     manage_etc_hosts: false
```

**Recommendation**: Use Option A (hardcode IP) for Proxmox nodes since IP addresses are static and this guarantees correct behavior regardless of MAAS metadata issues.

---

### Step 4.2: Handle MAAS/Netplan Network Configuration (CRITICAL for MAAS-deployed nodes)

**Problem**: If node deployed via MAAS, cloud-init creates netplan configuration that configures the built-in ethernet interface with the node's IP address. This creates duplicate IP situation when you also configure vmbr0 bridge.

**Detected by**:
- `/etc/netplan/50-cloud-init.yaml` exists with ethernet configuration
- `systemd-networkd` is running and managing interfaces
- Built-in ethernet has IP even though set to manual in `/etc/network/interfaces`

**Solution Options**:

**Option A: Unplug built-in ethernet cable (SIMPLEST)**:
```bash
# Physically unplug the 1GbE cable from built-in ethernet port
# This prevents MAAS netplan from configuring it
# Result: Clean single-IP configuration on vmbr0 only
```

**Option B: Disable systemd-networkd and mask wait-online**:
```bash
# Disable systemd-networkd (we use ifupdown for networking)
systemctl disable systemd-networkd
systemctl mask systemd-networkd-wait-online.service

# Note: MAAS will re-enable on next cloud-init run
# Only effective combined with unplugging cable
```

**Option C: Update MAAS to configure USB adapter instead (LONG-TERM)**:
- In MAAS UI, change network interface configuration
- Configure USB adapter MAC instead of built-in ethernet MAC
- MAAS will then manage the USB adapter directly
- Most consistent but requires MAAS reconfiguration

**Recommendation for MAAS nodes**: Use **Option A (unplug cable)** - simplest and most reliable. Built-in ethernet becomes unused backup interface.

---

### Step 4.3: Fix Current /etc/hosts File (Safety Measure)

**Purpose**: Ensure hostname resolves to actual IP immediately (cloud-init will regenerate from template on next boot)

**Note**: If you fixed the cloud-init template in Step 4.1, /etc/hosts will be automatically regenerated correctly on next boot. This step provides immediate fix and serves as safety verification.

**Commands**:
```bash
# Backup current hosts file
cp /etc/hosts /etc/hosts.backup.$(date +%Y%m%d_%H%M%S)

# Create new /etc/hosts
sudo tee /etc/hosts <<EOF
127.0.0.1 localhost
::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters

# Proxmox cluster nodes (adjust for your cluster)
192.168.4.122  pve.maas pve
192.168.4.19   chief-horse.maas chief-horse
192.168.4.172  fun-bedbug.maas fun-bedbug
192.168.4.175  pumped-piglet.maas pumped-piglet
EOF
```

**Verification**:
```bash
# Verify hostname resolves correctly
hostname -i  # Should return actual IP (e.g., 192.168.4.175), NOT 127.0.1.1
hostname -f  # Should return FQDN (e.g., pumped-piglet.maas)

# Check for pmxcfs errors
journalctl -u pmxcfs --since '1 minute ago' | grep -i 'unable to resolve'
```

**Success Criteria**:
- ✅ `hostname -i` returns non-loopback IP
- ✅ `hostname -f` returns FQDN
- ✅ No pmxcfs hostname resolution errors in logs

**Why This is Critical**: Without this fix, cloud-init will reset /etc/hosts to use 127.0.1.1 on every reboot, causing pmxcfs to fail and breaking cluster membership.

---

## Phase 5: Apply Network Configuration

### Step 5.1: Validate Configuration Syntax

**Purpose**: Catch syntax errors before applying

**Commands**:
```bash
# Check for syntax errors
cat /etc/network/interfaces

# Verify interface names match
ip link show | grep -E "(eno1|enx)"
```

**Common Mistakes**:
- Typo in interface name (e.g., `enx803f5df8d628` vs `enx803f5df8d629`)
- Missing `auto` directive
- Wrong IP address format
- Missing gateway

---

### Step 5.2: Apply Network Changes

**Method 1: Using ifreload (Recommended - No Reboot)**

**WARNING**: This may briefly interrupt network connectivity. Have console access available.

```bash
# Apply new configuration
ifreload -a

# Verify vmbr0 came up
ip addr show vmbr0

# Check routing
ip route show
```

**Method 2: Reboot (Safer for Remote Access)**

```bash
# Reboot to apply changes
reboot

# After reboot, verify configuration
ip addr show vmbr0
ip route show
```

---

### Step 5.3: Verify Network Connectivity

**Purpose**: Ensure network is working after configuration change

**Commands**:
```bash
# Check vmbr0 has IP address
ip addr show vmbr0 | grep "inet "

# Check routing table
ip route show

# Verify gateway reachable
ping -c 4 192.168.4.1

# Test DNS (if applicable)
ping -c 4 8.8.8.8

# Verify cluster connectivity (if in cluster)
ping -c 4 192.168.4.122  # pve.maas
ping -c 4 192.168.4.19   # chief-horse
```

**Success Criteria**:
- ✅ vmbr0 has correct IP address
- ✅ Default route via gateway present
- ✅ Gateway reachable
- ✅ Other cluster nodes reachable

---

## Phase 6: Cluster Verification (If in Cluster)

### Step 6.1: Verify Cluster Membership

**Purpose**: Ensure cluster communication working over new network path

**Commands**:
```bash
# Check cluster status
pvecm status

# Verify corosync connectivity
corosync-cfgtool -s

# Check cluster filesystem
ls -la /etc/pve/

# Verify pve-cluster service
systemctl status pve-cluster
```

**Expected Results**:
- Cluster status: Quorate
- Node appears in member list
- /etc/pve/ filesystem accessible
- pve-cluster service: active (running)

**If Cluster Issues**:
```bash
# Check corosync logs
journalctl -u corosync --since "5 minutes ago"

# Check pve-cluster logs
journalctl -u pve-cluster --since "5 minutes ago"

# Verify hostname resolution
hostname -i  # Must NOT be 127.0.1.1
```

---

### Step 6.2: Verify Web GUI Access

**Purpose**: Confirm Proxmox web interface accessible

**Commands**:
```bash
# Check pveproxy service
systemctl status pveproxy

# Test local HTTPS access
curl -k https://localhost:8006
```

**Manual Browser Test**:
1. Open browser: `https://<node-ip>:8006`
2. Login with root credentials
3. Navigate: Datacenter → Nodes
4. Verify cluster view shows all nodes (if in cluster)

**Success Criteria**:
- ✅ pveproxy service running
- ✅ Web GUI loads
- ✅ Can login
- ✅ Cluster view accurate (if applicable)

---

## Phase 7: Reboot Stability Test

### Step 7.1: Test Boot Persistence

**Purpose**: Ensure configuration survives reboot

**Commands**:
```bash
# Reboot node
reboot

# Wait 2-3 minutes for boot
# Then verify from another machine or console

# After reboot, check network config
ip addr show vmbr0
ip route show

# Verify hostname resolution
hostname -i

# Check /etc/hosts not overwritten
cat /etc/hosts | grep $(hostname -s)

# Verify cluster membership (if in cluster)
pvecm status
systemctl status pve-cluster
```

**Success Criteria**:
- ✅ vmbr0 has IP address after reboot
- ✅ Routing table correct
- ✅ Hostname resolves to actual IP (not 127.0.1.1)
- ✅ /etc/hosts contains correct mappings
- ✅ Cluster membership intact (if applicable)
- ✅ Web GUI accessible

---

## Rollback Procedure

If configuration causes issues:

### Emergency Rollback (If Network Lost)

**Via Console Access**:
```bash
# Restore backup configuration
cp /etc/network/interfaces.backup.<timestamp> /etc/network/interfaces

# Restore /etc/hosts
cp /etc/hosts.backup.<timestamp> /etc/hosts

# Restart networking
systemctl restart networking

# Or reboot
reboot
```

### Partial Rollback (Network Still Works)

**Via SSH**:
```bash
# Restore old configuration
cp /etc/network/interfaces.backup.<timestamp> /etc/network/interfaces

# Apply old config
ifreload -a

# Verify connectivity restored
ping -c 4 192.168.4.1
```

---

## Common Issues and Solutions

### Issue 1: NO CARRIER After Configuration

**Cause**: Cable not connected or link down on USB adapter

**Solution**:
```bash
# Check cable connection physically
# Verify switch port enabled

# Check link status
ethtool enx<MAC> | grep "Link detected"

# If still no carrier, try:
ip link set enx<MAC> down
ip link set enx<MAC> up
```

---

### Issue 2: Hostname Resolves to 127.0.1.1

**Cause**: Cloud-init template not fixed or /etc/hosts incorrect

**Solution**:
```bash
# Fix /etc/hosts immediately
sudo tee -a /etc/hosts <<EOF
<actual-ip> $(hostname -f) $(hostname -s)
EOF

# Fix cloud-init template (see Phase 4)
# Verify
hostname -i  # Should return actual IP
```

---

### Issue 3: Cluster Membership Lost

**Cause**: Hostname resolution failure or network routing issue

**Investigation**:
```bash
# Check hostname resolution
hostname -i

# Check cluster logs
journalctl -u pve-cluster --since "10 minutes ago"
journalctl -u pmxcfs --since "10 minutes ago" | grep -i "unable to resolve"

# Check corosync
corosync-cfgtool -s
journalctl -u corosync --since "10 minutes ago"
```

**Solution**:
1. Fix hostname resolution (see Issue 2)
2. Restart pve-cluster: `systemctl restart pve-cluster`
3. Verify cluster rejoins: `pvecm status`

---

### Issue 4: Speed Negotiation Failed

**Symptoms**: Adapter at 100Mb/s or 10Mb/s instead of 2500Mb/s

**Cause**: Cable quality, switch compatibility, or autonegotiation issue

**Solution**:
```bash
# Check current speed
ethtool enx<MAC> | grep Speed

# Try better quality cable (Cat6 or Cat6a)
# Verify switch port supports 2.5GbE
# Check switch configuration

# Force speed (last resort)
ethtool -s enx<MAC> speed 2500 duplex full autoneg on
```

---

## Validation Checklist

### Network Configuration
- [ ] USB 2.5GbE adapter detected and has link
- [ ] vmbr0 bridge created with USB adapter as port
- [ ] IP address correct on vmbr0
- [ ] Gateway configured and reachable
- [ ] Built-in ethernet set to manual (backup)

### Hostname Resolution
- [ ] `hostname -i` returns actual IP (not 127.0.1.1)
- [ ] `hostname -f` returns FQDN
- [ ] /etc/hosts maps hostname to actual IP
- [ ] Cloud-init template uses {{public_ipv4}}
- [ ] No pmxcfs hostname resolution errors

### Cluster (If Applicable)
- [ ] Node appears in `pvecm status`
- [ ] Cluster is quorate
- [ ] Corosync communication working
- [ ] /etc/pve/ filesystem accessible
- [ ] pve-cluster service active

### Services
- [ ] pveproxy service running
- [ ] Web GUI accessible
- [ ] No systemd degraded state
- [ ] All expected services running

### Persistence
- [ ] Configuration survives reboot
- [ ] vmbr0 comes up automatically
- [ ] Hostname resolution persists
- [ ] Cluster rejoins after reboot

---

## Performance Verification

**Check Link Speed**:
```bash
ethtool enx<MAC> | grep Speed
# Expected: Speed: 2500Mb/s
```

**Test Network Throughput** (optional):
```bash
# Install iperf3 if not present
apt-get install iperf3

# On another cluster node (server mode)
iperf3 -s

# On this node (client mode)
iperf3 -c <other-node-ip>
# Expected: ~2.3 Gbits/sec (2500Mb/s minus overhead)
```

---

## Related Documentation

- [2.5GbE Network Migration Guide](../../proxmox/guides/2.5gbe-migration.md) - Original migration procedure
- [Proxmox Cluster Node Addition](./proxmox-cluster-node-addition.md) - Adding nodes to cluster
- [Proxmox Multi-Network DNS Split Configuration](../source/md/proxmox-multi-network-dns-split-runbook.md) - DNS configuration
- [Proxmox Infrastructure Guide](../source/md/proxmox-infrastructure-guide.md) - Overall architecture

---

## Tags

proxmox, networking, 2.5gbe, usb-adapter, bridge, vmbr0, cluster, configuration, runbook, network-migration
