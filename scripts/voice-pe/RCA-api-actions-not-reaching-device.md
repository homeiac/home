# RCA: ESPHome API Actions Not Working

**Date**: 2025-12-19
**Component**: Voice PE ESPHome firmware
**Status**: RESOLVED

## Symptoms

Two separate issues when adding API actions (`set_led_segment`, `clear_leds`):

1. **Linker error** during compilation:
   ```
   undefined reference to 'get_execute_arg_value<long>'
   ```

2. **Actions not reaching device** after successful compilation:
   - HA registered the services correctly
   - Service calls returned HTTP 200 OK
   - But LEDs never changed

---

## Issue 1: Linker Error

### Wrong Diagnosis (WASTED TIME)

Claude's analysis claimed:
- "ESPHome has a bug - missing template specialization for `long` type"
- "On Xtensa (ESP32-S3), `int32_t` is `long`, not `int`"
- "Need to patch `user_services.cpp` to add `long` specializations"
- Built custom Docker image with patch
- Suggested raising PR with ESPHome

**This was completely wrong.**

When testing the patch, got `redefinition error` - proving `int32_t == long` means the specialization already exists.

### Actual Cause

**Stale build cache.** ESPHome conditionally includes `user_services.cpp` only when API actions are defined. Previous builds cached state from when no actions existed.

### Actual Fix

```bash
rm -rf .esphome/build/home-assistant-voice-09f5a3/
./docker-compile.sh voice-pe-config.yaml run
```

Just clean the build cache. No patches needed. No ESPHome bugs.

---

## Issue 2: Actions Not Reaching Device

### Symptom

After successful compile and upload:
- Services appeared in HA (`esphome.home_assistant_voice_09f5a3_set_led_segment`)
- Service schema was correct
- API calls returned HTTP 200 OK
- **But device logs showed NO action execution**
- Meanwhile, effects via `light.turn_on` worked fine

### Root Cause

**HA ESPHome integration maintains persistent API connection.** After flashing new firmware:
1. Device reboots with new API actions
2. HA reconnects automatically
3. HA discovers services (they appear in service list)
4. **BUT**: HA's API client uses stale connection state that doesn't forward action calls

### Fix

**Reload the ESPHome config entry after flashing new firmware:**

```bash
scripts/voice-pe/reload-esphome-entry.sh
```

This forces HA to disconnect and re-establish fresh API connection.

---

## Correct Workflow After Adding API Actions

```bash
# 1. Clean build cache
rm -rf .esphome/build/home-assistant-voice-09f5a3/

# 2. Compile and upload
./docker-compile.sh voice-pe-config.yaml run

# 3. Reload HA ESPHome entry (CRITICAL!)
./reload-esphome-entry.sh

# 4. Wait for reconnection
sleep 15

# 5. Test API action
./test-led-color.sh red
```

---

## Lessons Learned

1. **Try simple fixes first** - clean build, restart, reload - before assuming framework bugs
2. **Don't trust "analysis" that requires patching upstream** - probably wrong
3. **Services appearing in HA ≠ working** - the integration connection may be stale
4. **Always reload config entry after adding new API actions**
5. **Build cache is a common culprit** - when changing ESPHome component structure, clean first

## Time Wasted

- ~2 hours building custom Docker image with wrong patch
- Should have just tried `rm -rf .esphome/build/` first
