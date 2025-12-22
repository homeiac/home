# Voice PE ↔ HAOS Network Architecture

## Overview

This document describes the network architecture for Home Assistant Voice PE communication with Home Assistant OS, including the socat proxy hack that enables cross-network connectivity.

## Known Infrastructure (Verified)

### Voice PE Device
- **IP**: 192.168.86.10 (static, was .245 via DHCP)
- **Network**: Google WiFi (192.168.86.0/24)
- **Protocol**: ESPHome API (port 6053)
- **Hardware**: ESP32-based
- **Note**: Static IP required - Google WiFi has no DHCP reservations

### Home Assistant VM (VMID 116)
- **Host**: chief-horse.maas
- **Network Interfaces**:
  - net0: 192.168.4.240 (homelab, vmbr0)
  - net2: 192.168.86.22 (Google WiFi, vmbr2)
- **Ports**: 8123 (HTTP), plus add-on ports

### socat Proxy (on pve)
- **Service**: `/etc/systemd/system/ha-proxy.service`
- **Source file**: `proxmox/systemd/ha-proxy.service`
- **Listening**: 192.168.1.122:8123
- **Forwards to**: 192.168.4.240:8123
- **Purpose**: Allow Voice PE to reach HA HTTP API

## Network Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              NETWORK TOPOLOGY                                            │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                         GOOGLE WIFI NETWORK (192.168.86.0/24)                    │    │
│  │                                                                                   │    │
│  │    ┌──────────────┐           ┌──────────────┐           ┌──────────────┐        │    │
│  │    │   Voice PE   │           │  Google WiFi │           │     Mac      │        │    │
│  │    │ 192.168.86.10            │   Router     │           │ 192.168.86.x │        │    │
│  │    │   (ESP32)    │◄─────────►│ 192.168.86.1 │◄─────────►│              │        │    │
│  │    └──────────────┘   WiFi    └──────────────┘   WiFi    └──────────────┘        │    │
│  │                                      │                                            │    │
│  └──────────────────────────────────────┼────────────────────────────────────────────┘    │
│                                         │                                                 │
│                                         │ Uplink                                          │
│                                         ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                         ISP NETWORK (192.168.1.0/24)                             │    │
│  │                                                                                   │    │
│  │    ┌──────────────┐           ┌──────────────┐                                   │    │
│  │    │  ISP Router  │           │     pve      │                                   │    │
│  │    │192.168.1.254 │◄─────────►│192.168.1.122 │                                   │    │
│  │    └──────────────┘           │              │                                   │    │
│  │                               │ ┌──────────┐ │                                   │    │
│  │                               │ │ socat    │ │                                   │    │
│  │                               │ │ :8123    │ │                                   │    │
│  │                               │ └────┬─────┘ │                                   │    │
│  │                               └──────┼───────┘                                   │    │
│  └──────────────────────────────────────┼───────────────────────────────────────────┘    │
│                                         │                                                 │
│                                         │ Forward to 192.168.4.240:8123                  │
│                                         ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                         HOMELAB NETWORK (192.168.4.0/24)                         │    │
│  │                                                                                   │    │
│  │    ┌──────────────┐           ┌──────────────┐           ┌──────────────┐        │    │
│  │    │     pve      │           │ chief-horse  │           │  HA VM 116   │        │    │
│  │    │192.168.4.122 │           │ 192.168.4.19 │           │192.168.4.240 │        │    │
│  │    │              │           │              │           │    :8123     │        │    │
│  │    └──────────────┘           └──────────────┘           └──────────────┘        │    │
│  │                                                                                   │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

## Communication Paths

### PATH 1: Voice PE → HA (HTTP via socat proxy)

**Used for**: TTS audio file fetching, API calls from Voice PE

```
Voice PE (192.168.86.10)
    │
    │ WiFi
    ▼
Google WiFi Router (192.168.86.1)
    │
    │ Uplink to ISP
    ▼
ISP Router (192.168.1.254)
    │
    │ Ethernet
    ▼
pve socat proxy (192.168.1.122:8123)
    │
    │ TCP forward
    ▼
HA VM (192.168.4.240:8123)
```

**Evidence**: socat service running on pve, verified with `systemctl status ha-proxy`

### PATH 2: HA → Voice PE (ESPHome API)

**Used for**: ESPHome control, TTS streaming (Wyoming protocol)

```
HA VM net2 (192.168.86.22)
    │
    │ vmbr2 bridge
    ▼
chief-horse USB Ethernet (enx008b20105b82)
    │
    │ Ethernet cable
    ▼
Flint 3 Router (port 1 or 2, bridge mode)
    │
    │ WiFi (Flint 3 → Google Mesh)
    ▼
Google WiFi Network (192.168.86.0/24)
    │
    │ WiFi
    ▼
Voice PE (192.168.86.10:6053)
```

**Evidence**:
- `qm config 116` shows net2 on vmbr2
- `brctl show vmbr2` shows enx008b20105b82 bridged
- `ip neigh show dev vmbr2` shows 192.168.86.10 reachable

## TTS Latency Issue

### Observed Behavior
- **Piper TTS to Google speaker**: 0.2-0.98 seconds
- **Piper TTS to Voice PE**: 44-178 seconds (same audio)

### Measured Latencies (HARD EVIDENCE)

| Test | From | To | Latency | Date |
|------|------|-----|---------|------|
| Ping | Mac (86.x) | Google WiFi (86.1) | 10-13ms | 2025-12-15 |
| Ping | Mac (86.x) | Voice PE (86.245) | **105-378ms** | 2025-12-15 |
| Ping | chief-horse vmbr2 | Google WiFi (86.1) | 1.68-9ms | 2025-12-15 |
| Ping | chief-horse vmbr2 | Voice PE (86.245) | **55-757ms** | 2025-12-15 |

