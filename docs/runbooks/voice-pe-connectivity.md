# Voice PE Connectivity Runbook

Quick diagnosis and fix for Home Assistant Voice Preview Edition connectivity issues.

## Quick Diagnosis

```bash
scripts/voice-pe/diagnose-connectivity.sh
```

## Connection Flow

```
═══════════════════════════════════════════════════════════════════════════════
                     VOICE PE ↔ HOME ASSISTANT CONNECTION FLOW
═══════════════════════════════════════════════════════════════════════════════

BOOT SEQUENCE:
══════════════
  Voice PE                                                    Home Assistant
  (192.168.86.10)                                            (192.168.4.240)
       │                                                            │
       │── 1. Connect WiFi ──► Google WiFi                         │
       │◀── 2. Get static IP (86.10)                               │
       │                                                            │
       │   3. Start ESPHome API server on :6053                    │
       │      LED: Blue twinkle (waiting for HA)                   │
       │                                                            │
       │◀══════════════════ PATH A ════════════════════════════════│
       │   4. HA ESPHome integration connects TO Voice PE          │
       │      Route: HA VM net2 (86.22) → vmbr2 → Flint3 → 86.10   │
       │                                                            │
       │   5. Connected! LED: Solid (ready)                        │


VOICE INTERACTION:
══════════════════
  Voice PE                                                    Home Assistant
       │                                                            │
       │   6. Wake word detected ("Hey Jarvis")                    │
       │══════════════════ PATH A ════════════════════════════════►│
       │      Speech audio streamed via ESPHome API :6053          │
       │                                                            │
       │                                     7. STT (Whisper)      │
       │                                     8. Intent processing  │
       │                                     9. Generate TTS       │
       │                                                            │
       │◀═════════════════ PATH A ═════════════════════════════════│
       │      HA sends TTS URL: http://192.168.1.122:8123/api/tts_proxy/xxx.flac
       │                                                            │
       │══════════════════ PATH B ════════════════════════════════►│
       │  10. Voice PE fetches audio via HTTP                      │
       │      Route: 86.10 → Google WiFi → ISP → pve socat → HA   │
       │                     (86.1)      (1.254) (1.122:8123)      │
       │                                                            │
       │  11. Play audio on speaker                                │


TWO PATHS MUST WORK:
════════════════════
┌────────────────┐                              ┌────────────────┐
│                │◀════════ PATH A ═════════════│                │
│   Voice PE     │      ESPHome API :6053       │ Home Assistant │
│  192.168.86.10 │      (HA initiates)          │ 192.168.4.240  │
│                │══════════ PATH B ═══════════▶│                │
└────────────────┘   HTTP :8123 via socat       └────────────────┘
                     (Voice PE initiates)

PATH A: HA → Voice PE (ESPHome control + audio streaming)
         HA VM net2 (86.22) → vmbr2 → Flint3 bridge → Voice PE :6053

PATH B: Voice PE → HA (TTS audio fetch)
         Voice PE → Google WiFi → ISP Router → pve socat proxy → HA
         (86.10)      (86.1)       (1.254)     (1.122:8123)   (4.240:8123)
```

