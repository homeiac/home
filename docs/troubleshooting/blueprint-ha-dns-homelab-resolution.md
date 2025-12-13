# Blueprint: Home Assistant DNS Resolution for .homelab Domains

**Date**: December 2025
**Last Used**: 2025-12-13
**Status**: Validated

---

## Problem Statement

Home Assistant cannot resolve `*.app.homelab` domains (like `frigate.app.homelab`) because:
1. HA may not be using OPNsense (192.168.4.1) as its DNS server
2. MAAS DNS forwarding to OPNsense may not be working
3. HA's network interface priority may be wrong

**Impact**: HA integrations that rely on hostname resolution fail.

---

## Architecture

```
Mac Client                    Home Assistant (192.168.4.240)
    |                                |
    v                                v
OPNsense DNS (192.168.4.1)    [DNS Server???]
    |                                |
    v                                |
*.app.homelab -> 192.168.4.80       |
    |                                |
    v                                v
Traefik (192.168.4.80) <---------- HA HTTP request
    |
    v
Frigate Pod (port 5000)
```

---

## Pre-Flight Checks

| Check | Script | Expected |
|-------|--------|----------|
| Mac DNS works | `00-diagnose-dns-chain.sh` | `frigate.app.homelab` -> 192.168.4.80 |
| Traefik responds | `00-diagnose-dns-chain.sh` | HTTP 200 from 192.168.4.80 |
| OPNsense has override | `00-diagnose-dns-chain.sh` | Wildcard `*.app.homelab` exists |
| MAAS forwards | `00-diagnose-dns-chain.sh` | Query via 192.168.4.53 returns 192.168.4.80 |

---

## Fix Options

### Option B: OPNsense DNS Fix (Recommended First)
**When to use**: MAAS forwarding to OPNsense is broken

**Steps** (via `02-print-opnsense-dns-fix-steps.sh`):
1. Login to OPNsense web UI (https://192.168.4.1)
2. Navigate: Services -> Unbound DNS -> Overrides -> Host Overrides
3. Verify/Add:
   - Host: `*`
   - Domain: `app.homelab`
   - IP: `192.168.4.80`
4. Click Apply or Reboot OPNsense

### Option C: Home Assistant nmcli Fix
**When to use**: HA needs OPNsense as primary DNS

**Steps** (via `03-print-ha-nmcli-fix-commands.sh`):
1. Access HA console (Terminal Add-on or Proxmox console)
2. Run: `login` (if using Terminal Add-on)
3. Check current: `nmcli connection show "Supervisor enp0s18" | grep dns`
4. Fix: `nmcli connection modify "Supervisor enp0s18" ipv4.dns "192.168.4.1"`
5. Reload: `nmcli connection reload`
6. Restart connection: `nmcli connection up "Supervisor enp0s18"`
7. Verify: `nslookup frigate.app.homelab`

---

## Verification

Run `04-verify-frigate-app-homelab-works.sh`:
- DNS resolves from Mac
- Traefik routes correctly
- HA can reach Frigate

---

## Rollback

### If Option C was applied:
```bash
nmcli connection modify "Supervisor enp0s18" ipv4.dns ""
nmcli connection reload
nmcli connection up "Supervisor enp0s18"
```

---

## Common Mistakes

1. **Forgetting OPNsense reboot**: Host overrides may not apply until reboot
2. **Wrong interface name**: HA interface may not be `enp0s18` - check with `nmcli connection show`
3. **MAAS DNS caching**: MAAS may cache DNS - wait or restart MAAS regiond

---

## References

- [DNS Configuration Guide](../source/md/homelab_local_dns_resolution_guide.md)
- [HA Network Priority Fix](../source/md/homeassistant-os-network-priority-fix.md)
- [Traefik IP Shuffle RCA](../source/md/rca/2025-11-29-traefik-ip-shuffle.md)

---

## Scripts

| Script | Purpose |
|--------|---------|
| `00-diagnose-dns-chain.sh` | Full DNS chain diagnosis |
| `01-test-ha-can-reach-frigate.sh` | Test HA->Frigate via API |
| `02-print-opnsense-dns-fix-steps.sh` | Print OPNsense fix steps |
| `03-print-ha-nmcli-fix-commands.sh` | Print nmcli commands |
| `04-verify-frigate-app-homelab-works.sh` | End-to-end verification |
| `99-validate-deliverables.sh` | Validate deliverables meet constraints |

---

## Action Log Template

Use `scripts/ha-dns-homelab/TEMPLATE-action-log-ha-dns-fix.md` for tracking each run.
