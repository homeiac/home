# Home Assistant DNS Resolution for .homelab Domains

Scripts and documentation to diagnose and fix Home Assistant DNS resolution for `*.app.homelab` domains like `frigate.app.homelab`.

## Problem

Home Assistant cannot resolve `frigate.app.homelab` while Mac clients can. This prevents HA integrations from using hostnames.

## Quick Start

```bash
# 1. Diagnose the DNS chain (run from Mac)
./00-diagnose-dns-chain.sh

# 2. Test if HA can reach Frigate
./01-test-ha-can-reach-frigate.sh

# 3. If diagnosis shows issues, see fix options:
./02-print-opnsense-dns-fix-steps.sh   # Option B: OPNsense fix
./03-print-ha-nmcli-fix-commands.sh    # Option C: HA nmcli fix

# 4. After fix, verify everything works
./04-verify-frigate-app-homelab-works.sh

# 5. Before committing, validate deliverables
./99-validate-deliverables.sh
```

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

## Scripts

| Script | Purpose |
|--------|---------|
| `00-diagnose-dns-chain.sh` | Full DNS chain diagnosis from Mac |
| `01-test-ha-can-reach-frigate.sh` | Test HA -> Frigate via API |
| `02-print-opnsense-dns-fix-steps.sh` | Print OPNsense DNS fix steps |
| `03-print-ha-nmcli-fix-commands.sh` | Print nmcli commands for HA |
| `04-verify-frigate-app-homelab-works.sh` | End-to-end verification |
| `99-validate-deliverables.sh` | Validate all deliverables meet constraints |

## Fix Options

### Option B: OPNsense DNS Fix (Recommended First)
No changes to Home Assistant. Add/verify DNS override in OPNsense.

### Option C: Home Assistant nmcli Fix
Set OPNsense (192.168.4.1) as HA's primary DNS via nmcli.

## Prerequisites

- HA_TOKEN in `proxmox/homelab/.env`
- Access to OPNsense web UI (for Option B)
- Access to HA console (for Option C) - Terminal Add-on or Proxmox console

## Files

```
scripts/ha-dns-homelab/
├── README.md                              # This file
├── 00-diagnose-dns-chain.sh               # Diagnosis
├── 01-test-ha-can-reach-frigate.sh        # HA test
├── 02-print-opnsense-dns-fix-steps.sh     # Option B steps
├── 03-print-ha-nmcli-fix-commands.sh      # Option C commands
├── 04-verify-frigate-app-homelab-works.sh # Verification
├── 99-validate-deliverables.sh            # Constraint validation
├── TEMPLATE-action-log-ha-dns-fix.md      # Reusable action log template
└── 2025-12-13-action-log-frigate-dns-fix.md # This run's action log
```

## Related Documentation

- **Blueprint**: `docs/troubleshooting/blueprint-ha-dns-homelab-resolution.md`
- **DNS Guide**: `docs/source/md/homelab_local_dns_resolution_guide.md`
- **HA Network Fix**: `docs/source/md/homeassistant-os-network-priority-fix.md`
