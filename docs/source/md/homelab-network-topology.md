# Homelab Network Topology

## Overview

This document describes the complete network topology of the homelab, including all subnets, key devices, and how they interconnect.

## Network Segments

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           NETWORK SEGMENTS                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐      │
│  │    GOOGLE WIFI      │  │    ISP NETWORK      │  │      HOMELAB        │      │
│  │   192.168.86.0/24   │  │   192.168.1.0/24    │  │   192.168.4.0/24    │      │
│  ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤      │
│  │ • WiFi devices      │  │ • ISP router        │  │ • Proxmox hosts     │      │
│  │ • IoT devices       │  │ • Bridge network    │  │ • K3s cluster       │      │
│  │ • Voice PE          │  │ • pve gateway       │  │ • Home Assistant    │      │
│  │ • Phones            │  │                     │  │ • Frigate NVR       │      │
│  │ • Flint 3 (broken)  │  │                     │  │ • All services      │      │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘      │
│           │                        │                        │                    │
│           │         ┌──────────────┴──────────────┐         │                    │
│           │         │                             │         │                    │
│           └─────────┤      PVE (Gateway)          ├─────────┘                    │
│                     │   Multi-homed host          │                              │
│                     │                             │                              │
│                     │  wlan0:    192.168.86.27    │                              │
│                     │  vmbr0:    192.168.1.122    │                              │
│                     │  vmbr25gbe: 192.168.4.122   │                              │
│                     └─────────────────────────────┘                              │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Detailed Topology

```
                                    INTERNET
                                        │
                                        ▼
                              ┌─────────────────┐
                              │   ISP ROUTER    │
                              │  192.168.1.254  │
                              └────────┬────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
          ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
          │   GOOGLE WIFI   │ │      PVE        │ │   (Direct to    │
          │   192.168.86.1  │ │ 192.168.1.122   │ │    homelab)     │
          │   (WiFi AP)     │ │ (Multi-homed)   │ │                 │
          └────────┬────────┘ └────────┬────────┘ └─────────────────┘
                   │                   │
     ┌─────────────┼─────────────┐     │
     │             │             │     │
     ▼             ▼             ▼     │
┌─────────┐  ┌─────────┐  ┌─────────┐  │
│ Voice PE│  │  Mac    │  │ Phones  │  │
│ .86.245 │  │ .86.32  │  │ .86.x   │  │
└─────────┘  └─────────┘  └─────────┘  │
                                       │
          ┌────────────────────────────┘
          │
          │    HOMELAB NETWORK (192.168.4.0/24)
          │    ══════════════════════════════════════════════════════════
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│   │     PVE      │  │  STILL-FAWN  │  │ CHIEF-HORSE  │  │  FUN-BEDBUG  │        │
│   │  .4.122      │  │    .4.17     │  │    .4.19     │  │    .4.172    │        │
│   │              │  │              │  │              │  │              │        │
│   │ • Gateway    │  │ • K3s VM     │  │ • K3s VM     │  │ • Frigate    │        │
│   │ • K3s VM     │  │   .4.212     │  │   .4.237     │  │   LXC 113    │        │
│   │   .4.238     │  │              │  │ • HA VM      │  │              │        │
│   │              │  │              │  │   .4.240     │  │              │        │
│   └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘        │
│                                              │                                   │
│                                              │ vmbr2                             │
│                                              │ 192.168.86.244                    │
│                                              │ (Bridge to Google WiFi)           │
│                                              ▼                                   │
│                                       ┌──────────────┐                          │
│                                       │   HA VM      │                          │
│                                       │  (haos16.0)  │                          │
│                                       │              │                          │
│                                       │ net0: .4.240 │                          │
│                                       │ net2: .86.22 │                          │
│                                       └──────────────┘                          │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────┐      │
│   │                        K3S CLUSTER                                    │      │
│   │                                                                       │      │
│   │   Nodes:                          Services (MetalLB):                 │      │
│   │   • k3s-vm-pve        .4.238      • Traefik        .4.50              │      │
│   │   • k3s-vm-still-fawn .4.212      • Ollama         .4.80              │      │
│   │   • k3s-vm-chief-horse .4.237     • Grafana        .4.100             │      │
│   │   • k3s-vm-pumped-piglet .4.210   • Prometheus     .4.101             │      │
│   │                                                                       │      │
│   │   Tailscale Subnet Router:                                            │      │
│   │   • ts-homelab-router (advertises 192.168.4.0/24)                     │      │
│   │                                                                       │      │
│   └──────────────────────────────────────────────────────────────────────┘      │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Key IP Addresses

### Proxmox Hosts

| Host | IP | Role |
|------|-----|------|
| pve | 192.168.4.122 | Primary host, multi-homed gateway |
| still-fawn | 192.168.4.17 | K3s worker |
| chief-horse | 192.168.4.19 | K3s worker, HA host |
| fun-bedbug | 192.168.4.172 | Frigate NVR |

### Virtual Machines

| VM | VMID | Host | IP | Purpose |
|----|------|------|-----|---------|
| k3s-vm-pve | - | pve | 192.168.4.238 | K3s node |
| k3s-vm-still-fawn | 108 | still-fawn | 192.168.4.212 | K3s node |
| k3s-vm-chief-horse | 109 | chief-horse | 192.168.4.237 | K3s node (currently stopped) |
| haos16.0 | 116 | chief-horse | 192.168.4.240 | Home Assistant OS |

### LXC Containers

| Container | CTID | Host | Purpose |
|-----------|------|------|---------|
| Frigate | 113 | fun-bedbug | NVR with Coral TPU |

### K3s Services (MetalLB)

| Service | IP | Port |
|---------|-----|------|
| Traefik | 192.168.4.50 | 80, 443 |
| Ollama | 192.168.4.80 | 11434 |

### IoT Devices (Google WiFi)

| Device | IP | Purpose |
|--------|-----|---------|
| Voice PE | 192.168.86.245 | Voice assistant |
| Mac | 192.168.86.32 | Development machine |

## Network Bridges (chief-horse)

HA VM requires access to both homelab and Google WiFi networks:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CHIEF-HORSE BRIDGES                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  vmbr0 ─────► 192.168.4.19/24  (Homelab LAN)                    │
│     │                                                            │
│     └──► HA VM net0 ──► 192.168.4.240                           │
│                                                                  │
│  vmbr1 ─────► (unused)                                          │
│     │                                                            │
│     └──► HA VM net1                                             │
│                                                                  │
│  vmbr2 ─────► 192.168.86.244/24 (Google WiFi)                   │
│     │                                                            │
│     └──► HA VM net2 ──► 192.168.86.22                           │
│              │                                                   │
│              └──► Direct access to Voice PE (.86.245)           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Cross-Network Communication

### Problem: 86.x cannot reach 4.x directly

The Flint 3 router bridge is broken - devices on Google WiFi cannot reach homelab.

### Solution 1: Tailscale (for capable devices)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    Phone     │────►│   Tailscale  │────►│   Homelab    │
│  (86.x or    │     │    Cloud     │     │  192.168.4.x │
│   cellular)  │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                            ▼
                     K3s Subnet Router
                     ts-homelab-router
                     Advertises 192.168.4.0/24
```