**Key insights**:
1. HA initiates the ESPHome connection TO Voice PE (PATH A)
2. Voice PE fetches TTS audio FROM HA via socat proxy (PATH B)
3. If Voice PE IP changes, PATH A fails (HA has old IP)
4. If socat proxy is down, PATH B fails (TTS audio won't play)

## Common Issues & Fixes

### 1. PATH A Failure: IP Address Changed (DHCP)

**Symptom**: Voice PE boots, connects to WiFi, but HA never connects. LED shows "waiting" pattern (blue twinkle).

**What's broken**: HA's ESPHome integration tries to connect to old IP, fails.

**Diagnosis**:
```bash
# Check current IP via mDNS
ping home-assistant-voice-09f5a3.local

# Compare with what HA expects
scripts/haos/get-entity-state.sh | grep -i voice
```

**Fix**: Set static IP in ESPHome config:
```yaml
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  manual_ip:
    static_ip: 192.168.86.10
    gateway: 192.168.86.1
    subnet: 255.255.255.0
    dns1: 192.168.86.1
```

Then flash:
```bash
scripts/voice-pe/docker-compile.sh
scripts/voice-pe/usb-flash-esptool.sh
```

### 2. PATH A Failure: ESPHome Integration Lost Device

**Symptom**: Device online but no entities in HA.

**What's broken**: HA doesn't know about the device or has wrong IP cached.

**Fix**:
1. HA → Settings → Devices & Services → ESPHome
2. If device shows "offline", click Configure → Update host
3. Or: Remove integration, re-add with correct IP

### 3. PATH A Failure: WiFi Connection Failed

**Symptom**: Device boots but never gets IP. Can't even start.

**Diagnosis**:
```bash
scripts/voice-pe/serial-monitor-timeout.sh /dev/cu.usbmodem12201 60 "wifi|connect|fail"
```

**Fix**: Check WiFi credentials in `secrets.yaml`, verify 2.4GHz network (ESP32 doesn't support 5GHz).

### 4. PATH A Failure: API Port Not Reachable

**Symptom**: Device has IP, ping works, but port 6053 closed.

**What's broken**: ESPHome API server not running on device.

**Diagnosis**:
```bash
nc -zv 192.168.86.10 6053
```

**Fix**: Check ESPHome config has `api:` section, check serial logs for errors.

### 5. PATH B Failure: socat Proxy Down

**Symptom**: Voice PE connects, wake word works, speech recognized, but NO audio response.

**What's broken**: Voice PE can't fetch TTS audio from HA.

**Diagnosis**:
```bash
# Check socat service on pve
ssh root@pve.maas "systemctl status ha-proxy"

# Check if proxy port is listening
ssh root@pve.maas "ss -tlnp | grep 8123"

# Test proxy from your Mac (on Google WiFi)
curl -s --max-time 3 http://192.168.1.122:8123/ | head -1
```

**Fix**:
```bash
ssh root@pve.maas "systemctl restart ha-proxy"
```

### 6. PATH B Failure: HA Internal URL Misconfigured

**Symptom**: Voice PE connects, but TTS fails with URL errors in logs.

**What's broken**: HA tells Voice PE to fetch audio from unreachable IP (4.240 instead of 1.122).

**Diagnosis**: Check serial logs for TTS URL:
```bash
scripts/voice-pe/serial-monitor-timeout.sh /dev/cu.usbmodem12201 60 "tts_proxy"
```

If URL shows `192.168.4.240` instead of `192.168.1.122`, HA is misconfigured.

**Fix**: In HA → Settings → System → Network → Home Assistant URL:
- Set **Local network** to: `http://192.168.1.122:8123`

### 7. USB Not Detected

**Symptom**: Can't flash or see serial logs.

**Diagnosis**:
```bash
ls /dev/cu.usb*
```

**Fix**:
- Try different USB cable (some are charge-only)
- Try different USB port
- Hold BOOT button while plugging in for bootloader mode

## Serial Log Patterns

### Healthy Boot
```
[I][wifi:1079]: Connected
[C][wifi:834]:   IP Address: 192.168.86.28
[I][api:102]: Client 'Home Assistant 2024.x.x' connected
[I][voice_assistant:...]: Starting voice assistant
```

### IP Changed Problem
```
[I][wifi:1079]: Connected
[C][wifi:834]:   IP Address: 192.168.86.XX    ← Different IP!
[D][api:...]: Waiting for client...           ← Never connects
```

### WiFi Problem
```
[W][wifi:...]: Can't connect to SSID
[I][wifi:...]: Starting WiFi AP fallback
```

## Diagnostic Scripts

| Script | Purpose |
|--------|---------|
| `diagnose-connectivity.sh` | Full connectivity diagnosis |
| `serial-monitor-timeout.sh` | Capture boot logs with timeout |
| `check-entities.sh` | List Voice PE entities in HA |
| `test-led-color.sh` | Test LED control from HA |
| `reload-esphome-entry.sh` | Reload ESPHome integration |

## LED Status Indicators

| Pattern | Meaning |
|---------|---------|
| Blue twinkle | Waiting for HA connection |
| Solid blue | Connected, idle |
| Green pulse | Listening for wake word |
| Yellow | Processing speech |
| Red | Error state |

## Recovery Procedure

If device is completely unresponsive:

1. **Factory reset via USB**:
   ```bash
   # Hold BOOT button, plug USB, release after 3s
   scripts/voice-pe/usb-flash-esptool.sh --erase-all
   scripts/voice-pe/usb-flash-esptool.sh
   ```

2. **Re-adopt in HA**:
   - HA → Settings → Devices → Add Integration → ESPHome
   - Enter: `home-assistant-voice-09f5a3.local:6053`

## Prevention

1. **Always use static IP** in production
2. **Document the IP** in this runbook
3. **DHCP reservation** as backup (router config)

## Current Configuration

- **Hostname**: `home-assistant-voice-09f5a3`
- **Static IP**: `192.168.86.28`
- **API Port**: `6053`
- **WiFi SSID**: `wiremore2`
- **MAC**: `20:F8:3B:09:F5:A3`

## Related Docs

- [ESPHome Voice PE Config](../../scripts/voice-pe/README.md)
- [Home Assistant Integration](./ha-esphome-integration.md)
