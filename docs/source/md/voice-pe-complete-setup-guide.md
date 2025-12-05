# Voice PE Complete Setup Guide

## Overview

This guide documents the complete setup of Home Assistant Voice PE in a complex multi-network homelab environment, including network proxying, local speech processing, and voice assistant configuration.

## Network Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HOMELAB NETWORK TOPOLOGY                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐     │
│  │  GOOGLE WIFI    │      │   ISP ROUTER    │      │    HOMELAB      │     │
│  │  192.168.86.x   │      │  192.168.1.x    │      │  192.168.4.x    │     │
│  └────────┬────────┘      └────────┬────────┘      └────────┬────────┘     │
│           │                        │                        │               │
│           │    ┌───────────────────┼────────────────────────┤               │
│           │    │                   │                        │               │
│           ▼    ▼                   ▼                        ▼               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                           PVE HOST                                   │   │
│  │                    (Multi-Network Gateway)                           │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  wlan0: 192.168.86.27   │  vmbr0: 192.168.1.122  │  vmbr25gbe: 192.168.4.122  │
│  │  (Google WiFi)          │  (ISP Network)         │  (Homelab)       │   │
│  └─────────────────────────┴─────────────────────────┴──────────────────┘   │
│                                    │                                        │
│                                    │ socat proxy                            │
│                                    │ 192.168.1.122:8123                     │
│                                    │      ↓                                 │
│                                    │ 192.168.4.240:8123                     │
│                                    │                                        │
│  ┌──────────────┐                  │                  ┌──────────────┐      │
│  │  VOICE PE    │──────────────────┘                  │  HOME        │      │
│  │              │                                     │  ASSISTANT   │      │
│  │ 192.168.86.245                                     │ 192.168.4.240│      │
│  │              │◄────────────────────────────────────│              │      │
│  │  (Google WiFi)     ESPHome API (6053)              │  (Homelab)   │      │
│  └──────────────┘     via chief-horse vmbr2           └──────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Communication Paths

### Voice PE to Home Assistant (HTTP for TTS audio)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Voice PE   │────►│ Google WiFi  │────►│  ISP Router  │────►│     pve      │
│ 192.168.86.245     │ 192.168.86.x │     │ 192.168.1.254│     │192.168.1.122 │
└──────────────┘     └──────────────┘     └──────────────┘     └──────┬───────┘
                                                                      │
                                                                socat proxy
                                                                      │
                                                                      ▼
                                                               ┌──────────────┐
                                                               │     HA       │
                                                               │192.168.4.240 │
                                                               │    :8123     │
                                                               └──────────────┘
```

### Home Assistant to Voice PE (ESPHome API)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│     HA VM    │────►│ chief-horse  │────►│   Voice PE   │
│192.168.4.240 │     │    vmbr2     │     │192.168.86.245│
│   (net0)     │     │192.168.86.244│     │    :6053     │
└──────────────┘     └──────────────┘     └──────────────┘

HA VM has net2 bridged to vmbr2 (Google WiFi network)
Direct Layer 2 connectivity for ESPHome native API
```

## Problem Statement

1. Voice PE connects to Google WiFi (192.168.86.x)
2. Home Assistant runs on homelab network (192.168.4.240)
3. Flint 3 router bridge between networks is broken
4. Voice PE is ESP32-based - cannot run Tailscale
5. Voice PE needs HTTP access to HA for TTS audio files
6. HA needs ESPHome API access to Voice PE for control

## Solution Components

### 1. socat Proxy on pve

The pve host has interfaces on all three networks, making it the ideal proxy point.

**Location**: `/etc/systemd/system/ha-proxy.service` on pve

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

**Management**:
```bash
# Check status
ssh root@pve.maas "systemctl status ha-proxy"

# Restart
ssh root@pve.maas "systemctl restart ha-proxy"

# View logs
ssh root@pve.maas "journalctl -u ha-proxy -f"
```

### 2. HA Internal URL Configuration

Configure HA to tell devices to fetch media from the proxy URL.

**Settings → System → Network → Home Assistant URL**:
- Local network: `http://192.168.1.122:8123`

This ensures Voice PE fetches TTS audio from the reachable proxy address.

### 3. ESPHome Bidirectional Communication

The HA VM (VMID 116 on chief-horse) has three network interfaces:

| Interface | Bridge | Network | IP |
|-----------|--------|---------|-----|
| net0 | vmbr0 | Homelab | 192.168.4.240 |
| net1 | vmbr1 | - | - |
| net2 | vmbr2 | Google WiFi | 192.168.86.22 |

This allows HA to reach Voice PE directly on the 86.x network for ESPHome API.

### 4. Local Speech Processing

#### Whisper (Speech-to-Text)

**Add-on**: Whisper (core_whisper)
**Memory requirement**: 4GB+ recommended
**Protocol**: Wyoming

#### Piper (Text-to-Speech)

**Add-on**: Piper (core_piper)
**Protocol**: Wyoming

#### HA VM Memory

Increased from 2GB to 6GB to support local Whisper processing.

