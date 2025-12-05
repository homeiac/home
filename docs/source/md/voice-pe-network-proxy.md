# Voice PE Network Proxy Setup

## Overview

This document describes the network proxy configuration that allows Home Assistant Voice PE (and other IoT devices) on the Google WiFi network (192.168.86.x) to reach Home Assistant on the homelab network (192.168.4.x).

## Problem Statement

- Voice PE connects to Google WiFi (192.168.86.x)
- Home Assistant runs at 192.168.4.240
- The Flint 3 bridge between these networks is broken
- Voice PE cannot run Tailscale (ESP32-based hardware)
- Direct communication between 192.168.86.x and 192.168.4.x is not possible

## Solution

A socat TCP proxy runs on the `pve` Proxmox host, which has interfaces on multiple networks:

| Interface | IP | Network |
|-----------|-----|---------|
| wlan0 | 192.168.86.27 | Google WiFi |
| vmbr0 | 192.168.1.122 | ISP network |
| vmbr25gbe | 192.168.4.122 | Homelab |

The key discovery: devices on Google WiFi (192.168.86.x) CAN reach the ISP network (192.168.1.x), and pve has an interface on both networks.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      NETWORK PATH                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Voice PE ──► Google WiFi ──► ISP Router ──► pve ──► HA         │
│  (86.x)         (86.x)        (1.254)      (1.122)   (4.240)    │
│                                               │                  │
│                                          socat proxy             │
│                                     192.168.1.122:8123           │
│                                            ↓                     │
│                                    192.168.4.240:8123            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration

### Systemd Service on pve

Location: `/etc/systemd/system/ha-proxy.service`

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

### Service Management

```bash
# Check status
ssh root@pve.maas "systemctl status ha-proxy"

# Restart if needed
ssh root@pve.maas "systemctl restart ha-proxy"

# View logs
ssh root@pve.maas "journalctl -u ha-proxy -f"
```

## Device Configuration

### Voice PE Setup

1. Connect Voice PE to Google WiFi (normal WiFi setup)
2. When prompted for Home Assistant URL, enter:
   ```
   http://192.168.1.122:8123
   ```
3. Complete the setup as normal

### Other IoT Devices

Any device on Google WiFi that needs to reach Home Assistant can use the same proxy address: `http://192.168.1.122:8123`

## Testing

```bash
# From Mac on Google WiFi (192.168.86.x):
curl -s http://192.168.1.122:8123/ | head -5

# Expected: Home Assistant HTML response
```

## Troubleshooting

### Proxy not responding

```bash
# Check if service is running
ssh root@pve.maas "systemctl status ha-proxy"

# Check if port is listening
ssh root@pve.maas "ss -tlnp | grep 8123"

# Check if HA is reachable from pve
ssh root@pve.maas "curl -s http://192.168.4.240:8123/ | head -1"
```

### Cannot reach 192.168.1.122 from Google WiFi

1. Verify ISP router is routing between subnets
2. Check firewall rules on ISP router
3. Verify pve's 192.168.1.122 interface is up:
   ```bash
   ssh root@pve.maas "ip addr show vmbr0"
   ```

## Security Considerations

- Port 8123 is exposed on the ISP network (192.168.1.x)
- This is an internal network, not internet-exposed
- If additional security is needed, consider:
  - IP allowlisting in socat
  - Firewall rules on pve
  - Mutual TLS (more complex)

## Dependencies

- `socat` package on pve: `apt install socat`
- Home Assistant at static IP 192.168.4.240
- pve network interfaces properly configured

## Related Documentation

- [Tailscale K3s Setup Guide](tailscale-k3s-setup-guide.md) - For devices that CAN run Tailscale
- [Home Assistant OS Network Priority Fix](homeassistant-os-network-priority-fix.md) - Multi-network HA configuration

## Tags

voice-pe, voicepe, home-assistant, homeassistant, network-proxy, socat, iot, esp32, google-wifi, network-bridge, proxy

---

*Document created: 2025-12-05*
