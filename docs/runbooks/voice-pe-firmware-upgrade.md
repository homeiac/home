# Runbook: Voice PE Custom Firmware Build, Flash, and Debug

**Last Updated**: 2026-02-24
**Owner**: Homelab

## Overview

The Voice PE runs custom ESPHome firmware built from the upstream `home-assistant-voice-pe` package plus our local additions. The firmware is compiled on Mac via Docker, and flashed to the device via USB. This runbook covers the full build-flash-debug cycle, including every issue encountered during the 25.11.0 → 25.12.4 upgrade.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Firmware Build Pipeline                                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  voice-pe-config.yaml ──────┐                                   │
│    (our custom additions)   │                                   │
│                             ├──→ ESPHome Docker ──→ firmware.bin│
│  upstream package ──────────┘    (compile)                      │
│    (github://esphome/                                           │
│     home-assistant-voice-pe                                     │
│     @<version>)                                                 │
│                                                                 │
│  secrets.yaml ──────────────→ WiFi creds, API key               │
│    (SOPS encrypted in git)     (decrypted for build)            │
│                                                                 │
│  Flash: USB-C ──→ esptool ──→ ESP32-S3                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Custom Additions (preserved across upgrades)

Our `voice-pe-config.yaml` extends the upstream package with:

| Addition | Purpose |
|----------|---------|
| LED ring effects (Progress 1-6, Waiting, Approved, Rejected) | Claude Code approval UI |
| API actions (`set_led_segment`, `clear_leds`) | Per-LED control from HA |
| Dial events (`esphome.voice_pe_dial`) | Physical approve/reject for Claude |
| Static IP (`192.168.86.10`) | HA integration requires stable IP |
| WiFi tuning (`power_save_mode: none`, `fast_connect: true`) | Prevent timeout issues |
| `manual_ip` block | Static IP outside Google WiFi DHCP range |

**CRITICAL**: The `manual_ip` block MUST be in `voice-pe-config.yaml`. Without it, the device gets a DHCP address and HA can't find it. This was missing in the initial 25.12.4 upgrade and caused the device to appear "unavailable".

---

## Pre-flight Checklist

- [ ] Docker Desktop is running (`docker info`)
- [ ] `scripts/voice-pe/secrets.yaml` exists (SOPS encrypted)
- [ ] SOPS age key exists at `~/.config/sops/age/keys.txt`
- [ ] Voice PE is reachable: `ping 192.168.86.10`
- [ ] USB-C cable available for flashing
- [ ] Note current firmware version

---

## Upgrade Procedure

### 1. Update the version pin

```bash
cd scripts/voice-pe
```

Edit `voice-pe-config.yaml`:

```yaml
packages:
  Nabu Casa.Home Assistant Voice PE: github://esphome/home-assistant-voice-pe/home-assistant-voice.yaml@<NEW_VERSION>
```

### 2. Update the ESPHome Docker image

The Docker image version should match the firmware version:

```bash
# Edit ESPHOME_IMAGE in both scripts:
#   scripts/voice-pe/docker-compile.sh
#   scripts/voice-pe/ota-upload-long-timeout.sh
ESPHOME_IMAGE="ghcr.io/esphome/esphome:<NEW_VERSION>"
```

### 3. Decrypt secrets

The `secrets.yaml` is SOPS-encrypted in git. The Docker container can't decrypt it, so you must decrypt before compiling:

```bash
cd scripts/voice-pe

# Decrypt in place
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops -d secrets.yaml > secrets.decrypted.yaml
cp secrets.yaml secrets.yaml.sops.bak
cp secrets.decrypted.yaml secrets.yaml
rm secrets.decrypted.yaml
```

**IMPORTANT**: The `docker-compile.sh` script tries to auto-decrypt, but if it fails, do it manually as above.

**IMPORTANT**: After building, restore the encrypted version:

```bash
cp secrets.yaml.sops.bak secrets.yaml
rm secrets.yaml.sops.bak
```

### 4. Compile the firmware

```bash
./docker-compile.sh
```

- First build: ~10 minutes (pulls upstream package, compiles everything)
- Subsequent builds: ~30-60 seconds (cached)
- Output: `.esphome/build/home-assistant-voice-09f5a3/.pioenvs/home-assistant-voice-09f5a3/firmware.factory.bin`

### 5. Flash via USB

```bash
# 1. Connect Voice PE to Mac via USB-C (no boot mode needed for JTAG devices)
# 2. Verify USB detected:
ls /dev/cu.usbmodem*

# 3. Flash:
./usb-flash-esptool.sh
```

The device reboots automatically after flashing (~20-30 seconds to WiFi).

### 6. Run acceptance test

