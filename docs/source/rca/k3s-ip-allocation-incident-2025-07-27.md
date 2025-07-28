# Root Cause Analysis: K3s VM IP Allocation Incident

**Incident ID**: RCA-2025-07-27-001  
**Date**: July 27-28, 2025  
**Duration**: ~20 hours  
**Severity**: P1 (Complete cluster outage)  
**Status**: Resolved  
**Prepared by**: Homelab SRE Team  
**Date Prepared**: July 28, 2025  

## Executive Summary

The K3s cluster experienced a complete outage when all three VM nodes received unexpected IP addresses from MAAS DHCP, causing certificate validation failures. The incident was caused by MAAS automatically deleting dynamic host entries that had previously provided stable IP assignments, forcing VMs into the general DHCP pool where they received different IPs than expected by the cluster certificates.

## Incident Timeline (All times Pacific)

### Detection and Initial Response
- **July 27, 8:00 PM**: Two K3s nodes (`k3s-vm-pve`, `k3s-vm-still-fawn`) go offline (Grafana monitoring)
- **July 27, 8:30 PM**: Cluster degraded but functional on single node (`k3s-vm-chief-horse`)
- **July 28, 4:10 AM**: Final node (`k3s-vm-chief-horse`) goes offline - complete cluster outage
- **July 28, 8:00 AM**: Investigation begins
- **July 28, 2:00 PM**: Root cause identified as IP allocation issue
- **July 28, 3:00 PM**: Manual static IP reservations created in MAAS
- **July 28, 3:30 PM**: All nodes restored, cluster operational

### Technical Timeline from Logs
- **July 26, 8:51 AM**: Last successful lease renewal with correct IPs
- **July 27, 6:03 PM**: `k3s-vm-chief-horse` gets wrong IP `192.168.4.220`
- **July 27, 8:01 PM**: `k3s-vm-still-fawn` loses `192.168.4.236`, gets `192.168.4.221`
- **July 27, 8:01 PM**: `k3s-vm-pve` loses `192.168.4.238`, DNS entry deleted
- **July 28, 8:17 AM**: Orphan DNS records cleaned up

## Problem Statement

K3s cluster VMs configured with DHCP (`ipconfig0: ip=dhcp`) received IP addresses in the `192.168.4.220-221` range instead of their expected `192.168.4.236-238` range, causing:
1. TLS certificate validation failures (certificates bound to specific IPs)
2. Node authentication failures
3. Complete cluster outage

## Technical Analysis

### Infrastructure Configuration
- **MAAS Version**: 3.5.7-16375-g.69525c9de
- **DHCP Server**: ISC DHCP 4.4 (managed by MAAS snap)
- **Network**: 192.168.4.0/24 subnet
- **K3s Version**: Latest stable
- **VM Configuration**: Proxmox VE with cloud-init, DHCP-assigned IPs

### Expected vs Actual IP Assignments
| VM Name | MAC Address | Expected IP | Actual IP (Incident) | Current Status |
|---------|-------------|-------------|---------------------|----------------|
| k3s-vm-pve | bc:24:11:3b:7a:a7 | 192.168.4.238 | 192.168.4.222 | Reserved ✅ |
| k3s-vm-still-fawn | bc:24:11:a9:d5:8c | 192.168.4.236 | 192.168.4.221 | Reserved ✅ |
| k3s-vm-chief-horse | bc:24:11:1a:38:07 | 192.168.4.237 | 192.168.4.220 | Reserved ✅ |

## Diagnostic Investigation Process

### Step 1: DHCP Server Discovery

**Objective**: Identify what DHCP server is managing IP allocations

```bash
# First, identify if DHCP service exists on MAAS VM
ssh gshiva@192.168.4.53 "systemctl status maas-dhcpd 2>/dev/null || systemctl status isc-dhcp-server 2>/dev/null || echo 'DHCP service not found'"
# Result: DHCP service not found (service has different name)

# Search for any DHCP processes
ssh gshiva@192.168.4.53 "ps aux | grep -E '(dhcp|maas)' | grep -v grep"
```

