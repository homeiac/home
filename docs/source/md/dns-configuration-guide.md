# DNS Configuration Guide for Homelab Docker Containers

## Overview

This guide documents the DNS configuration required for Docker containers running in LXC containers within the homelab to properly resolve both `.maas` and `.homelab` domains.

## Problem Summary

Docker containers running inside LXC containers were unable to resolve:
- `.maas` domain entries (managed by MAAS DNS at 192.168.4.53)
- `.homelab` domain entries (managed by OPNsense Unbound DNS at 192.168.4.1)

The root cause was incorrect DNS server configuration and missing search domains in the Docker containers.

## Working DNS Configuration

### Required DNS Servers (in order of priority)
1. **192.168.4.1** - OPNsense Unbound DNS (contains `.homelab` domain overrides)
2. **2600:1700:7270:933f:be24:11ff:fed5:6f30** - IPv6 DNS server (ISP provided)
3. **192.168.4.53** - MAAS DNS server (contains `.maas` domain entries)

### Required Search Domains
- `maas.` - For resolving MAAS-managed hostnames
- `homelab.` - For resolving homelab service domains

## Implementation

### ✅ Persistent Configuration (Recommended)

The following method ensures DNS configuration persists across reboots and DHCP renewals:

#### 1. Docker Daemon Configuration

Create `/etc/docker/daemon.json` in the LXC container:

```json
{
  "dns": [
    "192.168.4.1",
    "2600:1700:7270:933f:be24:11ff:fed5:6f30",
    "192.168.4.53"
  ],
  "dns-search": [
    "maas.",
    "homelab."
  ]
}
```

#### 2. DHCP Exit Hook (Critical for Persistence)

Create `/etc/dhcp/dhclient-exit-hooks.d/homelab-dns`:

```bash
#!/bin/bash
# Homelab DNS configuration override
# Ensures correct DNS servers and search domains

if [ "$reason" = "BOUND" ] || [ "$reason" = "RENEW" ] || [ "$reason" = "REBIND" ]; then
    echo "Applying homelab DNS configuration"
    
    # Create new resolv.conf with our DNS settings
    cat > /etc/resolv.conf << RESOLV_EOF
domain maas
search maas homelab
nameserver 192.168.4.1
nameserver 2600:1700:7270:933f:be24:11ff:fed5:6f30
nameserver 192.168.4.53
RESOLV_EOF

    echo "DNS configuration applied successfully"
fi
```

#### 3. Complete Implementation Steps

```bash
# 1. Create Docker daemon configuration
cat > /etc/docker/daemon.json << EOF
{
  "dns": [
    "192.168.4.1",
    "2600:1700:7270:933f:be24:11ff:fed5:6f30",
    "192.168.4.53"
  ],
  "dns-search": [
    "maas.",
    "homelab."
  ]
}
EOF

# 2. Create DHCP exit hook for persistence
cat > /etc/dhcp/dhclient-exit-hooks.d/homelab-dns << 'EOF'
#!/bin/bash
# Homelab DNS configuration override
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

# 3. Make hook executable
chmod +x /etc/dhcp/dhclient-exit-hooks.d/homelab-dns

# 4. Force DHCP renewal to apply configuration
dhclient -r eth0 && dhclient eth0

# 5. Restart Docker to pick up new DNS settings
systemctl restart docker
```

### ⚠️ Alternative: Manual Configuration (Not Persistent)

If you need to apply DNS settings manually (will be lost on restart):

```bash
# Update resolv.conf (temporary)
cat > /etc/resolv.conf << EOF
domain maas
search maas homelab
nameserver 192.168.4.1
nameserver 2600:1700:7270:933f:be24:11ff:fed5:6f30
nameserver 192.168.4.53
EOF

# Restart Docker service
systemctl restart docker
```

## Verification

### Test DNS Resolution

From within a Docker container, test resolution of both domain types:

```bash
# Test .maas domain resolution
ping -c 1 still-fawn.maas
ping -c 1 fun-bedbug.maas

# Test .homelab domain resolution
ping -c 1 ollama.app.homelab
ping -c 1 stable-diffusion.app.homelab

# Check DNS configuration
cat /etc/resolv.conf
```

Expected output should show:
- `.maas` domains resolving to their respective IP addresses
- `.homelab` domains resolving to configured IP addresses (e.g., 192.168.4.80)
- resolv.conf containing all three nameservers and both search domains

### Expected Results

✅ **Working resolution examples:**
- `still-fawn.maas` → `192.168.4.17`
- `fun-bedbug.maas` → `192.168.4.172`
- `ollama.app.homelab` → `192.168.4.80`
- `stable-diffusion.app.homelab` → `192.168.4.80`

