# MAAS DNS Scripts

---

## ⚠️ CRITICAL WARNING ⚠️

**DO NOT ATTEMPT TO FIX `.homelab` FORWARDING. YOU WILL BREAK `.maas` DNS.**

MAAS DNS is fragile:
- Killing `named` → zone files disappear
- Editing configs → MAAS overwrites on restart
- The fix exists but is NOT persistent

**If `.maas` breaks, run:** `./07-emergency-restore-maas-dns.sh`

---

## Current Status

- ✅ `.maas` DNS works - **DO NOT TOUCH**
- ❌ `.homelab` forwarding broken - **LEAVE IT ALONE**
- Workaround: `dig @192.168.4.1 hostname.homelab` (query OPNsense directly)

---

## Background

MAAS uses bind for DNS. Fake TLDs like `.homelab` need explicit forward zones, but MAAS regenerates all bind configs on restart, removing any manual changes.

## Scripts

| Script | Purpose |
|--------|---------|
| `00-check-dns-chain.sh` | Full diagnostic: Mac → MAAS → OPNsense |
| `01-check-maas-forwarders.sh` | Check MAAS bind configuration |
| `02-add-forward-zone.sh` | ⚠️ DANGEROUS - Add forward zone (not persistent) |
| `03-list-forward-zones.sh` | List all custom forward zones |
| `04-restart-maas-bind.sh` | ⚠️ DANGEROUS - May break zone files |
| `05-remove-forward-zone.sh` | Remove a forward zone |
| `06-flush-mac-dns-cache.sh` | Flush macOS DNS cache |
| `07-emergency-restore-maas-dns.sh` | 🚨 EMERGENCY - Restore broken .maas DNS |

## Quick Start

### Diagnose DNS issue
```bash
./00-check-dns-chain.sh rancher homelab
```

### Add forward zone for .homelab
```bash
./02-add-forward-zone.sh homelab
```

### Flush Mac DNS cache after fix
```bash
./06-flush-mac-dns-cache.sh
```

## Environment

- **MAAS VM**: pve.maas, VMID 102
- **MAAS DNS**: 192.168.4.53
- **OPNsense DNS**: 192.168.4.1

## RCA Document

Full root cause analysis: `docs/source/md/maas-dns-forwarding-rca.md`
