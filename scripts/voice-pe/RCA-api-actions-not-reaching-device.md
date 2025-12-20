# RCA: ESPHome API Actions Not Reaching Device

**Date**: 2025-12-19
**Component**: Voice PE ESPHome firmware
**Status**: RESOLVED

## Symptom

After adding custom API actions (`set_led_segment`, `clear_leds`) to Voice PE firmware:
- Firmware compiled successfully
- HA registered the services correctly
- Service calls returned HTTP 200 OK
- **But LEDs never changed** - actions not reaching device

Meanwhile, named effects via `light.turn_on` worked fine.

## Root Cause

**HA ESPHome integration maintains persistent API connection.** After flashing new firmware:
1. Device reboots with new API actions
2. HA reconnects automatically
3. HA discovers services (they appear in service list)
4. **BUT**: HA's API client uses stale connection state that doesn't forward action calls

## Resolution

**Reload the ESPHome config entry after flashing new firmware:**

```bash
scripts/voice-pe/reload-esphome-entry.sh
```

This forces HA to disconnect and re-establish fresh API connection.

## Workflow After Firmware Update

```bash
# 1. Compile and upload
./docker-compile.sh voice-pe-config.yaml run

# 2. Reload HA ESPHome entry
./reload-esphome-entry.sh

# 3. Wait for reconnection
sleep 15

# 4. Test API action
./test-led-color.sh red
```

## Lessons Learned

1. **Services appearing in HA ≠ working** - the integration connection may be stale
2. **Always reload config entry after adding new API actions**
3. **Effects work via existing light component** - API actions need fresh connection
