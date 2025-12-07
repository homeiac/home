# Package Detection System

Rock-solid package delivery detection for homelab using:
- **Frigate 0.16+** - Person detection with Coral TPU
- **LLM Vision** - Ollama llava:7b for package confirmation (zero false alarms)
- **Voice PE** - LED ring visual notification
- **HA Companion** - Phone push notifications

## Architecture

```
Person at door → Frigate (Coral TPU) → Person detected
                         ↓
                  Capture snapshot
                         ↓
              LLM Vision (llava:7b) → "Is there a package?"
                         ↓
                    YES? ───────────────────┐
                         ↓                  ↓
              Voice PE LED pulse    Phone notification
              (blue, 30 seconds)    (with camera image)
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

### 1. Deploy Automation

Copy `automation-package-detection.yaml` content to Home Assistant:

**Option A: Via UI**
1. Settings → Automations → Create Automation
2. Switch to YAML mode (⋮ menu → Edit in YAML)
3. Paste the content

**Option B: Via File**
1. Copy to `/config/automations.yaml`
2. Reload automations: Developer Tools → YAML → Automations

### 2. Update Entity Names (when Frigate 0.16 ready)

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

## Files

```
scripts/package-detection/
├── README.md                          # This file
├── automation-package-detection.yaml  # Main HA automation
├── check-prerequisites.sh             # Verify all components
├── check-llmvision-config.sh          # Check LLM Vision setup
├── list-cameras.sh                    # List camera entities
├── pull-vision-model.sh               # Pull Ollama models
├── test-llm-vision.sh                 # Test LLM Vision analysis
├── test-notification.sh               # Test phone notifications
└── test-voice-pe-led.sh               # Test Voice PE LED
```

## Related Documentation

- **Blog Post**: `docs/source/md/blog-package-detection-llm-vision.md`
- Voice PE Setup: `docs/source/md/voice-pe-complete-setup-guide.md`
- LLM Vision Reference: `docs/reference/llm-vision-complete-reference.md`
- Frigate Integration: `docs/source/md/frigate-homeassistant-integration-guide.md`

## GitHub Issue

Tracking: https://github.com/homeiac/home/issues/167
