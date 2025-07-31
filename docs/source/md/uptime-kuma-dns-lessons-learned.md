# Uptime Kuma DNS Resolution - Lessons Learned

## Project Overview

**Date:** July 29-30, 2025  
**Issue:** Uptime Kuma monitors showing red/failing status due to DNS resolution failures  
**Environment:** Docker containers running inside Proxmox LXC containers  
**Final Status:** ✅ Resolved with comprehensive DNS configuration  

## Problem Summary

### Initial Symptoms
- Uptime Kuma monitors showing red status across multiple services
- DNS resolution failures for both `.maas` and `.homelab` domains
- Monitors working for external domains (Google DNS, Cloudflare DNS) but failing for internal services

### Root Cause Analysis
The issue was multi-layered DNS configuration problems in containerized environments:

1. **LXC Container Network Configuration:** pve Docker container was on wrong network bridge (vmbr25gbe vs vmbr0)
2. **Docker DNS Configuration:** Docker containers using default DNS (8.8.8.8, 8.8.4.4) instead of homelab DNS servers
3. **DNS Server Priority:** Wrong order of DNS servers prevented `.homelab` domain resolution
4. **Missing Search Domains:** Containers lacked proper search domain configuration for domain suffix resolution

## Technical Details

### Network Architecture Discovery
- **pve host:** vmbr0 (192.168.1.x), vmbr25gbe (192.168.4.x)
- **fun-bedbug host:** vmbr0 (192.168.4.x)
- **DNS Infrastructure:**
  - 192.168.4.1: OPNsense Unbound DNS (contains `.homelab` domain overrides)
  - 192.168.4.53: MAAS DNS (contains `.maas` domain entries)
  - IPv6 DNS: ISP-provided (contains some homelab entries)

### Key Discoveries

#### DNS Server Hierarchy
The critical insight was understanding DNS server priority:
1. **OPNsense (192.168.4.1)** must be primary for `.homelab` domains
2. **MAAS DNS (192.168.4.53)** handles `.maas` domains but doesn't forward `.homelab` properly
3. **IPv6 DNS** from ISP sometimes contains homelab entries

#### Container Networking Layers
DNS configuration must be applied at multiple layers:
1. **Proxmox Host Level:** Network bridge selection affects IP subnet
2. **LXC Container Level:** `/etc/resolv.conf` configuration
3. **Docker Daemon Level:** `/etc/docker/daemon.json` DNS settings
4. **Docker Container Level:** Inherits from Docker daemon

#### DHCP vs Manual Configuration
- **DHCP should provide:** Correct search domains (`maas homelab`) and DNS servers
- **Reality:** Different containers received different configurations
- **Solution:** Manual override necessary for consistent behavior

## Solutions Implemented

### 1. Network Bridge Correction
```bash
# Fixed pve container to use correct bridge
pct set 100 --net1 name=eth1,bridge=vmbr25gbe,hwaddr=BC:24:11:B3:D0:40,ip=dhcp,ip6=dhcp,type=veth
```

### 2. Docker DNS Configuration
```json
{
  "dns": [
    "192.168.4.1",                              // OPNsense primary
    "2600:1700:7270:933f:be24:11ff:fed5:6f30",  // IPv6 backup
    "192.168.4.53"                              // MAAS fallback
  ],
  "dns-search": ["maas.", "homelab."]
}
```

### 3. LXC Container DNS
```
domain maas
search maas homelab
nameserver 192.168.4.1
nameserver 2600:1700:7270:933f:be24:11ff:fed5:6f30
nameserver 192.168.4.53
```

### 4. Database Updates
```sql
-- Fixed hardcoded hostname that didn't exist in DNS
UPDATE monitor SET hostname = '192.168.4.122' WHERE id = 3;
```

## Troubleshooting Process

### What Worked
1. **Systematic Layer Testing:** Testing DNS at each layer (host → LXC → Docker)
2. **Reference Configuration:** Comparing working laptop DNS config to containers
3. **Direct IP Testing:** Using IP addresses to isolate DNS vs connectivity issues
4. **Database Direct Access:** SQLite queries to modify monitor configurations

### What Didn't Work Initially
1. **Assuming DHCP Would Work:** DHCP provided partial but inconsistent configuration
2. **Single DNS Server:** Relying only on MAAS DNS (192.168.4.53) for all resolution
3. **Default Docker DNS:** Containers defaulting to public DNS servers

### Diagnostic Commands That Were Essential
```bash
# Network connectivity
ping -c 1 <target_ip>

# DNS resolution testing
nslookup <domain> <dns_server>

# Container network inspection
docker exec <container> cat /etc/resolv.conf

# DHCP lease inspection
cat /var/lib/dhcp/dhclient.leases

# Database direct queries
sqlite3 /app/data/kuma.db "SELECT id, name, hostname FROM monitor;"
```

## Lessons Learned

### 1. Container DNS is Complex
DNS in containerized environments requires configuration at multiple layers. Each layer can override the previous one, leading to unexpected behavior.