**Decision**: Stopped k3s-vm-chief-horse (VMID 109) to dedicate chief-horse entirely to Home Assistant. The K3s cluster still has 3 nodes (pve, still-fawn, pumped-piglet-gpu) which is sufficient.

```bash
# Drain k3s node first (move workloads gracefully)
KUBECONFIG=~/kubeconfig kubectl drain k3s-vm-chief-horse --ignore-daemonsets --delete-emptydir-data

# Stop the k3s VM
ssh root@chief-horse.maas "qm stop 109"

# Increase HA memory to 6GB
ssh root@chief-horse.maas "qm set 116 --memory 6144"

# Reboot HA
ssh root@chief-horse.maas "qm reboot 116"
```

**Current state**:
- k3s-vm-chief-horse: **stopped** (was 4GB)
- haos16.0 (HA): **running** with 6GB
- K3s cluster: 3 nodes remaining (pve, still-fawn, pumped-piglet-gpu)

## Voice PE Setup Steps

### Prerequisites

1. socat proxy running on pve
2. HA internal URL set to proxy address
3. Whisper and Piper add-ons installed and running
4. Wyoming Protocol integration configured

### Setup Process

1. **Connect Voice PE to WiFi** (Google WiFi network via Bluetooth setup)

2. **ESPHome Discovery**
   - HA auto-discovers Voice PE via ESPHome
   - Configure at Settings → Devices & Services → ESPHome
   - Host: 192.168.86.245, Port: 6053

3. **Voice Assistant Wizard**
   - Follow the setup wizard
   - Select "Full local processing" for Whisper + Piper

4. **Test**
   - Say "Okay Nabu" (or configured wake word)
   - Try commands like "turn on office light"

## Troubleshooting

### "Entity not found" during setup

**Cause**: Whisper/Piper add-ons not installed or not running

**Fix**:
1. Install Whisper and Piper from Add-on Store
2. Start both add-ons
3. Add Wyoming Protocol integration (auto-discovers)
4. Retry setup

### Whisper OOM (Signal 9) crashes

**Cause**: Insufficient memory for ML model

**Fix**:
```bash
# Check HA VM memory
ssh root@chief-horse.maas "qm config 116 | grep memory"

# Increase to 6GB
ssh root@chief-horse.maas "qm set 116 --memory 6144"
ssh root@chief-horse.maas "qm reboot 116"
```

### "Unable to connect to Home Assistant" error

**Cause**: Voice PE can't reach HA for TTS audio files

**Fix**:
1. Verify socat proxy running: `ssh root@pve.maas "systemctl status ha-proxy"`
2. Verify HA internal URL set to `http://192.168.1.122:8123`
3. Test proxy: `curl http://192.168.1.122:8123/`

### ESPHome connection issues

**Cause**: HA can't reach Voice PE on 86.x network

**Fix**:
```bash
# Test from chief-horse (HA's host)
ssh root@chief-horse.maas "ping 192.168.86.245"

# Verify HA VM has net2 on vmbr2
ssh root@chief-horse.maas "qm config 116 | grep net"
```

## Verification Commands

```bash
# Check socat proxy
ssh root@pve.maas "systemctl status ha-proxy"
ssh root@pve.maas "ss -tlnp | grep 8123"

# Test proxy from Mac (on 86.x network)
curl -s http://192.168.1.122:8123/ | head -5

# Check Whisper add-on logs
source ~/code/home/proxmox/homelab/.env
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://192.168.4.240:8123/api/hassio/addons/core_whisper/logs" | tail -20

# Check STT/TTS entities
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://192.168.4.240:8123/api/states" | jq -r '.[] | select(.entity_id | startswith("stt.") or startswith("tts.")) | .entity_id'

# Check Voice PE entities
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://192.168.4.240:8123/api/states" | jq -r '.[] | select(.entity_id | contains("voice")) | .entity_id'
```

## Infrastructure Summary

| Component | Location | Purpose |
|-----------|----------|---------|
| Voice PE | 192.168.86.245 | Voice input device |
| HA VM | 192.168.4.240 (VMID 116 on chief-horse) | Home automation hub |
| socat proxy | pve:192.168.1.122:8123 | Network bridge for HTTP |
| Whisper | HA add-on | Local speech-to-text |
| Piper | HA add-on | Local text-to-speech |
| chief-horse vmbr2 | 192.168.86.244 | Bridge to Google WiFi for ESPHome |

## Related Documentation

- [Voice PE Network Proxy Setup](voice-pe-network-proxy.md) - Detailed proxy configuration
- [Tailscale K3s Setup Guide](tailscale-k3s-setup-guide.md) - Remote access (separate from Voice PE)
- [Home Assistant OS Network Priority Fix](homeassistant-os-network-priority-fix.md) - Multi-network HA configuration

## Tags

voice-pe, voicepe, home-assistant, homeassistant, esphome, whisper, piper, speech-to-text, text-to-speech, stt, tts, wyoming, network-proxy, socat, esp32, google-wifi, local-voice, voice-assistant, okay-nabu

---

*Document created: 2025-12-05*
