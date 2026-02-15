# Why Your Homelab DNS Breaks When You're on Wi-Fi (and How to Fix It)

**TL;DR**: macOS uses DNS from your default route. If Wi-Fi is your default route and your homelab DNS is on a different network, `*.app.homelab` won't resolve. Fix: `/etc/resolver/homelab` with `nameserver 192.168.4.1`.

## The Setup

My Mac connects to two networks simultaneously:
- **Wi-Fi** (`192.168.1.x`) - AT&T router, internet access
- **USB LAN** (`192.168.4.x`) - Homelab network with OPNsense

OPNsense (`192.168.4.1`) has a wildcard DNS override:
```
*.app.homelab → 192.168.4.80 (Traefik)
```

This lets me access services like `frigate.app.homelab`, `ollama.app.homelab`, etc.

## The Problem

Firefox: "Hmm. We're having trouble finding that site."

```bash
$ dig frigate.app.homelab +short
# Nothing. Empty.

$ dig frigate.app.homelab @192.168.4.1 +short
192.168.4.80
# Works when I ask OPNsense directly!
```

## The Investigation

First, I checked my DNS settings:
```bash
$ networksetup -getdnsservers "USB 10/100/1000 LAN"
192.168.4.1
192.168.4.53
1.1.1.1
```

Looks right. But what's macOS actually using?

```bash
$ scutil --dns | grep -A5 "resolver #1"
resolver #1
  search domain[0] : attlocal.net
  nameserver[0] : 192.168.1.254    # ← AT&T router!
  if_index : 15 (en0)
```

There it is. macOS uses DNS from the interface with the default route:

```bash
$ route -n get default | grep interface
  interface: en0    # Wi-Fi, not USB LAN
```

## Why `networksetup` Doesn't Stick

Setting DNS with `networksetup -setdnsservers` works temporarily, but DHCP lease renewal overwrites it. AT&T routers also don't let you customize DHCP-provided DNS servers (locked down firmware).

## The Fix: Scoped Resolvers

macOS has a lesser-known feature: `/etc/resolver/`. Files here define per-domain DNS servers that survive DHCP renewals.

```bash
sudo sh -c 'echo "nameserver 192.168.4.1" > /etc/resolver/homelab'
```

That's it. Now:

```bash
$ scutil --dns | grep -A3 "homelab"
  domain   : homelab
  nameserver[0] : 192.168.4.1
  flags    : Request A records
  reach    : 0x00020002 (Reachable,Directly Reachable Address)
```

All `*.homelab` queries go to OPNsense. Everything else uses the default DNS.

## How It Works

```
┌──────────────────────────────────────────────────────────┐
│                    DNS Query Flow                        │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  frigate.app.homelab                                     │
│         │                                                │
│         ▼                                                │
│  ┌─────────────────────┐                                 │
│  │ /etc/resolver/homelab│ ──► OPNsense (192.168.4.1)    │
│  │ nameserver 192.168.4.1│     └─► 192.168.4.80         │
│  └─────────────────────┘                                 │
│                                                          │
│  google.com                                              │
│         │                                                │
│         ▼                                                │
│  ┌─────────────────────┐                                 │
│  │ Default resolver    │ ──► AT&T (192.168.1.254)       │
│  │ (from DHCP/Wi-Fi)   │     └─► normal resolution      │
│  └─────────────────────┘                                 │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## Why Not Just Use /etc/hosts?

You could add entries to `/etc/hosts`:
```
192.168.4.80 frigate.app.homelab
192.168.4.80 ollama.app.homelab
```

But:
1. You need an entry for every service
2. No wildcard support
3. Easy to forget when adding new services

The scoped resolver handles `*.homelab` with one file.

## Gotchas

### Subdomain Matching

The resolver matches the domain suffix. `/etc/resolver/homelab` handles:
- `frigate.app.homelab` ✓
- `anything.app.homelab` ✓
- `test.homelab` ✓
- `homelab` ✓

### Old Resolver Files

Check for stale files that might conflict:
```bash
ls -la /etc/resolver/
```

I had an old `homelab.local` pointing to a wrong IP. Remove anything outdated.

### No Wildcards in the File

The filename is the domain. You can't put `*.homelab` as a filename. Just use `homelab` and it matches all subdomains.

## The Script

For repeatability, I put this in `scripts/dns/setup-macos-resolver.sh`:

```bash
#!/bin/bash
set -e

if [[ $EUID -ne 0 ]]; then
   echo "Run with sudo"
   exit 1
fi

mkdir -p /etc/resolver
echo "nameserver 192.168.4.1" > /etc/resolver/homelab
echo "Done. Test with: dig frigate.app.homelab +short"
```

## Key Takeaways

1. **macOS uses DNS from default route interface** - not necessarily the interface you're accessing resources through
2. **DHCP overwrites manual DNS settings** - `networksetup` changes don't persist
3. **Scoped resolvers are permanent** - `/etc/resolver/<domain>` survives reboots and DHCP
4. **AT&T routers lock DNS settings** - can't fix this at the router level
5. **One file handles all subdomains** - `homelab` covers `*.app.homelab`, `*.homelab`, etc.

---

*Tags: macos, dns, resolver, homelab, multi-network, opnsense, scoped-resolver, dhcp*