```bash
# Wait 20-30 seconds for device to boot and connect to WiFi
scripts/voice-pe/test-firmware-upgrade.sh
```

Tests: device reachable, HA sees device, satellite idle, LED ring on/off, LED auto-off after announce, Ollama integration loaded.

**Manual test**: Say "OK Nabu, what time is it?" and verify:
- Blue LED comes on while processing
- Response is spoken
- LED turns off automatically after response

### 7. Restore encrypted secrets

```bash
cd scripts/voice-pe
cp secrets.yaml.sops.bak secrets.yaml
rm secrets.yaml.sops.bak
```

### 8. If tests fail — rollback

1. Edit `voice-pe-config.yaml` — change version pin back to previous version
2. Update Docker image versions in both scripts
3. Decrypt secrets (step 3), recompile (step 4), and USB flash (step 5) again

---

## Debugging

### Problem: Compilation fails with "SSID can't be longer than 32 characters"

**Cause**: `secrets.yaml` is still SOPS-encrypted. The encrypted blobs are long strings that ESPHome rejects.

**Fix**: Decrypt secrets before compiling (see step 3 above).

```bash
# Check if secrets are encrypted:
head -1 secrets.yaml
# If you see ENC[AES256_GCM,... → encrypted, needs decryption
# If you see wifi_ssid: <plaintext> → already decrypted, OK
```

### Problem: Device not connecting to WiFi after flash

**Diagnosis**: Enable USB serial logging and read boot logs.

```yaml
# Add to voice-pe-config.yaml temporarily:
logger:
  hardware_uart: USB_SERIAL_JTAG
```

Then recompile, reflash, and read logs:

```bash
# Recompile + flash
./docker-compile.sh && ./usb-flash-esptool.sh

# Wait 5-10 seconds, then read serial logs:
python3 -c "
import serial, time
s = serial.Serial('/dev/cu.usbmodem112201', 115200, timeout=1)
start = time.time()
while time.time() - start < 60:
    data = s.read(4096)
    if data:
        print(data.decode('utf-8', errors='replace'), end='', flush=True)
s.close()
"
```

**What to look for in logs**:
- `Starting fast_connect` → WiFi attempting to connect
- `IP Address: X.X.X.X` → Got an IP (check if static or DHCP)
- `Connected: NO` with `Subnet: 0.0.0.0` → WiFi associated but no IP
- No WiFi logs at all → Wrong SSID/password

**Remove the logger override** after debugging — it's not needed for normal operation.

### Problem: Device gets DHCP address instead of static IP

**Cause**: Missing `manual_ip` block in `voice-pe-config.yaml`.

**Symptom**: Serial logs show `IP Address: 192.168.86.244` (or similar DHCP address) instead of `192.168.86.10`. HA shows device as "unavailable" because it's looking for `.10`.

**Fix**: Ensure `voice-pe-config.yaml` has:

```yaml
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  power_save_mode: none
  fast_connect: true
  manual_ip:
    static_ip: 192.168.86.10
    gateway: 192.168.86.1
    subnet: 255.255.255.0
    dns1: 192.168.86.1
```

**Why this happens**: The upstream package doesn't set a static IP. Our config overrides the `wifi:` section, but if `manual_ip` is missing, DHCP takes over.

### Problem: No serial output on USB

**Cause**: ESP32-S3 USB JTAG doesn't output logs by default — the ESPHome logger defaults to UART0.

**Fix**: Add `logger: hardware_uart: USB_SERIAL_JTAG` to config, recompile, and reflash.

**Alternative**: If you just need to know if WiFi connected:
```bash
# Just ping the expected static IP:
ping 192.168.86.10

# Or check HA:
bash -c 'source scripts/lib-sh/ha-api.sh && ha_get_state "assist_satellite.home_assistant_voice_09f5a3_assist_satellite" | jq .state'
```

### Problem: USB device not detected

**Symptom**: `ls /dev/cu.usbmodem*` returns nothing.

**Fixes**:
1. Try a different USB-C cable (some are charge-only)
2. Try a different USB port on the Mac
3. For boot mode flash: hold center button while plugging in USB
4. Check system: `system_profiler SPUSBDataType | grep -A5 "Espressif"`

### Problem: HA shows device "unavailable" after flash

**Check these in order**:

```bash
# 1. Is device on the network?
ping 192.168.86.10

# 2. If not pingable, is it on a DHCP address?
#    Check router or use serial logs to find actual IP

# 3. If pingable but HA says unavailable, reload ESPHome integration:
bash -c 'source scripts/lib-sh/ha-api.sh && ha_api_get "config/config_entries/entry"' | \
  jq '.[] | select(.domain == "esphome") | {entry_id, state, title}'

# 4. If state is setup_error, reload:
# Use the entry_id from above
bash -c 'source scripts/lib-sh/ha-api.sh && ha_api_post "config/config_entries/entry/<ENTRY_ID>/reload" "{}"'
```

