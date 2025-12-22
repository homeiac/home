# Runbook: Voice PE IP Address Change

**When**: Voice PE entities show "unavailable" in HA but device is powered on

## Diagnose

```bash
# 1. Check current Voice PE IP (serial logs)
scripts/voice-pe/serial-monitor-reset.sh /dev/cu.usbmodem* 15 | grep "IP Address"

# 2. Check what IP HA expects
scripts/voice-pe/check-esphome-device.sh | grep '"host"'

# 3. If IPs don't match → proceed with fix
```

## Fix Option A: Reconfigure in HA UI (fastest)

1. Settings → Devices & Services → ESPHome
2. Click "Home Assistant Voice 09f5a3" → Configure
3. Enter new IP address
4. Submit

## Fix Option B: Set Static IP (permanent fix)

```bash
# 1. Backup current config
scripts/voice-pe/haos-esphome-cat.sh /config/esphome/home-assistant-voice-09f5a3.yaml > /tmp/voice-pe-backup.yaml

# 2. Edit local config to add static IP
# Add under wifi: section:
#   manual_ip:
#     static_ip: 192.168.86.10
#     gateway: 192.168.86.1
#     subnet: 255.255.255.0
#     dns1: 192.168.86.1

# 3. Copy to ESPHome addon
scripts/voice-pe/haos-esphome-write.sh scripts/voice-pe/configs/home-assistant-voice-09f5a3.yaml /config/esphome/home-assistant-voice-09f5a3.yaml

# 4. Compile and flash via USB
scripts/voice-pe/docker-compile.sh voice-pe-config.yaml run

# 5. After flash, reconfigure HA to use new static IP (Option A)
```

## Verify

```bash
scripts/voice-pe/check-entities.sh | grep -E "unavailable|idle|on|off"
# All entities should show states, not "unavailable"
```

## Notes

- Google WiFi DHCP range: 192.168.86.20-250
- Safe static IPs: 192.168.86.2-19
- Current static IP: 192.168.86.10
- HA does NOT auto-update cached IP on restart
- ESPHome integration must be reconfigured or deleted/re-added
