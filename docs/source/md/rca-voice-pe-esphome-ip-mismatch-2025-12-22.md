# RCA: Voice PE ESPHome IP Mismatch

**Date**: 2025-12-22
**Duration**: ~90 minutes (60 min wasted on wrong diagnosis)
**Impact**: Voice PE completely unavailable in HA
**Status**: RESOLVED

## Summary

Voice PE entities showed "unavailable" in Home Assistant. Root cause: DHCP assigned new IP (192.168.86.28) but HA's ESPHome integration cached old IP (192.168.86.245). Fixed by setting static IP (192.168.86.10) and reconfiguring HA.

## Network Architecture (Updated)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    VOICE PE NETWORK TOPOLOGY                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────── GOOGLE WIFI (192.168.86.0/24) ──────────────────┐  │
│  │                                                                         │  │
│  │   ┌─────────────┐                        ┌─────────────┐               │  │
│  │   │  Voice PE   │  WiFi                  │  HAOS VM    │               │  │
│  │   │ 192.168.86.10 ◄─────────────────────► 192.168.86.22 (net2)        │  │
│  │   │   :6053     │  ESPHome API           │             │               │  │
│  │   │  (ESP32)    │  HA initiates ──────►  │             │               │  │
│  │   └─────────────┘                        └─────────────┘               │  │
│  │         │                                       │                       │  │
│  │         │ static IP                             │ also on:              │  │
│  │         │ (was DHCP .28, .245)                  │                       │  │
│  └─────────┼───────────────────────────────────────┼───────────────────────┘  │
│            │                                       │                          │
│            │ HTTP (TTS fetch)                      │                          │
│            ▼                                       ▼                          │
│  ┌─────────────────────── ISP (192.168.1.0/24) ──────────────────────────┐  │
│  │                                                                         │  │
│  │   ┌─────────────┐      socat proxy       ┌─────────────┐               │  │
│  │   │    pve      │ ──────────────────────► │   HAOS VM   │               │  │
│  │   │192.168.1.122│      forwards to       │192.168.4.240│ (net0)        │  │
│  │   │   :8123     │ ───────────────────────► │   :8123    │               │  │
│  │   └─────────────┘                        └─────────────┘               │  │
│  │                                                                         │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  CRITICAL FLOWS:                                                             │
│  ──────────────                                                              │
│  1. HA → Voice PE (ESPHome API :6053): HA initiates, via 192.168.86.x       │
│  2. Voice PE → HA (TTS fetch): Via socat proxy 192.168.1.122 → 192.168.4.240│
│                                                                              │
│  IP ADDRESSES THAT MATTER:                                                   │
│  ─────────────────────────                                                   │
│  • Voice PE: 192.168.86.10 (static, was .245 then .28 via DHCP)             │
│  • HA external (socat): 192.168.1.122:8123 (Voice PE uses this for HTTP)    │
│  • HA internal: 192.168.4.240:8123 (homelab network)                         │
│  • HA google-wifi: 192.168.86.22 (ESPHome API connection source)            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## The Debugging Disaster

