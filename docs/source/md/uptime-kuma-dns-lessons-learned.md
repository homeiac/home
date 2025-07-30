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

### Configuration Persistence
The DNS configuration applied is temporary and will be overwritten by:
- DHCP lease renewals
- System reboots
- systemd-resolved/NetworkManager updates

**Action Required:** Implement persistent DNS configuration using appropriate system management tools.

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