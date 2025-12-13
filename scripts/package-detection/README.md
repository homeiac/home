# Package Detection System

Rock-solid package delivery detection for homelab using:
- **Reolink Doorbell** - Person detection sensor
- **LLM Vision** - Ollama llava:7b for package confirmation (zero false alarms)
- **Voice PE** - LED ring visual notification (stays on until acknowledged)
- **HA Companion** - Phone push notifications

## Current Version: v3.0

**Key behavior**: Alerts ONLY when a package is detected. No notifications for person-only events.

## Architecture

```
Person detected → Reolink Doorbell → person_arrived trigger
                         ↓
                  Wait 2s, capture snapshot
                         ↓
              LLM Vision (llava:7b) → Identify visitor (silent)
                         ↓
                  Person leaves → person_left trigger
                         ↓
                  Capture snapshot
                         ↓
              LLM Vision (llava:7b) → "Is there a package?"
                         ↓
                    YES? ───────────────────┐
                         ↓                  ↓
              Voice PE LED (blue)    Phone notification
              (stays on until        (with camera image)
               voice acknowledgment)
```

## OBSOLETE: Legacy LLM Vision Automations

The following automations have been **DISABLED** (2025-12-12):
- `automation.llm_vision` - Spammed on every motion event
- `automation.ai_event_summary_v1_5_0` - Spammed on every motion event

These were blueprint automations from the LLM Vision HACS integration that triggered
on ALL motion, not just person detection. They've been replaced by
`automation.package_delivery_detection` (v3) which only alerts on packages.

To re-enable if needed:
```bash
./disable-legacy-automations.sh  # Shows current state, can be modified to re-enable
```

## Prerequisites

| Component | Status | Notes |
|-----------|--------|-------|
| Frigate 0.16 | 🔄 Upgrading | Optional - can use Reolink directly |
| LLM Vision | ✅ Ready | Ollama provider configured |
| llava:7b | ✅ Ready | Vision model (3.8GB VRAM) |
| Voice PE LED | ✅ Ready | `light.home_assistant_voice_09f5a3_led_ring` |
| Phone notify | ✅ Working | `notify.mobile_app_pixel_10_pro` |
| Doorbell | ✅ Ready | `camera.reolink_doorbell` |

## Performance Results

| Metric | Value |
|--------|-------|
| **Inference Time** | 1.8-2.0 seconds |
| **GPU Memory** | 6.3GB / 8GB (llava:7b loaded) |
| **GPU Utilization** | 0% idle, spikes during inference |
| **Pod CPU** | ~1m (minimal) |
| **Pod Memory** | ~1GB |

**Notes:**
- llava:7b uses 3.8GB VRAM
- Model swapping (qwen↔llava) adds ~3-5 seconds
- Frigate snapshot is preferred (pre-filtered by Coral TPU)
- Direct camera snapshot works but slightly slower

## Scripts

### Check Prerequisites
```bash
./check-prerequisites.sh
```

### Test Phone Notification
```bash
./test-notification.sh mobile_app_pixel_10_pro
```

### Test Voice PE LED
```bash
./test-voice-pe-led.sh blue 5    # Blue for 5 seconds
./test-voice-pe-led.sh red 10    # Red for 10 seconds
./test-voice-pe-led.sh off       # Turn off
```

### Test LLM Vision
```bash
./test-llm-vision.sh                              # Use default doorbell snapshot
./test-llm-vision.sh image.reolink_doorbell_person  # Specific image entity
```

### Check LLM Vision Config
```bash
./check-llmvision-config.sh
```

### Pull Vision Model
```bash
./pull-vision-model.sh llava:7b     # Default
./pull-vision-model.sh moondream    # Alternative (smaller)
```

### List Cameras
```bash
./list-cameras.sh
```

## Installation

### 1. Deploy Automation v3

```bash
./deploy-automation-v3.sh
```

This deploys `automation-package-detection-v3.yaml` via the HA API and reloads automations.

### 2. Disable Legacy Automations (if present)

```bash
./disable-legacy-automations.sh
```

Disables the spammy `automation.llm_vision` and `automation.ai_event_summary_v1_5_0`.

### 3. Update Entity Names (when Frigate 0.16 ready)