**Key Discovery**: Found ISC DHCP server process:
```
root 806791 /snap/maas/40008/usr/sbin/dhcpd -f -4 -pf /var/snap/maas/common/maas/dhcp/dhcpd.pid -cf /var/snap/maas/common/maas/dhcpd.conf -lf /var/snap/maas/common/maas/dhcp/dhcpd.leases ens19
```

**Critical Information Extracted**:
- DHCP daemon location: `/snap/maas/40008/usr/sbin/dhcpd`
- Configuration file: `/var/snap/maas/common/maas/dhcpd.conf`
- Lease database: `/var/snap/maas/common/maas/dhcp/dhcpd.leases` ← **PRIMARY DATA SOURCE**
- PID file: `/var/snap/maas/common/maas/dhcp/dhcpd.pid`

### Step 2: MAAS Service Architecture Discovery

**Objective**: Understand MAAS service structure for log analysis

```bash
# Check MAAS snap installation
ssh gshiva@192.168.4.53 "snap list | grep maas"
# Result: maas 3.5.7-16375-g.69525c9de 40008 3.5/stable canonical** -

# Identify MAAS services
ssh gshiva@192.168.4.53 "systemctl list-units | grep maas"
# OR search for snap services
ssh gshiva@192.168.4.53 "systemctl list-units | grep snap.maas"
```

**Service Discovery Result**:
- Primary service: `snap.maas.pebble` ← **PRIMARY LOG SOURCE**
- MAAS runs under snap confinement with pebble service manager

### Step 3: DHCP Lease Database Analysis

**Objective**: Find evidence of IP allocation changes

```bash
# Check DHCP leases for problematic IP range
ssh gshiva@192.168.4.53 "cat /var/snap/maas/common/maas/dhcp/dhcpd.leases | grep -A 5 -B 5 '192\.168\.4\.22[01]'"

# Look for K3s VM entries in lease database
ssh gshiva@192.168.4.53 "cat /var/snap/maas/common/maas/dhcp/dhcpd.leases | grep -A 3 -B 3 'k3s'"

# Search for dynamic host entries and deletions
ssh gshiva@192.168.4.53 "cat /var/snap/maas/common/maas/dhcp/dhcpd.leases | grep -A 2 -B 2 'deleted'"
```

**Critical Discovery in `/var/snap/maas/common/maas/dhcp/dhcpd.leases`**:
```
host bc-24-11-3b-7a-a7 {
  dynamic;
  hardware ethernet bc:24:11:3b:7a:a7;
  fixed-address 192.168.4.236;
}
host bc-24-11-3b-7a-a7 {
  dynamic;
  deleted;  ← Evidence of dynamic entry deletion
}
```

### Step 4: MAAS Event Log Analysis

**Objective**: Find timeline of IP allocation events

```bash
# Check MAAS service logs (discovered service name from Step 2)
ssh gshiva@192.168.4.53 "journalctl -u snap.maas.pebble --since '48 hours ago' | grep -E 'k3s.*vm'"

# Search for specific IP allocation changes
ssh gshiva@192.168.4.53 "journalctl -u snap.maas.pebble --since '24 hours ago' | grep -E 'k3s.*vm.*(22[01]|23[6-8])'"

# Look for DHCP lease events
ssh gshiva@192.168.4.53 "journalctl -u snap.maas.pebble --since '24 hours ago' | grep -E '(lease|hostname.*IP)'"
```

### Step 5: MAAS Configuration Analysis

**Objective**: Understand DHCP configuration and subnet management

```bash
# Attempt to read DHCP configuration (discovered path from Step 1)
ssh gshiva@192.168.4.53 "cat /var/snap/maas/common/maas/dhcpd.conf"
# Result: Permission denied (root access required)

# Check file permissions
ssh gshiva@192.168.4.53 "ls -la /var/snap/maas/common/maas/dhcpd.conf"
# Result: -rw-r----- 1 root root (requires sudo)

# Use MAAS CLI for subnet information (API approach)
ssh gshiva@192.168.4.53 "maas admin subnets read"
# Note: Requires MAAS admin credentials and proper CLI setup
```

