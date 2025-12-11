# LED Notification System Fix

## Problem Summary

The LED stays on after user asks "what's my notification" via Ollama conversation agent.

## Root Cause Analysis

### What Works
1. **Automation `automation.clear_doorbell_notification`**: ✅ WORKING
   - Trigger: When `input_boolean.has_pending_notification` turns OFF
   - Action: Turns off LED and clears notification messages
   - Status: Enabled and functioning correctly

2. **LED Control**: ✅ WORKING
   - LED turns off immediately when boolean is turned off manually
   - Tested successfully with `test-led-off.sh`

### What Doesn't Work
**Script `script.get_pending_notification`**: ❌ BLOCKING

The script sequence:
1. Announces message via `assist_satellite.announce`
2. Turns off `input_boolean.has_pending_notification`

**The Problem**: Step 1 (`assist_satellite.announce`) is a BLOCKING action that doesn't complete, preventing step 2 from ever running.

**Evidence**:
- Script state shows `"state": "on"` with `"current": 1` (still running)
- Last triggered: 2025-12-08T03:34:32 but never completed
- The boolean never gets turned off because the script hangs

## Investigation Results

### Current State (as of investigation)
```bash
# Script is hung
$ curl -H "Authorization: Bearer $HA_TOKEN" \
  $HA_URL/api/states/script.get_pending_notification | jq '.state, .attributes.current'
"on"
1

# Boolean is still ON (script never turned it off)
$ curl -H "Authorization: Bearer $HA_TOKEN" \
  $HA_URL/api/states/input_boolean.has_pending_notification | jq '.state'
"on"

# LED is ON (automation can't trigger because boolean is still ON)
$ curl -H "Authorization: Bearer $HA_TOKEN" \
  $HA_URL/api/states/light.home_assistant_voice_09f5a3_led_ring | jq '.state'
"on"
```

### Manual Test Confirms Automation Works
```bash
# When we manually turn off the boolean...
$ curl -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_id": "input_boolean.has_pending_notification"}' \
  $HA_URL/api/services/input_boolean/turn_off

# ...the LED turns off within 2 seconds (automation triggered successfully)
$ curl -H "Authorization: Bearer $HA_TOKEN" \
  $HA_URL/api/states/light.home_assistant_voice_09f5a3_led_ring | jq '.state'
"off"
```

## Solution

### Option 1: Fix the Script (Recommended)

Replace the current script configuration with a non-blocking version:

**File**: `fixed-script.yaml`

Key changes:
1. Wrap `assist_satellite.announce` in a `parallel` block (non-blocking)
2. Turn off boolean immediately after starting announcement
3. Change mode from `single` to `restart` (allows interruption)

**How to apply**:
1. Copy contents of `fixed-script.yaml` to your Home Assistant configuration
2. Add under `script:` section in `configuration.yaml` or `scripts.yaml`
3. Reload scripts via Developer Tools → YAML → Reload Scripts

### Option 2: Workaround - Alternative Intent Response

Instead of using `script.get_pending_notification`, create a custom intent response that:
1. Reads the notification message
2. Immediately calls a service to turn off the boolean

This avoids the blocking issue entirely by not using `assist_satellite.announce` in a script context.

### Option 3: Timeout Wrapper (Quick Fix)

Add a timeout to the script:
```yaml
- timeout: "00:00:05"  # 5 second timeout
  action: assist_satellite.announce
  ...
```

This forces the script to continue after 5 seconds even if announcement hasn't completed.

## Testing

### Test Script: `test-led-off.sh`

Comprehensive test that simulates the full notification flow:

```bash
./scripts/package-detection/test-led-off.sh
```

**What it tests**:
1. Sets notification message
2. Turns on LED and boolean (like package detection automation)
3. Waits 5 seconds
4. Turns off boolean (simulating acknowledgment)
5. Verifies LED turned off via automation

**Expected output**:
```
=== Testing LED Notification Flow ===
...
✓ LED confirmed OFF - Automation working correctly!
=== Test Complete - All checks passed! ===
```

## Files Created

1. **test-led-off.sh**: Test script for LED notification flow
2. **fixed-script.yaml**: Fixed script configuration (non-blocking)
3. **fix-script-config.json**: JSON version of fix (for API updates)
4. **fix-notification-script.sh**: Shell script to apply fix via API
5. **LED-NOTIFICATION-FIX.md**: This documentation

## Recommendations

1. **Immediate**: Apply Option 1 (fixed script) to resolve blocking issue
2. **Testing**: Run `test-led-off.sh` to verify fix works
3. **Monitoring**: Check script state after user asks for notifications
4. **Long-term**: Consider moving notification logic to intent responses instead of scripts

## Environment Details

- **Home Assistant URL**: http://192.168.4.240:8123
- **Token Location**: `/Users/10381054/code/home/proxmox/homelab/.env` (HA_TOKEN)
- **Voice Device**: Home Assistant Voice 09f5a3
- **LED Entity**: `light.home_assistant_voice_09f5a3_led_ring`
- **Package Detection**: Uses Reolink doorbell + LLM Vision analysis