### What AI Did Wrong

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        WASTED TIME: BAD ASSUMPTIONS                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  MISTAKE 1: Assumed 192.168.1.122 was Voice PE IP                            │
│  ─────────────────────────────────────────────────                           │
│  User: "external URL for HA is 192.168.1.122:8123"                           │
│  AI: *doesn't read*, assumes Voice PE is at 192.168.1.122                    │
│  Reality: 192.168.1.122 is socat PROXY for HA, not Voice PE                  │
│                                                                               │
│  MISTAKE 2: Claimed subnet isolation without checking                        │
│  ──────────────────────────────────────────────────                          │
│  AI: "Voice PE at .86.28 can't reach HA at .4.240 - different subnets!"     │
│  User: "but external URL is 192.168.1.122... .86 can reach it"               │
│  AI: *still didn't understand the proxy architecture*                        │
│                                                                               │
│  MISTAKE 3: Used hardcoded .240 IP from stale script                         │
│  ──────────────────────────────────────────────────                          │
│  scripts/haos/check-ha-api.sh had: HA_URL="http://192.168.4.240:8123"        │
│  AI reported results from wrong endpoint without noticing                    │
│                                                                               │
│  MISTAKE 4: Didn't check ESPHome config entry FIRST                          │
│  ──────────────────────────────────────────────────                          │
│  AI checked: network connectivity, ping, HA logs, entity states              │
│  AI should have checked: ESPHome config entry stored IP                      │
│  User had to say: "check from haos whether it can reach 192.168.86.28"       │
│                                                                               │
│  TIMELINE OF WASTE:                                                          │
│  ─────────────────                                                           │
│  00:00 - User reports Voice PE spinning, can't connect                       │
│  00:10 - AI checks serial logs: device healthy, WiFi connected               │
│  00:15 - AI claims "different subnets" problem (WRONG)                       │
│  00:20 - User corrects: "192.168.1.122 is HA external URL"                   │
│  00:25 - AI tests connectivity FROM HAOS (should have done earlier)          │
│  00:30 - AI FINALLY checks ESPHome config entry: "host": "192.168.86.245"    │
│  00:35 - ROOT CAUSE FOUND: HA has wrong IP cached                            │
│  00:40 - User: "can you just fucking fix it"                                 │
│  01:30 - Fixed after Docker DNS issues, compile errors, etc.                 │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Correct Diagnostic Flow (For Next Time)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    CORRECT DIAGNOSIS SEQUENCE                                │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  STEP 1: Get actual device IP from serial logs                               │
│  ────────────────────────────────────────────                                │
│  $ scripts/voice-pe/serial-monitor-reset.sh                                  │
│  Output: "IP Address: 192.168.86.28"  ◄── ACTUAL IP                          │
│                                                                               │
│  STEP 2: Get HA's cached IP from ESPHome config                              │
│  ──────────────────────────────────────────────                              │
│  $ scripts/voice-pe/check-esphome-device.sh | grep host                      │
│  Output: "host": "192.168.86.245"     ◄── CACHED IP (WRONG!)                 │
│                                                                               │
│  STEP 3: Compare                                                             │
│  ───────────────                                                             │
│  .28 ≠ .245 → DHCP changed IP, HA has stale cache                           │
│                                                                               │
│  STEP 4: Fix                                                                 │
│  ──────────                                                                  │
│  Option A: Reconfigure in HA UI with new IP                                  │
│  Option B: Set static IP in ESPHome config (permanent)                       │
│                                                                               │
│  TOTAL TIME IF DONE RIGHT: 5 minutes                                         │
│  ACTUAL TIME WASTED: 60+ minutes                                             │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Root Cause

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         ROOT CAUSE ANALYSIS                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  WHAT HAPPENED:                                                              │
│  ─────────────                                                               │
│  1. Voice PE was on DHCP (Google WiFi assigns 192.168.86.20-250)             │
│  2. Device had IP 192.168.86.245, HA connected fine                          │
│  3. DHCP lease expired/changed, device got new IP: 192.168.86.28             │
│  4. HA's ESPHome integration stores IP in config entry (not hostname)        │
│  5. HA kept trying to connect to .245 (timeout, no response)                 │
│  6. All entities → "unavailable"                                             │
│                                                                               │
│  WHY HA DIDN'T AUTO-DISCOVER:                                                │
│  ───────────────────────────                                                 │
│  - ESPHome uses mDNS for discovery                                           │
│  - Once configured, HA caches IP in config entry                             │
│  - mDNS updates don't override cached config                                 │
│  - HA restart doesn't re-query mDNS for existing integrations                │
│                                                                               │
│  WHY GOOGLE WIFI MAKES THIS WORSE:                                           │
│  ─────────────────────────────────                                           │
│  - No DHCP reservation feature (consumer mesh limitation)                    │
│  - Can't pin device to specific IP                                           │
│  - Only fix: static IP on device itself                                      │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Resolution

```bash
# 1. Updated ESPHome config with static IP
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  manual_ip:
    static_ip: 192.168.86.10    # Outside DHCP range (20-250)
    gateway: 192.168.86.1
    subnet: 255.255.255.0
    dns1: 192.168.86.1

# 2. Compiled and flashed via USB
scripts/voice-pe/docker-compile.sh voice-pe-config.yaml run

# 3. Reconfigured HA ESPHome integration to use 192.168.86.10
# (HA UI: Settings → Devices & Services → ESPHome → Configure)
```

## Scripts Created/Fixed

| Script | Purpose |
|--------|---------|
| `scripts/voice-pe/serial-monitor.sh` | Read ESP32 serial logs without hanging |
| `scripts/voice-pe/serial-monitor-reset.sh` | Reset device and capture boot logs |
| `scripts/voice-pe/check-esphome-device.sh` | Get HA's cached ESPHome config (including IP) |
| `scripts/voice-pe/check-esphome-entries.sh` | List ESPHome integration entries |
| `scripts/voice-pe/haos-esphome-cat.sh` | Read files from ESPHome addon via docker |
| `scripts/voice-pe/haos-esphome-write.sh` | Write files to ESPHome addon via base64 |
| `scripts/voice-pe/haos-docker-exec.sh` | Run commands in HAOS docker containers |
| `scripts/voice-pe/docker-compile.sh` | Fixed: use `$SCRIPT_DIR` not `$(pwd)`, added timeout/error handling |

## Lessons Learned

1. **Check ESPHome config entry FIRST** when device shows unavailable
2. **Read the network architecture doc** before making subnet assumptions
3. **Google WiFi has no DHCP reservations** - must use static IP on device
4. **HA caches ESPHome IPs** - restart doesn't help, must reconfigure
5. **192.168.1.122 is socat proxy** - not a device IP, it forwards to 192.168.4.240

## Prevention

1. **Static IP set**: Voice PE now at 192.168.86.10 (outside DHCP range)
2. **Runbook created**: `docs/source/md/runbook-voice-pe-ip-change.md`
3. **Network architecture updated**: This document includes corrected diagram
4. **OpenMemory**: Store this pattern for future reference

## Related

- Network Architecture: `docs/source/md/voice-pe-haos-network-architecture.md`
- Previous RCA: `docs/source/md/rca-voice-pe-tts-failure-2025-12-20.md`
- Runbook: `docs/source/md/runbook-voice-pe-ip-change.md`

## Tags

voice-pe, esphome, ip-address, dhcp, static-ip, google-wifi, home-assistant, unavailable, rca, network, mDNS, config-entry
