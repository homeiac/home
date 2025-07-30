# Homelab Return Action Plan

## Overview
Action items to complete when returning home to verify and make persistent the DNS configuration fixes applied to resolve Uptime Kuma monitoring issues.

## Priority 1: Verify Current Status

### Check Uptime Kuma Status
```bash
# Access Uptime Kuma web interfaces
# fun-bedbug: http://192.168.4.223:3001
# pve: http://192.168.4.194:3001 (if container is working)

# Verify monitors are green:
# - Proxmox pve Node (should use IP 192.168.4.122)
# - Proxmox still-fawn Node
# - Proxmox fun-bedbug Node
# - Ollama GPU Server (.homelab domain)
# - Stable Diffusion WebUI (.homelab domain)
# - All other monitors
```

### Test DNS Resolution
```bash
# From fun-bedbug Docker container
ssh root@fun-bedbug.maas "pct exec 112 -- docker exec uptime-kuma ping -c 1 ollama.app.homelab"
ssh root@fun-bedbug.maas "pct exec 112 -- docker exec uptime-kuma ping -c 1 still-fawn.maas"

# Expected: Both should resolve and ping successfully
```

## Priority 2: Make DNS Configuration Persistent

### Identify DNS Management System
```bash
# On fun-bedbug LXC container
ssh root@fun-bedbug.maas "pct exec 112 -- systemctl status systemd-resolved"
ssh root@fun-bedbug.maas "pct exec 112 -- ls -la /etc/resolv.conf"
ssh root@fun-bedbug.maas "pct exec 112 -- ls /etc/netplan/"
ssh root@fun-bedbug.maas "pct exec 112 -- systemctl status NetworkManager"
```

### Apply Persistent Configuration
Based on findings above, choose appropriate method:

#### If using systemd-resolved:
```bash
ssh root@fun-bedbug.maas "pct exec 112 -- bash -c 'cat > /etc/systemd/resolved.conf << EOF
[Resolve]
DNS=192.168.4.1 2600:1700:7270:933f:be24:11ff:fed5:6f30 192.168.4.53
Domains=maas homelab
EOF'"

# Restart systemd-resolved
ssh root@fun-bedbug.maas "pct exec 112 -- systemctl restart systemd-resolved"
```

#### If using dhclient:
```bash
ssh root@fun-bedbug.maas "pct exec 112 -- bash -c 'cat >> /etc/dhcp/dhclient.conf << EOF
supersede domain-name-servers 192.168.4.1, 2600:1700:7270:933f:be24:11ff:fed5:6f30, 192.168.4.53;
supersede domain-search \"maas\", \"homelab\";
EOF'"
```

#### If using netplan:
```bash
ssh root@fun-bedbug.maas "pct exec 112 -- bash -c 'cat > /etc/netplan/99-dns-override.yaml << EOF
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: yes
      nameservers:
        addresses: [192.168.4.1, \"2600:1700:7270:933f:be24:11ff:fed5:6f30\", 192.168.4.53]
        search: [maas, homelab]
EOF'"

ssh root@fun-bedbug.maas "pct exec 112 -- netplan apply"
```

### Test Persistence
```bash
# Restart the LXC container
ssh root@fun-bedbug.maas "pct stop 112 && pct start 112"

# Wait for startup, then test DNS again
sleep 30
ssh root@fun-bedbug.maas "pct exec 112 -- docker exec uptime-kuma cat /etc/resolv.conf"
ssh root@fun-bedbug.maas "pct exec 112 -- docker exec uptime-kuma ping -c 1 ollama.app.homelab"
```

## Priority 3: Fix pve Docker Container (If Time Permits)

### Diagnose pve Container Issues
```bash
ssh root@pve.maas "pct status 100"
ssh root@pve.maas "pct exec 100 -- systemctl status docker"

# If Docker is hanging, try:
ssh root@pve.maas "pct exec 100 -- systemctl restart docker"
```

### Apply DNS Configuration to pve
If pve container is working, apply same DNS configuration as fun-bedbug.

## Priority 4: Investigate MAAS DNS Forwarding

### Check MAAS DNS Configuration
```bash
# Check if upstream DNS is actually configured in BIND
ssh root@pve.maas "grep -r 'forwarders' /etc/bind/maas/"
ssh root@pve.maas "grep -r '192.168.4.1' /etc/bind/"

# Test MAAS DNS forwarding directly
ssh root@pve.maas "nslookup ollama.app.homelab 127.0.0.1"
ssh root@pve.maas "nslookup ollama.app.homelab 192.168.4.53"
```

### Check MAAS Web UI Settings
- Access MAAS web interface: `http://192.168.4.53:5240/MAAS/`
- Navigate to Settings → DNS
- Verify "Upstream DNS" is set to `192.168.4.1`
- Check "Allow DNS resolution" settings for subnets

### BIND Configuration Verification
```bash
# Check MAAS BIND configuration
ssh root@pve.maas "cat /etc/bind/maas/named.conf.options.inside.maas"
ssh root@pve.maas "named-checkconf"

# If forwarders are missing, add manually:
ssh root@pve.maas "systemctl status bind9"
```

## Priority 5: Create Automation

### Create DNS Configuration Script
```bash
# Create persistent DNS configuration script
cat > /usr/local/bin/configure-homelab-dns.sh << 'EOF'
#!/bin/bash
# Homelab DNS Configuration Script
# Applies correct DNS settings for Docker containers in LXC

set -e

echo "Configuring homelab DNS..."

# Detect DNS management system
if systemctl is-active --quiet systemd-resolved; then
    echo "Using systemd-resolved configuration..."
    # Apply systemd-resolved config
elif command -v netplan >/dev/null 2>&1 && ls /etc/netplan/*.yaml >/dev/null 2>&1; then
    echo "Using netplan configuration..."
    # Apply netplan config
else
    echo "Using dhclient configuration..."
    # Apply dhclient config
fi

# Always configure Docker daemon
echo "Configuring Docker daemon DNS..."
cat > /etc/docker/daemon.json << DOCKER_EOF
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
DOCKER_EOF

systemctl restart docker

echo "DNS configuration complete!"
EOF

chmod +x /usr/local/bin/configure-homelab-dns.sh
```

## Priority 6: Documentation Updates

### Update CLAUDE.md
Add DNS configuration process to the project's AI instructions:

```markdown
## DNS Configuration for Docker Containers

When creating new Docker containers in LXC, apply homelab DNS configuration:
```bash
/usr/local/bin/configure-homelab-dns.sh
```

DNS servers in order:
1. 192.168.4.1 (OPNsense - .homelab domains)
2. IPv6 ISP DNS (backup)
3. 192.168.4.53 (MAAS - .maas domains)
```

## Success Criteria

- [ ] All Uptime Kuma monitors showing green status
- [ ] DNS resolution works for both .maas and .homelab domains
- [ ] Configuration persists after container restart
- [ ] Automation script created and tested
- [ ] Documentation updated

## Rollback Plan

If persistent configuration breaks something:

```bash
# Remove custom configurations
rm -f /etc/systemd/resolved.conf.d/homelab.conf
rm -f /etc/netplan/99-dns-override.yaml
rm -f /etc/dhcp/dhclient.conf.backup

# Restart networking
systemctl restart systemd-resolved
systemctl restart docker
```

## Estimated Time
- **Total:** 1-2 hours
- **Critical path:** 30 minutes (verify status + make persistent)
- **Full investigation:** Additional 1 hour if issues found