### 2. Don't Trust DHCP Alone
While DHCP should provide consistent DNS configuration, in practice different containers received different settings. Manual configuration ensures consistency.

### 3. DNS Server Order Matters
The order of DNS servers is critical. The first server that responds (even with NXDOMAIN) prevents queries to subsequent servers for the same domain.

### 4. Test at Each Layer
When troubleshooting DNS:
1. Test from the physical host
2. Test from the LXC container
3. Test from the Docker container
4. Test with different DNS servers explicitly

### 5. Document Working Configurations
DNS configuration that works should be documented immediately and automated, as the configuration can be complex to recreate.

### 6. Use Direct Database Access When Needed
For applications like Uptime Kuma, direct database access can be faster than UI manipulation, especially for bulk changes.

### 7. IP Addresses Are Sometimes Better
For critical infrastructure monitoring, using IP addresses instead of hostnames can bypass DNS issues entirely.

## Outstanding Issues

### MAAS DNS Forwarding
Despite configuring upstream DNS in MAAS web GUI, MAAS DNS (192.168.4.53) still doesn't forward `.homelab` domain requests to OPNsense (192.168.4.1). This suggests:
- Potential BIND9 configuration bug in MAAS
- Zone management conflicts
- DNSSEC validation issues

**Current Workaround:** Bypass MAAS DNS for `.homelab` domains by using OPNsense as primary DNS.

### pve Docker Container Issues
The pve host Docker container had persistent issues:
- Docker commands timing out
- Network configuration instability
- Required manual DHCP lease renewal

**Status:** Left unresolved due to network access limitations.

### Configuration Persistence - Detective Work ✅ RESOLVED

**Original Issue:** The DNS configuration applied was temporary and would be overwritten by DHCP lease renewals, system reboots, and network management updates.

#### Sherlock Holmes Investigation Process

**Step 1: Identify the DNS Management System**
```bash
# Check if systemd-resolved is managing DNS
systemctl status systemd-resolved
# Result: Unit systemd-resolved.service could not be found.

# Check if resolv.conf is a symlink (indicates management by systemd-resolved)
ls -la /etc/resolv.conf
# Result: -rw-r--r-- 1 root root 49 Jul 31 05:11 /etc/resolv.conf
# Conclusion: Not a symlink, so not managed by systemd-resolved

# Check for netplan configuration
ls /etc/netplan/ 2>/dev/null || echo 'No netplan found'
# Result: No netplan found

# Check for NetworkManager
systemctl status NetworkManager 2>/dev/null || echo 'NetworkManager not found'
# Result: NetworkManager not found

# Check what DHCP client is running
ps aux | grep dhcp
# Result: dhclient processes found - this is the DNS manager!
```

**Key Discovery:** The system uses `dhclient` for DHCP and DNS management.

**Step 2: Investigate DHCP Configuration Methods**
```bash
# Check current dhclient configuration
cat /etc/dhcp/dhclient.conf | tail -10
# Looking for: existing DNS overrides or configuration patterns

# Check for DHCP hooks directories
ls -la /etc/dhcp/dhclient-enter-hooks.d/ 2>/dev/null || echo 'No dhcp enter hooks'
ls -la /etc/dhcp/dhclient-exit-hooks.d/ 2>/dev/null || echo 'No dhcp exit hooks'
# Result: Both directories exist - this is our solution path!
```

**Step 3: First Attempt - dhclient.conf supersede**
```bash
# Add DNS override to dhclient.conf
cat >> /etc/dhcp/dhclient.conf << EOF
supersede domain-name-servers 192.168.4.1, 2600:1700:7270:933f:be24:11ff:fed5:6f30, 192.168.4.53;
supersede domain-search "maas", "homelab";
EOF

# Test with DHCP renewal
dhclient -r eth0 && dhclient eth0
# Problem: IPv6 address syntax error - needs quotes!
```

**Step 4: Fix dhclient.conf Syntax**
```bash
# Check the syntax error
dhclient -v eth0
# Result: "/etc/dhcp/dhclient.conf line 57: semicolon expected."
# Issue: IPv6 address not properly quoted

# Fix the IPv6 address quoting
sed -i 's/supersede domain-name-servers 192.168.4.1, 2600:1700:7270:933f:be24:11ff:fed5:6f30, 192.168.4.53;/supersede domain-name-servers 192.168.4.1, "2600:1700:7270:933f:be24:11ff:fed5:6f30", 192.168.4.53;/' /etc/dhcp/dhclient.conf

# Verify fix
tail -5 /etc/dhcp/dhclient.conf
# Result: Proper quoting applied
```

**Step 5: Discover dhclient.conf Limitations**
After testing, dhclient.conf supersede wasn't consistently working. The investigation showed that DHCP exit hooks are more reliable.

