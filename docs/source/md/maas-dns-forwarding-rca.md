# RCA: MAAS DNS Not Forwarding .homelab Domain

**Date**: 2025-12-19
**Severity**: Medium (DNS resolution broken for internal services)
**Duration**: ~30 minutes to diagnose and fix
**Services Affected**: All `*.homelab` DNS resolution from MAAS-managed clients

---

## ⚠️ CRITICAL WARNING - DO NOT TOUCH MAAS DNS ⚠️

**MAAS DNS IS FRAGILE. DO NOT ATTEMPT TO FIX `.homelab` FORWARDING.**

### What Happens If You Try:
1. Adding forward zones to `named.conf` → **MAAS overwrites on restart**
2. Killing `named` process → **Zone files disappear, `.maas` resolution breaks**
3. Editing any bind config → **MAAS regenerates everything on `snap restart maas`**

### The Zone File Problem:
- Zone files live in `/var/snap/maas/{revision}/bind/zone.*`
- When you `pkill named`, pebble restarts bind BUT zone files are gone
- Only `snap restart maas` regenerates zone files
- But `snap restart maas` also regenerates `named.conf`, removing your changes

### Current State (2025-12-19):
- ✅ `.maas` DNS works - **DO NOT TOUCH**
- ❌ `.homelab` forwarding broken - **LEAVE IT ALONE**
- Use `dig @192.168.4.1 hostname.homelab` to query OPNsense directly if needed

### If You Break It:
```bash
# Full MAAS restart regenerates zone files
ssh root@pve.maas "qm guest exec 102 -- snap restart maas"
# Wait 15 seconds, then test
dig @192.168.4.53 still-fawn.maas +short
```

---

## Executive Summary

MAAS DNS (bind) was not forwarding queries for the `.homelab` fake TLD to OPNsense, causing NXDOMAIN responses for internal services like `rancher.homelab`. The root cause was that bind queries root DNS servers for unknown TLDs, which correctly return NXDOMAIN since `.homelab` is not a real TLD. The fix required adding an explicit forward zone to tell bind to ONLY query OPNsense for `.homelab` domains.

## Timeline

| Time | Event |
|------|-------|
| T+0 | User reports `rancher.homelab` not resolving |
| T+2m | Confirmed OPNsense (192.168.4.1) returns correct IP |
| T+3m | Confirmed MAAS (192.168.4.53) returns NXDOMAIN |
| T+10m | Located MAAS VM (VMID 102) on pve.maas |
| T+15m | Found forwarders configured in UI but bind not using them for .homelab |
| T+20m | Identified root cause: bind queries root servers for fake TLDs |
| T+25m | Added forward zone for .homelab |
| T+30m | Verified fix, DNS resolving correctly |

## Environment

```
DNS Chain: Client → MAAS (192.168.4.53) → OPNsense (192.168.4.1)

MAAS Server:
- Host: pve.maas (Proxmox VE)
- VMID: 102 (UbuntuMAAS)
- MAAS Version: 3.5.10
- DNS: bind (managed by MAAS pebble service)

OPNsense:
- IP: 192.168.4.1
- Service: Unbound DNS
- Has host overrides for *.homelab
```

## Root Cause Analysis

### The Problem

When a client queries MAAS for `rancher.homelab`:

1. MAAS bind receives the query
2. Bind checks if it's authoritative for `.homelab` → No
3. Bind queries **root DNS servers** for `.homelab`
4. Root servers return **NXDOMAIN** (`.homelab` is not a real TLD)
5. Bind caches and returns NXDOMAIN to client
6. **Forwarders are never consulted** because bind already got an authoritative answer

### Why Forwarders Didn't Help

The MAAS UI setting for "Upstream DNS" (forwarders) only applies when:
- Bind cannot resolve a query through normal recursion
- The query is for a domain bind doesn't know about

For fake TLDs like `.homelab`, bind's normal recursion returns NXDOMAIN from root servers, so it never falls back to forwarders.

