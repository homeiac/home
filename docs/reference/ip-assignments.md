# IP Assignments - 192.168.4.0/24

**Source of Truth** for all static IP assignments in the homelab.

> **Related Files:**
> - [`proxmox/inventory.txt`](../../proxmox/inventory.txt) - Ansible-style inventory (legacy, sync with this file)
> - [`gitops/.../IP-ASSIGNMENTS.md`](../../gitops/clusters/homelab/infrastructure-config/metallb-config/IP-ASSIGNMENTS.md) - MetalLB assignments only

## MAAS IP Ranges

| Range | Type | Purpose |
|-------|------|---------|
| 192.168.4.1 | Gateway | OPNsense router |
| 192.168.4.2-19 | Unmanaged | Proxmox hosts (bare metal) |
| 192.168.4.20-49 | Reserved Dynamic | MAAS internal (commissioning/deployment) |
| 192.168.4.50-78 | DHCP Pool | Auto-assigned to new machines |
| 192.168.4.79 | Reserved | K3s control plane VIP (kube-vip) |
| 192.168.4.80-120 | Reserved | MetalLB LoadBalancer pool |
| 192.168.4.121-179 | DHCP Pool | Auto-assigned (extended range) |
| 192.168.4.180-199 | Reserved | Storage/Crucible nodes |
| 192.168.4.200-250 | Reserved Static | Infrastructure VMs (manual assignment) |

---

## Proxmox Hosts (Bare Metal)

| IP | Hostname | Notes |
|----|----------|-------|
| 192.168.4.11 | rapid-civet | |
| 192.168.4.17 | still-fawn | AMD Radeon GPU |
| 192.168.4.19 | chief-horse | HAOS host |
| 192.168.4.122 | pve | Primary Proxmox host |
| 192.168.4.172 | fun-bedbug | Disabled - thermal issues |
| 192.168.4.175 | pumped-piglet | RTX 3070 GPU |

---

## Infrastructure Services

| IP | Service | Notes |
|----|---------|-------|
| 192.168.4.53 | ubuntu-maas-vm | MAAS controller |
| 192.168.4.79 | k3s-vip | K3s control plane VIP (kube-vip) |

---

## K3s VMs (Control Plane Nodes)

| IP | VM Name | VMID | Proxmox Host | Status |
|----|---------|------|--------------|--------|
| 192.168.4.210 | k3s-vm-pumped-piglet-gpu | 105 | pumped-piglet | Active (primary) |
| 192.168.4.212 | k3s-vm-still-fawn | 108 | still-fawn | Active |
| 192.168.4.192 | k3s-vm-fun-bedbug | 114 | fun-bedbug | Disabled (thermal) |
| 192.168.4.193 | k3s-vm-pve | 107 | pve | Standby (powered off) |

---

## MetalLB LoadBalancer IPs (80-120)

| IP | Service | Namespace | Notes |
|----|---------|-----------|-------|
| 192.168.4.80 | traefik | kube-system | Main ingress, all HTTP(S) |
| 192.168.4.81 | frigate | frigate | NVR web UI, RTSP, WebRTC TCP |
| 192.168.4.82 | stable-diffusion-webui | stable-diffusion | SD WebUI |
| 192.168.4.84 | frigate-webrtc-udp | frigate | WebRTC UDP streams |
| 192.168.4.85 | ollama-lb | ollama | Ollama API |
| 192.168.4.120 | samba-lb | samba | SMB/CIFS shares |

---

## Storage/Crucible Nodes (180-199)

| IP | Hostname | Interface | Notes |
|----|----------|-----------|-------|
| 192.168.4.189 | proper-raptor | enp1s0 (1GbE) | Management interface |
| 192.168.4.190 | proper-raptor | enx* (USB 2.5GbE) | Crucible storage traffic (planned) |

---

## RKE2 Evaluation VMs (200-202)

| IP | VM Name | VMID | Proxmox Host | Status |
|----|---------|------|--------------|--------|
| 192.168.4.200 | rancher-server | 200 | pumped-piglet | Evaluation |
| 192.168.4.202 | linux-control | 202 | pumped-piglet | Evaluation |
| (none) | windows-worker | 201 | pumped-piglet | Stopped |

---

## Other Infrastructure VMs (203+)

| IP | VM Name | Notes |
|----|---------|-------|
| 192.168.4.203 | k3s-vm-fun-bedbug | Legacy entry (now .192) |
| 192.168.4.211 | (homelab.yaml ref) | Unknown - needs investigation |
| 192.168.4.238 | k3s-vm-pve | Legacy entry (now .193) |

---

## Reserved for Future Use

| Range | Purpose |
|-------|---------|
| 192.168.4.191-199 | Crucible storage expansion |
| 192.168.4.204-209 | Available |
| 192.168.4.213-237 | Available |
| 192.168.4.239-250 | Available |

---

## AT&T Router - 192.168.1.0/24 (Fixed Allocations)

These devices have **Fixed Allocation** configured in the AT&T router's IP Allocation table.
When replacing the router, reconfigure these allocations.

| IP | Device | MAC Address | Notes |
|----|--------|-------------|-------|
| 192.168.1.107 | TPLINK-WEBCAM | 00:14:d1:7c:e9:60 | Trendnet IP camera |
| 192.168.1.124 | homeassistant | bc:24:11:21:f4:ab | HAOS VM |
| 192.168.1.131 | OPNsense | bc:24:11:c2:5e:3b | Router/firewall |
| 192.168.1.110 | cloudflared | bc:24:11:dd:72:5f | Cloudflare tunnel |
| 192.168.1.137 | Hall | 0c:79:55:4b:d4:2a | Reolink E1 Zoom (hall) |
| 192.168.1.138 | Living | 14:ea:63:a9:04:08 | Reolink E1 Zoom (living room) |

**AT&T Router Config Location:** Home Network → IP Allocation → Click "Allocate" → Select "Private fixed:IP" → Save

---

## Update Log

| Date | Change |
|------|--------|
| 2026-01-26 | Added AT&T router 192.168.1.x fixed allocations |
| 2026-01-25 | Created from scattered sources |
