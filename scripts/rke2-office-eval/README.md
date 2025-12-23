# RKE2 Office Evaluation Setup

Proxmox + RKE2 with:
- Native Linux worker on Proxmox host (not VM)
- Windows worker as VM
- Entra ID authentication for Proxmox UI

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Proxmox VE Host (Debian 12)                │
│                                                         │
│  ┌───────────────────┐    ┌───────────────────────────┐ │
│  │  RKE2 Agent       │    │  Windows Server 2022 VM   │ │
│  │  (Native Linux)   │    │  - RKE2 Windows Agent     │ │
│  │  - No VM overhead │    │  - ADO Agent              │ │
│  │  - Direct HW      │    │                           │ │
│  └───────────────────┘    └───────────────────────────┘ │
│                                                         │
│  Entra ID SSO ──► OIDC ──► Proxmox Web UI (:8006)      │
└─────────────────────────────────────────────────────────┘
              │
              ▼
     Rancher Server (VM or separate host)
```

## Differences from Homelab Setup

| Component | Homelab (scripts/rke2-windows-eval/) | Office (this dir) |
|-----------|--------------------------------------|-------------------|
| Linux Worker | Ubuntu VM | Native on Proxmox host |
| Authentication | PAM/local | Entra ID via OIDC |
| Performance | VM overhead | Bare metal |
| Isolation | Full VM isolation | Shared host |

## Prerequisites

### Azure / Entra ID
- Azure subscription with Entra ID access
- App registration permissions

### Proxmox Host
- Proxmox VE 8.x
- Internet access (for Entra ID OIDC)
- Sufficient RAM: 16GB+ recommended

## Setup Order

1. `00-configure-entra-id.md` - Azure App Registration (manual steps)
2. `01-configure-proxmox-oidc.sh` - Add OIDC realm to Proxmox
3. `02-install-rancher-vm.sh` - Create Rancher management VM
4. `03-install-rke2-agent-native.sh` - Install RKE2 on Proxmox host itself
5. `04-create-windows-vm.sh` - Create Windows worker VM
6. `05-register-windows-node.sh` - Join Windows to cluster

## Running RKE2 on Proxmox Host

**Pros:**
- No virtualization overhead
- Direct NVMe/SSD access
- Better performance for I/O-heavy workloads

**Cons:**
- Less isolation (container escape = host access)
- Proxmox upgrades may affect RKE2
- Resource contention with VMs

**Recommendation:** Good for eval/dev. For production, use dedicated nodes.

## Entra ID Limitations

- Web UI only (SSH/console uses local PAM)
- No automatic group sync
- API tokens still require PAM users