### The Fix

Add an explicit **forward zone** that tells bind:
- For `.homelab` queries, ONLY ask the specified forwarder
- Do NOT query root servers

```bind
zone "homelab" {
    type forward;
    forward only;
    forwarders { 192.168.4.1; };
};
```

## Configuration Details

### MAAS Bind Configuration Files

| File | Purpose |
|------|---------|
| `/var/snap/maas/{rev}/bind/named.conf` | Main config (includes others) |
| `/var/snap/maas/current/bind/named.conf.options.inside.maas` | MAAS-managed options (forwarders, ACLs) |
| `/var/snap/maas/current/bind/named.conf.maas` | MAAS-managed zones |
| `/var/snap/maas/current/bind/named.conf.local.maas` | **Custom forward zones (we created this)** |

### Important Notes

1. **Snap revision paths**: Bind uses versioned path (`/var/snap/maas/40962/`) not just `current`
2. **Pebble manages bind**: Kill named and pebble auto-restarts it
3. **SIGHUP not sufficient**: Must kill and restart for config changes
4. **MAAS may overwrite**: On upgrade, check if custom config persists

## Verification Commands

```bash
# From Mac - test full chain
dig rancher.homelab @192.168.4.53 +short

# From inside MAAS VM - test local bind
ssh root@pve.maas "qm guest exec 102 -- bash -c 'host rancher.homelab 127.0.0.1'"

# Check forward zones
ssh root@pve.maas "qm guest exec 102 -- cat /var/snap/maas/current/bind/named.conf.local.maas"
```

## Prevention

1. **Document fake TLDs**: Any new fake TLD (e.g., `.local`, `.internal`) needs a forward zone
2. **Test after MAAS upgrade**: Custom configs may be lost
3. **Use scripts**: `scripts/maas-dns/` has automation for adding/removing forward zones

## Related Scripts

| Script | Purpose |
|--------|---------|
| `00-check-dns-chain.sh` | Full diagnostic of DNS resolution chain |
| `01-check-maas-forwarders.sh` | Check MAAS bind forwarder config |
| `02-add-forward-zone.sh` | Add forward zone for a fake TLD |
| `03-list-forward-zones.sh` | List all custom forward zones |
| `04-restart-maas-bind.sh` | Restart bind (with verification) |
| `05-remove-forward-zone.sh` | Remove a forward zone |
| `06-flush-mac-dns-cache.sh` | Flush macOS DNS cache (requires sudo) |

## Client-Side Troubleshooting

### macOS DNS Cache

macOS caches DNS responses, including NXDOMAIN. After fixing server-side DNS, clients may still see the old cached response.

**Symptoms:**
- Server DNS queries work: `dig hostname.homelab @192.168.4.53` returns IP
- Local resolution fails: `nslookup hostname.homelab` returns NXDOMAIN

**Fix - Flush macOS DNS cache:**
```bash
sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
```

Or use the script:
```bash
./scripts/maas-dns/06-flush-mac-dns-cache.sh
```

**Verify:**
```bash
nslookup rancher.homelab
```

### Other Clients

| OS | Flush Command |
|----|---------------|
| macOS | `sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder` |
| Linux (systemd-resolved) | `sudo systemd-resolve --flush-caches` |
| Linux (nscd) | `sudo systemctl restart nscd` |
| Windows | `ipconfig /flushdns` |

## Lessons Learned

1. **Forwarders ≠ Forward Zones**: Global forwarders only apply when recursion fails; fake TLDs need explicit forward zones
2. **Test from multiple points**: OPNsense working doesn't mean MAAS is forwarding
3. **Check actual config**: MAAS UI settings may not reflect bind's runtime config
4. **Snap versioning**: Always check which revision bind is using

## Tags

`dns, maas, bind, forwarder, forward-zone, homelab, opnsense, nxdomain, fake-tld, proxmox`