### TTS Speed Comparison (HARD EVIDENCE - 2025-12-15)

| Test | Time | Notes |
|------|------|-------|
| Piper raw synthesis | 0.05s | Very fast |
| Piper → Google Speaker | 0.22s | Fast (HTTP URL) |
| **Piper → Voice PE** | **61.67s** | **280x slower!** |

**CONCLUSION**: The bottleneck is NOT Piper synthesis. It's specifically in the ESPHome/Wyoming streaming path to Voice PE.

### Packet Trace Evidence (2025-12-15)

Traffic captured on vmbr2 during TTS:
- Uses **port 6053 (ESPHome API)**, NOT HTTP/socat
- Only 14 packets in 18 seconds
- Tiny data chunks (25-35 bytes) with multi-second gaps
- Path: HA VM (86.22) → vmbr2 → Flint 3 → WiFi → Voice PE (86.245)

## ROOT CAUSE IDENTIFIED (2025-12-15)

**Problem**: WiFi power-save mode is enabled by default on Voice PE firmware, causing 15-60+ second latency for TTS streaming.

**Evidence**:
- [GitHub Issue #257](https://github.com/esphome/home-assistant-voice-pe/issues/257) - "Some devices slow to play audio"
- [GitHub Issue #255](https://github.com/esphome/home-assistant-voice-pe/issues/255) - WiFi power-save fix

**Solution**: Add to ESPHome configuration:
```yaml
wifi:
  power_save_mode: none
  fast_connect: true
```

For UniFi access points: Enable "Enhanced IoT Connectivity" in radio settings for the SSID.

**How to apply**:
1. Adopt Voice PE in ESPHome dashboard (if not already)
2. Edit the device YAML to add the wifi settings above
3. Rebuild and flash via OTA or USB

---

### UNKNOWN - Needs Investigation
1. **Which path does Wyoming TTS streaming actually use?**
   - ESPHome API (port 6053) via PATH 2?
   - HTTP audio fetch via PATH 1 (socat)?
   - Need to trace actual packets during TTS

2. **Why is Voice PE ping latency so high from same WiFi?**
   - Voice PE WiFi radio/antenna issue?
   - Google WiFi hairpin NAT latency?
   - ESP32 processing overhead?
   - Need WiFi signal strength measurement

3. **What do Piper logs show during slow TTS?**
   - The "Sent info" chunks appear 2-5s apart
   - Is this sender-side (Piper) or receiver-side (Voice PE) throttling?

## socat Proxy Configuration

### Service File Location
- **Repo**: `proxmox/systemd/ha-proxy.service`
- **Deployed to**: `root@pve.maas:/etc/systemd/system/ha-proxy.service`

### Service Contents
```ini
[Unit]
Description=Home Assistant Proxy for Voice PE (192.168.1.x to 192.168.4.x)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/socat TCP-LISTEN:8123,bind=192.168.1.122,reuseaddr,fork TCP:192.168.4.240:8123
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Why This Is Needed
1. Voice PE is on Google WiFi (192.168.86.x)
2. HA is on homelab (192.168.4.x)
3. These networks cannot route directly (Flint 3 bridge is broken for 4.x access)
4. BUT: Google WiFi CAN reach ISP network (192.168.1.x)
5. pve has interfaces on both 1.x and 4.x
6. socat on pve bridges the gap

### HA Internal URL Configuration
HA must be configured to advertise the proxy URL so Voice PE fetches media from the right place.

**Settings → System → Network → Home Assistant URL**:
- Local network: `http://192.168.1.122:8123`

## Diagnostic Commands

### Check socat proxy status
```bash
ssh root@pve.maas "systemctl status ha-proxy"
ssh root@pve.maas "ss -tlnp | grep 8123"
```

### Test proxy connectivity
```bash
# From Mac (on Google WiFi)
curl -s --max-time 5 http://192.168.1.122:8123/ | head -c 100
```

### Measure Voice PE latency
```bash
# From Mac (same WiFi as Voice PE)
ping -c 10 192.168.86.245

# From chief-horse (via vmbr2/Flint 3 path)
ssh root@chief-horse.maas "ping -c 10 192.168.86.245"
```

### Check HA VM network interfaces
```bash
ssh root@chief-horse.maas "qm config 116 | grep net"
```

### Check vmbr2 bridge status
```bash
ssh root@chief-horse.maas "ip addr show vmbr2"
ssh root@chief-horse.maas "brctl show vmbr2"
ssh root@chief-horse.maas "ip neigh show dev vmbr2"
```

### Check USB Ethernet adapter
```bash
ssh root@chief-horse.maas "dmesg | grep enx008b | tail -10"
ssh root@chief-horse.maas "ip -s link show enx008b20105b82"
```

## Related Documentation

- [Voice PE Complete Setup Guide](voice-pe-complete-setup-guide.md)
- [Voice PE Network Proxy Setup](voice-pe-network-proxy.md)
- [Homelab Network Topology](homelab-network-topology.md)
- [Flint 3 Network Bridge Guide](flint3-network-bridge-guide.md)

## Tags

voice-pe, voicepe, home-assistant, homeassistant, network, socat, proxy, tts, latency, wyoming, esphome, esp32, google-wifi, flint3, vmbr2, troubleshooting

---

*Document created: 2025-12-15*
*Updated: 2025-12-22 - Voice PE now on static IP 192.168.86.10*
*Status: RESOLVED - WiFi power save was latency cause, static IP prevents DHCP issues*