### Solution 2: socat Proxy (for ESP32/IoT devices)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Voice PE   │────►│   ISP Net    │────►│     pve      │────►│     HA       │
│ 192.168.86.245     │ 192.168.1.x  │     │192.168.1.122 │     │192.168.4.240 │
└──────────────┘     └──────────────┘     └──────┬───────┘     └──────────────┘
                                                 │
                                            socat proxy
                                         :8123 → .4.240:8123
```

## Tailscale Network

```
                              ☁️  TAILSCALE CLOUD
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            │                         │                         │
            ▼                         ▼                         ▼
      ┌──────────┐             ┌──────────┐             ┌──────────────┐
      │ ANDROID  │             │   MAC    │             │   K3S POD    │
      │  PHONE   │             │  (Dev)   │             │ ts-homelab-  │
      │100.x.x.x │             │100.x.x.x │             │   router     │
      │          │             │          │             │              │
      │ [CLIENT] │             │ [CLIENT] │             │ [SUBNET RTR] │
      └──────────┘             └──────────┘             │ [EXIT NODE]  │
                                                        └──────┬───────┘
                                                               │
                               Advertised Routes:              │
                               • 192.168.4.0/24  ◄─────────────┘
                               • 10.42.0.0/16
                               • 10.43.0.0/16
```

## Service Discovery

### DNS Resolution

- **homeassistant.maas**: Resolves to 192.168.4.240 (on homelab network)
- **\*.homelab**: OPNsense Unbound DNS overrides (e.g., grafana.homelab → 192.168.4.100)
- **\*.ts.net**: Tailscale MagicDNS

### mDNS/Zeroconf

- Home Assistant advertises on all connected networks
- ESPHome devices discovered via mDNS

## Firewall and Routing

### pve Host Routes

```
192.168.86.0/24 via wlan0     (Google WiFi)
192.168.1.0/24  via vmbr0     (ISP network)
192.168.4.0/24  via vmbr25gbe (Homelab)
```

### Key Services Exposed

| Service | Network | Port | Access |
|---------|---------|------|--------|
| HA | 192.168.4.240 | 8123 | Direct + Proxy |
| HA Proxy | 192.168.1.122 | 8123 | For 86.x devices |
| Frigate | 192.168.4.172:5000 | 5000 | Direct |
| Grafana | 192.168.4.100 | 80 | Via MetalLB |

## Related Documentation

- [Voice PE Complete Setup Guide](voice-pe-complete-setup-guide.md)
- [Voice PE Network Proxy Setup](voice-pe-network-proxy.md)
- [Tailscale K3s Setup Guide](tailscale-k3s-setup-guide.md)
- [Home Assistant OS Network Priority Fix](homeassistant-os-network-priority-fix.md)

## Tags

network, networking, topology, diagram, ascii, homelab, proxmox, k3s, kubernetes, tailscale, google-wifi, multi-network, routing, bridge, vmbr, subnet

---

*Document created: 2025-12-05*
