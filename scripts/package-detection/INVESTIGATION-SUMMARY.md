# LED Notification Investigation Summary

**Date**: 2025-12-08
**Issue**: LED stays on after user asks "what's my notification" via Ollama

## Investigation Findings

### ✅ What's Working

1. **Automation `automation.clear_doorbell_notification`**
   - Status: Enabled and fully functional
   - Trigger: `input_boolean.has_pending_notification` turns OFF
   - Actions:
     - Turns off LED (`light.home_assistant_voice_09f5a3_led_ring`)
     - Clears notification message
     - Clears notification type
   - **Tested**: Manually turning off boolean immediately turns off LED
   - **Conclusion**: No issues with this automation

2. **Package Detection Flow**
   - `automation.package_delivery_detection` works correctly
   - Detects person at door → analyzes visitor → checks for package
   - When package detected:
     - Sets notification message
     - Turns on `has_pending_notification`
     - Turns on LED with blue pulse effect
     - Sends mobile notification

### ❌ What's Broken

**Script `script.get_pending_notification`**

**Current State**:
```json
{
  "state": "on",
  "current": 1,
  "last_triggered": "2025-12-08T03:34:32.529097+00:00"
}
```

**Problem**: The script has been hung since 03:34 AM

**Root Cause**: Sequential execution of blocking action

Current script sequence:
```yaml
1. assist_satellite.announce (BLOCKS HERE - never completes)
2. input_boolean.turn_off (NEVER REACHED)
```

The `assist_satellite.announce` action is blocking and not completing, preventing the boolean from ever being turned off, which prevents the automation from turning off the LED.

## Why the LED Stays On

**The Chain of Events**:
1. User asks "what's my notification" → triggers `script.get_pending_notification`
2. Script calls `assist_satellite.announce` to read the message
3. Announcement action BLOCKS and doesn't complete
4. Script never reaches the `input_boolean.turn_off` step
5. Boolean stays ON
6. Automation never triggers (it only triggers on boolean turning OFF)
7. LED stays ON

**The Fix**: Make announcement non-blocking so boolean gets turned off immediately

## Solution Implemented

### Fixed Script Configuration

**File**: `/Users/10381054/code/home/scripts/package-detection/fixed-script.yaml`

**Key Changes**:
1. Wrap announcement in `parallel` block → runs without blocking
2. Turn off boolean immediately after starting announcement
3. Change mode to `restart` → allows script to be interrupted

**Before** (blocking):
```yaml
sequence:
  - action: assist_satellite.announce  # BLOCKS HERE
  - action: input_boolean.turn_off     # Never reached
```

**After** (non-blocking):
```yaml
sequence:
  - parallel:
      - action: assist_satellite.announce  # Runs in background
  - action: input_boolean.turn_off           # Executes immediately
```

### How to Apply Fix

**Option 1: Via Home Assistant UI**
1. Go to Settings → Automations & Scenes → Scripts
2. Edit "Get Pending Notification" script
3. Replace with contents of `fixed-script.yaml`
4. Save

**Option 2: Via Configuration File**
1. Add/replace script in `scripts.yaml` or `configuration.yaml`
2. Reload scripts: Developer Tools → YAML → Reload Scripts

**Option 3: Via API** (if supported by your HA version)
```bash
./scripts/package-detection/fix-notification-script.sh
```

## Workaround Scripts Created

### 1. `test-led-off.sh`
Full end-to-end test of notification flow:
- Sets notification
- Turns on LED and boolean
- Simulates acknowledgment
- Verifies LED turns off via automation

**Usage**: `./scripts/package-detection/test-led-off.sh`

**Result**: ✅ All tests pass - automation works perfectly

### 2. `clear-notification-workaround.sh`
Emergency workaround to manually clear stuck notifications:
- Reads current notification
- Turns off boolean
- Triggers automation to clear LED
- Verifies LED turned off

**Usage**: `./scripts/package-detection/clear-notification-workaround.sh`

**Use When**: Script is hung and LED won't turn off

## Test Results

### Automation Test (Manual Boolean Toggle)
```bash
# Turn off boolean manually
curl -X POST ... input_boolean.turn_off

# Result: LED turned off within 2 seconds
✅ Automation works perfectly
```

### End-to-End Test (`test-led-off.sh`)
```
=== Testing LED Notification Flow ===
[1/6] Setting test notification message... ✓
[2/6] Turning on LED and has_pending_notification... ✓
[3/6] Waiting 1 second for states to settle... ✓
✓ LED confirmed ON
[4/6] Waiting 5 seconds... ✓
[5/6] Turning off has_pending_notification... ✓
[6/6] Waiting 3 seconds for automation to turn off LED... ✓
✓ LED confirmed OFF - Automation working correctly!
=== Test Complete - All checks passed! ===
```

### Workaround Test (`clear-notification-workaround.sh`)
```
=== Clearing Notification and LED ===
Current notification: [empty]
Turning off has_pending_notification... ✓
✓ LED is now OFF
✓ Notification cleared
Done!
```

## Current System State (After Investigation)

- **LED**: OFF ✅
- **has_pending_notification**: OFF ✅
- **Automation**: Enabled and working ✅
- **Script**: Still hung from earlier execution ⚠️ (will auto-clear on next HA restart)

## Recommendations

### Immediate Actions
1. ✅ **Done**: Created fixed script configuration (`fixed-script.yaml`)
2. ✅ **Done**: Created workaround script (`clear-notification-workaround.sh`)
3. ✅ **Done**: Created comprehensive test script (`test-led-off.sh`)
4. **TODO**: Apply fixed script configuration to Home Assistant

### Short-term
1. Test the fixed script with real voice interactions
2. Monitor script state after user asks for notifications
3. Verify LED turns off consistently

### Long-term
1. Consider moving notification logic to custom intent responses
2. Add timeout to announcement actions as safety measure
3. Implement monitoring for hung scripts

## Files Created

| File | Purpose |
|------|---------|
| `LED-NOTIFICATION-FIX.md` | Detailed problem analysis and solutions |
| `INVESTIGATION-SUMMARY.md` | This document - investigation findings |
| `fixed-script.yaml` | Fixed script configuration (non-blocking) |
| `fix-script-config.json` | JSON version for API updates |
| `fix-notification-script.sh` | Automated fix application script |
| `test-led-off.sh` | End-to-end notification flow test |
| `clear-notification-workaround.sh` | Emergency notification clear script |

## Environment Details

- **Home Assistant**: http://192.168.4.240:8123
- **Voice Device**: Home Assistant Voice 09f5a3
- **LED Entity**: `light.home_assistant_voice_09f5a3_led_ring`
- **Notification Boolean**: `input_boolean.has_pending_notification`
- **Notification Message**: `input_text.pending_notification_message`
- **Package Detection**: Reolink doorbell + LLM Vision (Ollama llava:7b)

## Next Steps

1. **Apply the fix**: Update script configuration with `fixed-script.yaml`
2. **Test**: Run `test-led-off.sh` after fix is applied
3. **Verify**: Ask voice assistant for notification and confirm LED turns off
4. **Monitor**: Check script state after each voice interaction for first few days