**MAAS CLI Discovery Process**:
The `maas admin subnets read` command was identified through:
1. MAAS documentation references
2. Standard MAAS administrative commands
3. API endpoint exploration

### Step 6: File System Exploration for MAAS Snap

**Objective**: Understand MAAS snap directory structure

```bash
# Explore MAAS snap directory structure
ssh gshiva@192.168.4.53 "find /var/snap/maas -type d -name '*dhcp*' 2>/dev/null"
ssh gshiva@192.168.4.53 "find /var/snap/maas -name '*.conf' 2>/dev/null | head -10"
ssh gshiva@192.168.4.53 "find /var/snap/maas -name '*.log' -type f 2>/dev/null | head -10"

# Check MAAS common directory structure
ssh gshiva@192.168.4.53 "ls -la /var/snap/maas/common/"
```

**Key Directory Structure Discovered**:
```
/var/snap/maas/common/maas/
├── dhcp/
│   ├── dhcpd.conf      ← DHCP configuration
│   ├── dhcpd.leases    ← DHCP lease database (primary source)
│   ├── dhcpd.pid       ← Process ID file
│   └── dhcpd6.conf     ← IPv6 DHCP config
└── [other MAAS files]
```

## Discovery Methodology Summary

### Critical Files and Their Discovery Process

1. **`/var/snap/maas/common/maas/dhcp/dhcpd.leases`**
   - **Discovery**: Process command line analysis (`ps aux | grep dhcp`)
   - **Purpose**: DHCP lease database with historical IP assignments
   - **Key Evidence**: Dynamic host entries and deletion records

2. **`/var/snap/maas/common/maas/dhcpd.conf`**
   - **Discovery**: Process command line analysis (dhcpd `-cf` parameter)
   - **Purpose**: DHCP server configuration
   - **Access**: Requires root privileges

3. **Service: `snap.maas.pebble`**
   - **Discovery**: `systemctl list-units | grep snap.maas`
   - **Purpose**: Primary MAAS service for logging
   - **Log Access**: `journalctl -u snap.maas.pebble`

4. **Command: `maas admin subnets read`**
   - **Discovery**: MAAS CLI documentation and API exploration
   - **Purpose**: Subnet configuration and IP range management
   - **Requirement**: MAAS admin credentials

### Official Documentation References

