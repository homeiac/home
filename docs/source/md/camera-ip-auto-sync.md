# Camera IP Auto-Sync

Automatically detects when Reolink camera IPs change and updates Frigate configuration.

## Problem

AT&T router DHCP reservations don't persist reliably. When cameras get new IPs via DHCP, Frigate loses connectivity and requires manual config updates.

## Solution

A CronJob in K8s that:
1. Checks if cameras are responding at configured IPs (RTSP port 554)
2. If not, scans 192.168.1.x for ONVIF devices (port 8000)
3. Identifies cameras and updates Frigate ConfigMap
4. Triggers Frigate pod restart

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  K8s (frigate namespace)                                         │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  CronJob: camera-ip-discovery (every 5 min)              │   │
│  │  1. Check current IPs respond (RTSP 554)                 │   │
│  │  2. If down, scan 192.168.1.130-150 for ONVIF (8000)     │   │
│  │  3. Update ConfigMap with new IPs                        │   │
│  │  4. Restart Frigate                                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  ConfigMap: frigate-config                               │   │
│  │  - go2rtc streams with camera IPs                        │   │
│  │  - ONVIF host addresses                                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Deployment: frigate                                     │   │
│  │  - Restarts when ConfigMap changes                       │   │
│  │  - Reconnects to cameras at new IPs                      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Camera Identification

Since both cameras have identical credentials, identification is done by:
- **Hostname**: Cameras register as `Hall.attlocal.net` and `Living.attlocal.net` via DHCP
- **MAC Address**: `0C:79:55:4B:D4:2A` (Hall), `14:EA:63:A9:04:08` (Living Room)

Note: Hostname-based identification requires reverse DNS, which may not work from K8s. MAC-based identification requires nmap with privileges on the same L2 network.

## Current Limitation

The CronJob can detect when cameras are down and find new IPs, but **cannot definitively identify which camera is which** without:
1. Reverse DNS working (AT&T router DNS)
2. Running on HAOS (which can do nmap with MAC visibility)
3. Using authenticated ONVIF queries

## Files

| Path | Description |
|------|-------------|
| `gitops/clusters/homelab/apps/frigate-ip-webhook/deployment.yaml` | ServiceAccount and RBAC for ConfigMap access |
| `gitops/clusters/homelab/apps/frigate-ip-webhook/camera-discovery-cronjob.yaml` | CronJob that scans for cameras |
| `gitops/clusters/homelab/apps/frigate-ip-webhook/webhook.py` | HTTP webhook for HA integration (optional) |
| `scripts/haos/camera-ip-sync.sh` | HAOS script with MAC-based identification |

## Manual Recovery

If cameras change IPs and auto-sync doesn't identify them correctly:

```bash
# From HAOS, find cameras by MAC
docker exec homeassistant nmap -sn 192.168.1.0/24 | grep -B2 -E "0C:79:55|14:EA:63"

# Update Frigate config
# Edit gitops/clusters/homelab/apps/frigate/configmap.yaml
# Commit and push
flux reconcile kustomization flux-system --with-source
```

## Future Improvements

1. **Use DHCP reservations** on a proper router (Pi-hole, pfSense)
2. **Store MAC→camera mapping** and run discovery from HAOS
3. **Use Reolink P2P** protocol with camera UIDs (like the Reolink app does)
