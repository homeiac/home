# macOS Homelab DNS Resolver Runbook

## Problem

When your Mac is connected to multiple networks (e.g., Wi-Fi on `192.168.1.x` and USB LAN on `192.168.4.x`), DNS queries use the default route's DNS server. If your default route is through Wi-Fi (AT&T router), `*.app.homelab` domains won't resolve because AT&T's DNS doesn't know about your homelab zones.

**Symptoms:**
- `frigate.app.homelab` doesn't resolve in Firefox
- `dig frigate.app.homelab @192.168.4.1 +short` works (returns `192.168.4.80`)
- `dig frigate.app.homelab +short` fails (empty response)
- `scutil --dns` shows AT&T router (`192.168.1.254`) as primary DNS

## Root Cause

macOS uses the DNS server from the interface with the default route. Manual DNS settings via `networksetup -setdnsservers` get overwritten on DHCP lease renewal.

## Solution: Scoped Resolver

macOS supports scoped resolvers in `/etc/resolver/` that route specific domains to specific DNS servers. These survive DHCP renewals.

### Quick Fix

```bash
sudo sh -c 'echo "nameserver 192.168.4.1" > /etc/resolver/homelab'
```

### Using the Script

```bash
sudo ./scripts/dns/setup-macos-resolver.sh
```

### Verification

```bash
# Check resolver is active
scutil --dns | grep -A3 "homelab"

# Test resolution
dig frigate.app.homelab +short
# Expected: 192.168.4.80

# Test in browser
open http://frigate.app.homelab
```

## How It Works

```
*.homelab DNS query
       │
       ▼
┌─────────────────────────────┐
│  /etc/resolver/homelab      │
│  nameserver 192.168.4.1     │
└─────────────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  OPNsense (192.168.4.1)     │
│  *.app.homelab → 192.168.4.80│
└─────────────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  Traefik (192.168.4.80)     │
│  Routes by Host header      │
└─────────────────────────────┘
```

## Troubleshooting

### Resolver not working

Check the file exists and has correct content:
```bash
cat /etc/resolver/homelab
# Should show: nameserver 192.168.4.1
```

Check macOS sees it:
```bash
scutil --dns | grep -B2 -A3 "homelab"
```

### OPNsense not returning correct IP

Test OPNsense directly:
```bash
dig frigate.app.homelab @192.168.4.1 +short
# Should return 192.168.4.80
```

If empty, check OPNsense Host Overrides:
- Services → Unbound DNS → Overrides → Host Overrides
- Should have: Host `*`, Domain `app.homelab`, IP `192.168.4.80`

### Stale resolver files

Remove old/incorrect resolver files:
```bash
ls -la /etc/resolver/
# Remove any that point to wrong IPs
sudo rm /etc/resolver/homelab.local  # example
```

## Related Docs

- [Homelab Local DNS Resolution Guide](../source/md/homelab_local_dns_resolution_guide.md)
- [Seamless Access Architecture](../product/seamless-access/architecture-seamless-access.md)

## Tags

dns, macos, resolver, opnsense, homelab, multi-network, dhcp, scoped-resolver