- **MAAS DHCP Configuration**: [https://maas.io/docs/how-to-enable-dhcp](https://maas.io/docs/how-to-enable-dhcp)
- **MAAS CLI Reference**: [https://maas.io/docs/maas-cli](https://maas.io/docs/maas-cli)
- **MAAS API Documentation**: [https://maas.io/docs/api](https://maas.io/docs/api)
- **MAAS Snap Documentation**: [https://snapcraft.io/maas](https://snapcraft.io/maas)
- **ISC DHCP Configuration**: [https://kb.isc.org/docs/isc-dhcp-44-manual-pages-dhcpdconf](https://kb.isc.org/docs/isc-dhcp-44-manual-pages-dhcpdconf)
- **MAAS IP Management**: [https://maas.io/docs/how-to-manage-ip-addresses](https://maas.io/docs/how-to-manage-ip-addresses)

## Root Cause Analysis

### Immediate Cause
MAAS deleted dynamic host entries for K3s VMs, forcing them to receive new IP addresses from the general DHCP pool instead of their previous consistent assignments.

### 5 Why Analysis

**1. Why did the K3s cluster go offline?**
- Because K3s nodes could not authenticate with each other due to TLS certificate validation failures.

**2. Why did TLS certificate validation fail?**  
- Because the K3s nodes received different IP addresses (192.168.4.220-222) than what their certificates were issued for (192.168.4.236-238).

**3. Why did the nodes receive different IP addresses?**
- Because MAAS deleted the dynamic host entries that had been providing consistent IP assignments, forcing the VMs back into the general DHCP pool.

**4. Why did MAAS delete the dynamic host entries?**
- Because MAAS performs automatic cleanup of dynamic entries during network service operations, likely triggered by the MetalLB configuration change and subsequent network service restarts.

**5. Why were the VMs dependent on dynamic host entries instead of static reservations?**
- Because the infrastructure was not properly configured with explicit static IP reservations in MAAS, and the VMs were configured with `ipconfig0: ip=dhcp`, relying on MAAS's implicit dynamic host behavior.

### Contributing Factors

1. **Configuration Gap**: VMs configured for DHCP without explicit static reservations
2. **Assumption Risk**: Assuming MAAS dynamic entries were permanent
3. **Network Changes**: MetalLB reconfiguration may have triggered MAAS service operations
4. **Monitoring Gap**: No alerting on K3s node IP address changes
5. **Documentation Gap**: Dynamic host entry behavior not well understood

### MAAS Dynamic Host Entry Behavior

**How Dynamic Entries Work:**
- MAAS creates temporary "host" entries when machines consistently request the same IP
- Format: `host <mac> { dynamic; hardware ethernet <mac>; fixed-address <ip>; }`
- Provides pseudo-static behavior without explicit reservations

**Deletion Triggers:**
- Network service restarts/reconfigurations
- MAAS maintenance operations  
- IP pool changes or conflicts
- Automatic cleanup routines
- Service upgrades or snap refreshes

## Impact Assessment

### Service Impact
- **Complete K3s cluster outage**: 20 hours
- **All GitOps services**: Offline (Flux, monitoring, applications)
- **Load balancer services**: Offline (MetalLB dependent)
- **DNS resolution**: Degraded (some services)

### Business Impact
- Development work blocked
- Monitoring/alerting unavailable
- Home automation services interrupted
- AI workloads (Ollama, Stable Diffusion) unavailable

## Resolution

### Immediate Fix
1. Created explicit static IP reservations in MAAS:
   - `k3s-vm-pve` → `192.168.4.238` 
   - `k3s-vm-still-fawn` → `192.168.4.236`
   - `k3s-vm-chief-horse` → `192.168.4.237`

2. Verified VM IP assignments match reservations
3. Confirmed cluster certificate validation restored
4. Validated all services operational

### Verification Commands Used
```bash
# Verify DHCP reservations active
ssh gshiva@192.168.4.53 "cat /var/snap/maas/common/maas/dhcp/dhcpd.leases | grep 'k3s-vm' -A 5"

# Confirm VM IPs via Proxmox
ssh root@pve "qm guest cmd 107 network-get-interfaces"

# Test K3s cluster connectivity
export KUBECONFIG=~/kubeconfig && kubectl get nodes -o wide
```

## Prevention and Mitigation

### Immediate Actions (Completed ✅)
1. ✅ Static IP reservations created for all K3s VMs
2. ✅ Verified cluster stability post-resolution  
3. ✅ Updated documentation with reservation requirements

### Short-term Improvements (30 days)

#### 1. Monitoring and Alerting
```yaml
# Add Prometheus rule for IP change detection
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: k3s-node-ip-monitoring
  namespace: monitoring
spec:
  groups:
  - name: k3s.infrastructure
    rules:
    - alert: K3sNodeIPChanged
      expr: changes(kube_node_info[10m]) > 0
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "K3s node IP changed - potential certificate issues"
        description: "Node {{ $labels.node }} IP changed, may cause certificate validation failures"
```

#### 2. Infrastructure as Code
```python
# Add to proxmox/homelab/src/homelab/maas_client.py
class MAASReservationManager:
    def ensure_static_reservation(self, mac_address: str, ip_address: str, hostname: str):
        """Ensure static IP reservation exists in MAAS"""
        # Implementation for automated reservation management
        pass
        
    def validate_reservations(self, expected_mappings: Dict[str, str]):
        """Validate all expected reservations are active"""
        pass
```

#### 3. Configuration Management
Consider static IP configuration in Proxmox cloud-init:
```yaml
# Alternative approach - static IPs in VM config
ipconfig0: ip=192.168.4.238/24,gw=192.168.4.1
```

### Long-term Improvements (90 days)

#### 1. Network Architecture Review
- Evaluate subnet segmentation for critical services
- Consider dedicated management network for K3s
- Review DHCP vs static IP strategy

#### 2. Automated Testing
```bash
#!/bin/bash
# Integration test for IP stability
test_ip_consistency() {
    for vm in k3s-vm-pve k3s-vm-still-fawn k3s-vm-chief-horse; do
        expected_ip=$(maas admin machines read hostname=$vm | jq -r '.ip_addresses[0]')
        actual_ip=$(ssh root@proxmox "qm guest cmd $vm network-get-interfaces" | jq -r '.[1].ip_addresses[0].ip_address')
        [[ "$expected_ip" == "$actual_ip" ]] || echo "ERROR: $vm IP mismatch"
    done
}
```

#### 3. Disaster Recovery
- Document cluster certificate regeneration procedures
- Create automation for certificate updates on IP changes
- Implement backup/restore procedures for MAAS configuration

## Lessons Learned

### What Went Well
1. **Comprehensive logging**: MAAS provided detailed logs for root cause analysis
2. **Monitoring detection**: Grafana monitoring detected node failures promptly  
3. **Quick resolution**: Once root cause identified, fix was straightforward
4. **Documentation**: Incident well-documented for future reference

### What Could Be Improved
1. **Proactive monitoring**: Should have monitored IP assignments, not just node status
2. **Configuration management**: Should have used explicit reservations from the start
3. **Change management**: MetalLB changes should have included IP dependency review
4. **Runbook**: Need documented procedures for DHCP troubleshooting

### Knowledge Gaps Addressed
1. **MAAS dynamic entries**: Now understand temporary nature and deletion triggers
2. **K3s IP dependencies**: Certificates and cluster auth tied to specific IPs
3. **Change correlation**: Network changes can have delayed, indirect effects

## Appendix

### A. Diagnostic Command Reference
```bash
# DHCP server identification
ps aux | grep dhcp | grep -v grep

# DHCP lease analysis  
cat /var/snap/maas/common/maas/dhcp/dhcpd.leases | grep -E "(host|deleted|fixed-address)"

# MAAS event monitoring
journalctl -u snap.maas.pebble --since '24 hours ago' | grep -E 'hostname.*IP'

# VM network state
qm guest cmd <vmid> network-get-interfaces

# K3s cluster validation
kubectl get nodes -o wide
kubectl get certificatesigningrequests
systemctl status k3s  # on nodes
```

### B. MAAS Configuration Validation
```bash
# Check static reservations (requires MAAS CLI setup)
maas admin subnets read | jq '.[] | select(.name=="192.168.4.0/24") | .ip_ranges'

# Verify DHCP configuration (requires root access)
sudo cat /var/snap/maas/common/maas/dhcpd.conf | grep -A 5 -B 5 "k3s-vm"

# Check MAAS snap services
systemctl list-units | grep snap.maas
```

### C. File System Layout Reference
```
MAAS Snap Structure:
/var/snap/maas/
├── common/maas/
│   ├── dhcp/
│   │   ├── dhcpd.conf      ← DHCP configuration
│   │   ├── dhcpd.leases    ← Lease database (primary source)
│   │   └── dhcpd.pid       ← Process ID
│   ├── bind/               ← DNS configuration  
│   └── proxy/              ← Proxy configuration
└── current/                ← Current snap version files

Log Sources:
- journalctl -u snap.maas.pebble  ← Primary MAAS logs
- /var/snap/maas/common/maas/dhcp/dhcpd.leases  ← DHCP lease history
```

### D. Related Documentation
- [MAAS DHCP Configuration Guide](../guides/maas-dhcp-guide.md)
- [K3s Certificate Management](../guides/k3s-cert-management.md)  
- [Network Troubleshooting Runbook](../runbooks/network-troubleshooting.md)

---

**Document Status**: Final  
**Next Review Date**: August 28, 2025  
**Incident Closed**: July 28, 2025 15:30 PT  
**Total Outage Time**: 19 hours 30 minutes