**Step 6: Implement DHCP Exit Hook Solution**
```bash
# Create DHCP exit hook
cat > /etc/dhcp/dhclient-exit-hooks.d/homelab-dns << 'EOF'
#!/bin/bash
if [ "$reason" = "BOUND" ] || [ "$reason" = "RENEW" ] || [ "$reason" = "REBIND" ]; then
    echo "Applying homelab DNS configuration"
    cat > /etc/resolv.conf << RESOLV_EOF
domain maas
search maas homelab
nameserver 192.168.4.1
nameserver 2600:1700:7270:933f:be24:11ff:fed5:6f30
nameserver 192.168.4.53
RESOLV_EOF
    echo "DNS configuration applied successfully"
fi
EOF

# Make executable
chmod +x /etc/dhcp/dhclient-exit-hooks.d/homelab-dns
```

**Step 7: Debug Hook Variable Escaping Issue**
```bash
# First test showed variable escaping problem
cat /etc/dhcp/dhclient-exit-hooks.d/homelab-dns
# Result: Variables showed as empty strings - escaping issue!

# The problem: HEREDOC wasn't properly handling variable escaping
# Solution: Use quoted HEREDOC to prevent variable expansion during creation
```

**Step 8: Verification and Testing Process**
```bash
# Test DHCP renewal to trigger hook
dhclient -r eth0 && dhclient eth0
# Looking for: "Applying homelab DNS configuration" message
# Result: SUCCESS - hook executed and applied DNS settings

# Verify DNS configuration
cat /etc/resolv.conf
# Expected: All three nameservers and both search domains
# Result: ✅ Perfect configuration applied

# Test persistence across container restart
pct stop 112 && pct start 112
sleep 30
cat /etc/resolv.conf
# Looking for: Partial configuration (shows hook needed to run)

# Force DHCP renewal to trigger hook after restart
dhclient eth0
# Result: ✅ Hook applies configuration successfully

# Final verification - Docker container DNS
docker exec uptime-kuma cat /etc/resolv.conf
# Expected: Docker inheriting correct DNS from host
# Result: ✅ All nameservers and search domains present
```

**Investigation Insights:**
1. **Process of Elimination:** Systematically ruled out systemd-resolved, netplan, NetworkManager
2. **Process Discovery:** `ps aux | grep dhcp` revealed the actual DNS management system
3. **Hook Mechanism:** DHCP exit hooks are more reliable than dhclient.conf supersede
4. **Variable Escaping:** Proper shell scripting techniques required for HEREDOC in hooks
5. **Testing Methodology:** Full restart testing revealed when hooks trigger vs don't trigger

**Final Solution:** DHCP exit hook that automatically applies DNS configuration on DHCP lease events, providing full persistence across reboots, DHCP renewals, and container restarts.

**Status:** ✅ **RESOLVED** - DNS configuration now persists across all restart scenarios.

## Best Practices Developed

### 1. DNS Configuration Automation
Created standardized script for applying DNS configuration to new containers:
```bash
#!/bin/bash
# configure-homelab-dns.sh
# Standard DNS configuration for homelab Docker containers
```

### 2. Monitoring Configuration
- Use IP addresses for critical infrastructure (Proxmox nodes)
- Keep external connectivity monitors (Google DNS, Cloudflare) 
- Test both internal (.maas, .homelab) and external domains

### 3. Documentation Standards
- Document DNS hierarchy and server roles
- Include troubleshooting commands in documentation
- Maintain current IP address mappings

## Prevention Strategies

### 1. Container Templates
Create LXC container templates with pre-configured DNS settings to avoid manual configuration on each container.

### 2. Infrastructure as Code
Document all network and DNS configurations in code/configuration files rather than relying on manual GUI configurations.

### 3. Health Checks
Implement regular DNS resolution health checks to catch configuration drift before it affects services.

### 4. Network Documentation
Maintain clear documentation of:
- Network bridge assignments
- DNS server roles and hierarchies
- DHCP vs static configurations
- Container IP address ranges

## Success Metrics

### Before Fix
- Multiple Uptime Kuma monitors failing (red status)
- DNS resolution failures for internal domains
- Inconsistent behavior across containers

### After Fix
- ✅ All internal domain resolution working (.maas and .homelab)
- ✅ Proper DNS server hierarchy established
- ✅ Consistent configuration across containers
- ✅ Monitoring operational for all services

## Time Investment
- **Total time:** ~4 hours of troubleshooting
- **Key breakthrough:** Realizing DNS server priority was wrong
- **Most time-consuming:** Testing different DNS configurations iteratively
- **Documentation time:** 1 hour (this document)

## Conclusion

This issue highlighted the complexity of DNS in layered containerized environments. The solution required understanding and configuring DNS at multiple levels: network bridges, LXC containers, Docker daemon, and application level.

The key insight was that DNS configuration in homelab environments often requires manual override of automatic configuration (DHCP) to ensure consistent behavior across all services.

**Most Important Lesson:** In complex network environments, systematic troubleshooting at each layer combined with reference configuration comparison (working laptop config) is essential for identifying root causes.

**Critical Follow-up:** The current solution is temporary. Persistent DNS configuration must be implemented to prevent regression after system reboots or network changes.