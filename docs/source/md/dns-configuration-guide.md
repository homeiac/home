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

### Docker Daemon Configuration

Create or update `/etc/docker/daemon.json` in the LXC container:

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

### LXC Container resolv.conf

Update `/etc/resolv.conf` in the LXC container:

```
domain maas
search maas homelab
nameserver 192.168.4.1
nameserver 2600:1700:7270:933f:be24:11ff:fed5:6f30
nameserver 192.168.4.53
```

### Applying Changes

1. **Update Docker daemon configuration**:
   ```bash
   # Create/update daemon.json
   cat > /etc/docker/daemon.json << EOF
   {
     "dns": ["192.168.4.1", "2600:1700:7270:933f:be24:11ff:fed5:6f30", "192.168.4.53"],
     "dns-search": ["maas.", "homelab."]
   }
   EOF
   ```

2. **Update LXC container resolv.conf**:
   ```bash
   # Update resolv.conf
   cat > /etc/resolv.conf << EOF
   domain maas
   search maas homelab
   nameserver 192.168.4.1
   nameserver 2600:1700:7270:933f:be24:11ff:fed5:6f30
   nameserver 192.168.4.53
   EOF
   ```

3. **Restart Docker service**:
   ```bash
   systemctl restart docker
   ```

4. **Restart affected containers**:
   ```bash
   docker restart container-name
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

Create `/usr/local/bin/configure-homelab-dns.sh`:

```bash
#!/bin/bash
# Configure DNS for homelab Docker containers

set -e

echo "Configuring Docker DNS for homelab..."

# Create Docker daemon configuration
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

# Update LXC container resolv.conf
cat > /etc/resolv.conf << EOF
domain maas
search maas homelab
nameserver 192.168.4.1
nameserver 2600:1700:7270:933f:be24:11ff:fed5:6f30
nameserver 192.168.4.53
EOF

# Restart Docker
echo "Restarting Docker service..."
systemctl restart docker

echo "DNS configuration complete!"
echo "Remember to restart your containers: docker restart container-name"
```

Make executable and run:
```bash
chmod +x /usr/local/bin/configure-homelab-dns.sh
./usr/local/bin/configure-homelab-dns.sh
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