## DNS Server Roles

### 192.168.4.1 (OPNsense Unbound DNS)
- **Primary DNS server** for homelab
- Contains DNS overrides for `.homelab` domain services
- Forwards other requests to upstream DNS servers
- **Critical for**: Resolving homelab service names like `ollama.app.homelab`

### 192.168.4.53 (MAAS DNS)
- **MAAS-managed DNS server**
- Contains entries for MAAS-managed nodes (`.maas` domain)
- **Critical for**: Resolving Proxmox nodes and MAAS-managed systems
- **Should forward**: Non-MAAS requests to OPNsense DNS (192.168.4.1)

### IPv6 DNS Server (ISP Provided)
- **Fallback DNS server** for external resolution
- May contain some homelab entries depending on ISP configuration
- **Role**: External internet resolution and IPv6 domains

## Troubleshooting

### Common Issues

1. **Only .maas domains work**: Missing OPNsense DNS server (192.168.4.1) as primary
2. **Only external domains work**: Missing search domains in configuration
3. **No domains work**: Docker daemon not restarted after configuration change
4. **Intermittent failures**: DNS server order incorrect or IPv6 connectivity issues

### Diagnostic Commands

```bash
# Check Docker daemon DNS configuration
docker inspect container-name | jq '.[0].HostConfig.Dns'

# Check container resolv.conf
docker exec container-name cat /etc/resolv.conf

# Test specific DNS server
docker exec container-name nslookup ollama.app.homelab 192.168.4.1

# Check Docker daemon status
systemctl status docker
```

## Automation Script

### Persistent DNS Configuration Script

Create `/usr/local/bin/configure-homelab-dns.sh`:

```bash
#!/bin/bash
# Configure persistent DNS for homelab Docker containers
# This script implements the DHCP hook method for full persistence

set -e

echo "Configuring persistent DNS for homelab Docker containers..."

# 1. Create Docker daemon configuration
echo "Creating Docker daemon DNS configuration..."
cat > /etc/docker/daemon.json << EOF
{
  "dns": [
    "192.168.4.1",
    "2600:1700:7270:933f:be24:11ff:fed5:6f30",
    "192.168.4.53"
  ],
  "dns-search": [
    "maas.",
    "homelab."
  ]
}
EOF

# 2. Create DHCP exit hook for persistence
echo "Creating DHCP exit hook for DNS persistence..."
cat > /etc/dhcp/dhclient-exit-hooks.d/homelab-dns << 'EOF'
#!/bin/bash
# Homelab DNS configuration override
# Ensures correct DNS servers and search domains persist across DHCP renewals

if [ "$reason" = "BOUND" ] || [ "$reason" = "RENEW" ] || [ "$reason" = "REBIND" ]; then
    echo "Applying homelab DNS configuration"
    
    # Create new resolv.conf with our DNS settings
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

# 3. Make hook executable
chmod +x /etc/dhcp/dhclient-exit-hooks.d/homelab-dns

# 4. Apply DNS configuration immediately
echo "Applying DNS configuration..."
dhclient -r eth0 && dhclient eth0

# 5. Restart Docker to pick up new settings
echo "Restarting Docker service..."
systemctl restart docker

echo ""
echo "✅ Persistent DNS configuration complete!"
echo "Configuration will survive reboots, DHCP renewals, and container restarts."
echo ""
echo "Test with: docker exec container-name ping ollama.app.homelab"
```

### Installation and Usage

```bash
# Create and install the script
chmod +x /usr/local/bin/configure-homelab-dns.sh

# Run the script
/usr/local/bin/configure-homelab-dns.sh

# Verify configuration
cat /etc/resolv.conf
docker exec uptime-kuma ping -c 1 ollama.app.homelab
```

## Related Documentation

- [Monitoring and Alerting Guide](monitoring-alerting-guide.md) - Configure Uptime Kuma monitoring
- [Proxmox Guides](../../../proxmox/guides/) - LXC container management
- [GitOps Configuration](../../../gitops/clusters/homelab/) - Kubernetes DNS configuration

## Notes

- This configuration was tested on Ubuntu LXC containers running Docker
- DNS server IPv6 address may vary based on ISP configuration
- Search domain order matters - `maas.` should come before `homelab.`
- Always test DNS resolution after making changes
- Consider implementing this configuration in container creation automation

## Security Considerations

- DNS servers are internal homelab infrastructure
- No external DNS traffic should go to MAAS DNS server
- OPNsense Unbound configuration should have appropriate filtering
- Monitor DNS query logs for unusual activity