# Reolink Doorbell Network Architecture

## Overview

This document describes the network connectivity for the Reolink Video Doorbell WiFi, including all consumers and the migration path from DHCP to static IP with DNS.

## Network Subnets

| Subnet | Purpose | Gateway |
|--------|---------|---------|
| `192.168.1.x` | AT&T cable modem - Reolink lives here | 192.168.1.254 |
| `192.168.4.x` | Homelab VLAN (OPNsense) - Frigate, HA, K8s | 192.168.4.1 |
| `192.168.86.x` | Google Wifi mesh - Voice PE, IoT devices | 192.168.86.1 |

## Network Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         REOLINK DOORBELL CONNECTIONS                        │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐          RTSP (554)           ┌──────────────────────────┐
│   Reolink        │ ────────────────────────────► │  Frigate (K8s)           │
│   Doorbell       │                               │  on still-fawn           │
│reolink-vdb.homelab│  via go2rtc proxy            │  (192.168.4.x network)   │
│   192.168.1.10   │   127.0.0.1:8554              │                          │
└────────┬─────────┘                               └────────────┬─────────────┘
         │                                                      │
         │  HTTPS API (443)                                     │ Frigate API
         │  for PTZ, settings                                   │ (5000)
         ▼                                                      ▼
┌──────────────────┐                               ┌──────────────────────────┐
│   Home Assistant │◄──────────────────────────────│  HA Frigate Integration  │
│   192.168.4.240  │   Events, snapshots           │  frigate.homelab         │
│   (HAOS VM 116)  │                               │                          │
└────────┬─────────┘                               └──────────────────────────┘
         │
         │  Reolink Integration (native)
         │  - Doorbell press events
         │  - Motion detection
         │  - Two-way audio
         ▼
┌──────────────────┐
│   Automations    │
│   - Notifications│
│   - Package det. │
│   - LED control  │
└──────────────────┘
```

## Consumers

| Consumer | Protocol | Port | Config Location |
|----------|----------|------|-----------------|
| Frigate (K8s) | RTSP | 554 | `gitops/clusters/homelab/apps/frigate/configmap.yaml` |
| Home Assistant | HTTPS | 443 | Reolink integration (UI configured) |
| Reolink App | Cloud + local | various | Uses discovery/cloud |

## Target Configuration

### Static IP
- **IP Address**: 192.168.1.10
- **Gateway**: 192.168.1.254
- **Subnet Mask**: 255.255.255.0
- **DNS**: 192.168.1.254 (or 8.8.8.8)

### DNS Name
- **Hostname**: `reolink-vdb.homelab`
- **Resolves to**: 192.168.1.10

## Migration Steps

### Step 1: Verify HA DNS Resolution

Before migrating, confirm Home Assistant can resolve `.homelab` DNS names:

```bash
# Test from HA VM
scripts/haos/check-ha-api.sh
# Then test DNS resolution from inside HA
```

If DNS works, we can use `reolink.homelab` in all configs instead of hardcoded IPs.

### Step 2: Add DNS Override in OPNsense

Services → Unbound DNS → Overrides:
- **Host**: `reolink-vdb`
- **Domain**: `homelab`
- **IP**: `192.168.1.10`

### Step 3: Configure Static IP in Reolink

Via Reolink app or web UI:
1. Device Settings → Network
2. Disable DHCP
3. Set static IP: 192.168.1.10
4. Set gateway: 192.168.1.254
5. Save and reboot

### Step 4: Update Frigate Configmap

File: `gitops/clusters/homelab/apps/frigate/configmap.yaml`

```yaml
go2rtc:
  streams:
    reolink_doorbell: "rtsp://{FRIGATE_CAM_REOLINK_USER}:{FRIGATE_CAM_REOLINK_PASS}@reolink-vdb.homelab:554/h264Preview_01_sub"
```

### Step 5: Reconfigure HA Reolink Integration

1. Settings → Devices & Services → Reolink
2. Click the 3-dot menu (⋮) on the hub
3. Select **Reconfigure**
4. Enter new host: `reolink-vdb.homelab`
5. Submit and wait for "Initializing" to complete

## DNS Verification Commands

```bash
# From Mac
dig reolink-vdb.homelab @192.168.4.1

# From K8s pod (Frigate)
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- getent hosts reolink-vdb.homelab

# From HA (via qm guest exec)
ssh root@chief-horse.maas "qm guest exec 116 -- nslookup reolink-vdb.homelab"
```

## Related Documents

- Voice PE static IP: `scripts/voice-pe/configs/home-assistant-voice-09f5a3.yaml`
- Frigate config: `gitops/clusters/homelab/apps/frigate/configmap.yaml`