### Problem: LED ring stuck on after voice interaction

**Immediate fix**:
```bash
scripts/haos/reset-voice-pe.sh
```
This announces + explicitly turns off the LED ring.

**Root cause**: Firmware bug in versions < 25.12.4 where `voice_assistant_phase` doesn't reset to idle. Fixed in 25.12.4 ([#382](https://github.com/esphome/home-assistant-voice-pe/issues/382)).

### Problem: docker-compile.sh reports ERROR but compilation succeeded

**Cause**: The old script used `timeout` wrapper which returns non-zero even on success.

**Fix**: Already fixed — the script now captures the Docker exit code directly. If you see `[SUCCESS]` in the output, the build worked regardless of the script's exit code.

---

## Network Architecture

```
┌──────────────────────────────────────────────────────┐
│  Voice PE Network                                     │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Voice PE (192.168.86.10, Google WiFi)               │
│      │                                               │
│      ├──→ HA ESPHome API (:6053)                     │
│      │      HA at 192.168.4.240 (homelab VLAN)       │
│      │      Cross-subnet via router                  │
│      │                                               │
│      └──→ HA TTS fetch (HTTP)                        │
│             Via socat proxy at 192.168.1.122:8123     │
│                                                      │
│  DHCP range: 192.168.86.20-254                       │
│  Static IP:  192.168.86.10 (outside DHCP range)      │
│  Gateway:    192.168.86.1 (Google WiFi)               │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**CRITICAL**: The static IP `192.168.86.10` is outside the DHCP range. If the device gets a DHCP address, HA loses contact because the ESPHome integration caches the IP.

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/voice-pe/voice-pe-config.yaml` | Custom firmware config (version pin + our additions) |
| `scripts/voice-pe/secrets.yaml` | API key, WiFi creds (SOPS encrypted, NOT committed decrypted) |
| `scripts/voice-pe/docker-compile.sh` | Compile firmware via Docker |
| `scripts/voice-pe/usb-flash-esptool.sh` | USB flash via esptool |
| `scripts/voice-pe/ota-upload-long-timeout.sh` | OTA flash with extended timeout |
| `scripts/voice-pe/test-firmware-upgrade.sh` | Acceptance test (8 checks) |
| `scripts/voice-pe/serial-monitor.sh` | USB serial log reader |
| `scripts/haos/reset-voice-pe.sh` | Reset stuck satellite + LED ring |

## Version History

| Date | From | To | Reason | Issues Hit |
|------|------|----|--------|------------|
| 2026-02-24 | 25.11.0 | 25.12.4 | Fix LED stuck-on bug (#382) | SOPS decrypt, missing manual_ip, no serial logs |

## Lessons Learned (2026-02-24 Upgrade)

1. **SOPS secrets must be decrypted before Docker compile** — Docker can't access the age key. The compile will succeed but bake in the encrypted blob as the SSID, which is obviously wrong.
2. **`manual_ip` is NOT in the upstream package** — if your config doesn't include it, the device gets a DHCP address and HA loses it.
3. **ESP32-S3 USB JTAG doesn't output logs by default** — you must add `logger: hardware_uart: USB_SERIAL_JTAG` to get serial debug output.
4. **`fast_connect: true` saves the BSSID** — the device connects faster but if you move the device to a different AP, clear the saved BSSID.
5. **Always run the acceptance test** — the 8-check script catches issues (wrong IP, HA unavailable, LED stuck) before you walk away.
6. **The compile output `[SUCCESS]` is the truth** — ignore wrapper script exit codes, check for `[SUCCESS]` or `[FAILED]`.

## Related

- **Voice pipeline runbook**: `docs/runbooks/voice-pe-ollama-diagnosis-runbook.md`
- **Connectivity runbook**: `docs/runbooks/voice-pe-connectivity.md`
- **LED stuck-on fix**: `github.com/esphome/home-assistant-voice-pe/issues/382`
- **Upstream releases**: `github.com/esphome/home-assistant-voice-pe/releases`
- **IP mismatch RCA**: `docs/source/md/rca-voice-pe-esphome-ip-mismatch-2025-12-22.md`
- **ESPHome modification guide**: `scripts/claudecodeui/voice-pe/ESPHOME-MODIFICATION-GUIDE.md`

**Tags**: voice-pe, esphome, firmware, upgrade, OTA, USB, flash, LED, WiFi, static-ip, SOPS, debug, serial, runbook