Edit the automation to match your new Frigate camera names:
```yaml
# Trigger entity
entity_id: binary_sensor.YOUR_CAMERA_person_occupancy

# Image entity for LLM analysis
image_entity: image.YOUR_CAMERA_person
```

### 3. Configure Zone (after Frigate 0.16)

Add porch zone in Frigate config:
```yaml
cameras:
  reolink_doorbell:
    zones:
      porch:
        coordinates: 0.1,0.5,0.9,0.5,0.9,1.0,0.1,1.0
        objects:
          - person
```

## Tuning

### False Alarm Prevention

The automation has multiple safeguards:

1. **Time window**: 8am-9pm only (configurable)
2. **LLM confirmation**: Must explicitly say "YES"
3. **30-minute cooldown**: No re-alerts for same delivery
4. **Strict prompt**: Binary YES/NO answer

### Adjusting Sensitivity

**More sensitive** (catch more packages):
- Lower cooldown to 15 minutes
- Expand time window
- Add alternative triggers (motion)

**Less sensitive** (fewer false alarms):
- Increase cooldown to 60 minutes
- Add zone requirement in Frigate
- Require higher confidence

## Troubleshooting

### No notifications
1. Run `./test-notification.sh` to verify push works
2. Check HA logs: Developer Tools → Logs → filter "llmvision"
3. Verify automation is enabled

### LLM Vision errors
1. Run `./check-llmvision-config.sh` to verify config
2. Check Ollama: `curl http://192.168.4.81/api/tags`
3. Test directly: `./test-llm-vision.sh`

### LED not working
1. Run `./test-voice-pe-led.sh blue 3`
2. Check entity exists: `./check-prerequisites.sh`
3. Verify Voice PE is online in HA

### LED stays on after acknowledgment
**Problem**: LED stays on after asking "what's my notification"

**Quick fix**:
```bash
./clear-notification-workaround.sh
```

**Permanent fix**: See `LED-NOTIFICATION-FIX.md` and `INVESTIGATION-SUMMARY.md`

**Test notification flow**:
```bash
./test-led-off.sh
```

**Root cause**: The `script.get_pending_notification` uses a blocking `assist_satellite.announce` action that doesn't complete, preventing the notification boolean from being turned off. Fix by wrapping the announcement in a `parallel` block (see `fixed-script.yaml`).

## Files

```
scripts/package-detection/
├── README.md                          # This file
│
├── # Automation (v3 - current)
├── automation-package-detection-v3.yaml  # Package-only alerts
├── deploy-automation-v3.sh               # Deploy v3 via API
├── disable-legacy-automations.sh         # Disable spammy LLM Vision automations
│
├── # Debugging & Investigation
├── investigate-package-detection.sh      # Full system verification
├── get-automation-traces.sh              # Get HA automation traces
├── find-all-doorbell-automations.sh      # Find all related automations
├── timeline.sh                           # Build event timeline
├── check-recent-alerts.sh                # Check recent alert activity
│
├── # Component Tests
├── check-prerequisites.sh             # Verify all components
├── check-llmvision-config.sh          # Check LLM Vision setup
├── list-cameras.sh                    # List camera entities
├── pull-vision-model.sh               # Pull Ollama models
├── test-llm-vision.sh                 # Test LLM Vision analysis
├── test-notification.sh               # Test phone notifications
├── test-voice-pe-led.sh               # Test Voice PE LED
│
├── # LED Notification Fix
├── LED-NOTIFICATION-FIX.md            # LED acknowledgment issue analysis
├── INVESTIGATION-SUMMARY.md           # Complete investigation findings
├── test-led-off.sh                    # Test notification LED flow
├── clear-notification-workaround.sh   # Emergency notification clear
├── fixed-script.yaml                  # Fixed script configuration
└── fix-notification-script.sh         # Automated fix application
```

## Related Documentation

- **Blog Post**: `docs/source/md/blog-package-detection-llm-vision.md`
- Voice PE Setup: `docs/source/md/voice-pe-complete-setup-guide.md`
- LLM Vision Reference: `docs/reference/llm-vision-complete-reference.md`
- Frigate Integration: `docs/source/md/frigate-homeassistant-integration-guide.md`

## GitHub Issue

Tracking: https://github.com/homeiac/home/issues/167
