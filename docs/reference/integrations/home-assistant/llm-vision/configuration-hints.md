# LLM Vision Integration Configuration Guide

**Integration**: Home Assistant LLM Vision  
**Repository**: https://github.com/valentinfrlch/ha-llmvision  
**Last Updated**: August 2, 2025  
**Based on**: Real-world debugging session and configuration fixes

## Three Approaches to Using LLM Vision

LLM Vision can be configured in three different ways, each with specific use cases:

1. **Manual Service Calls** - Direct service calls for testing or simple setups
2. **Custom YAML Automations** - Write your own automation logic  
3. **Blueprint Automations** - Use provided template for complex multi-camera setups

### When to Use Each Approach:
- **Manual Service Calls**: Testing, development, simple one-off analysis
- **Custom YAML Automations**: Single camera or simple motion → camera mapping
- **Blueprint Automations**: Multi-camera setups with automatic camera selection logic

## Approach 1: Manual Service Calls

### Use Case
Perfect for testing, development, or simple analysis where you want direct control over which camera and prompt to use.

### Setup Requirements
1. LLM Vision integration installed and configured with AI provider
2. Camera entities available in Home Assistant
3. No automation configuration needed

### Service Call Examples
```yaml
# Basic image analysis
action: llmvision.image_analyzer
data:
  message: "Who's at the door?"
  image_entity: camera.front_door
  provider: your_provider_id

# Multiple camera analysis
action: llmvision.image_analyzer  
data:
  message: "Describe any activity in these cameras"
  image_entity:
    - camera.front_door
    - camera.driveway
  provider: your_provider_id

# Stream analysis with specific model
action: llmvision.stream_analyzer
data:
  message: "Monitor for package deliveries"
  image_entity: camera.front_porch
  provider: your_provider_id
  model: gemma3:4b
```

### Verification Steps
```bash
# 1. Test service call via Home Assistant API
TOKEN=$(grep HOME_ASSISTANT_TOKEN proxmox/homelab/.env | cut -d'=' -f2)
URL=$(grep HOME_ASSISTANT_URL proxmox/homelab/.env | cut -d'=' -f2)

# 2. Call LLM Vision service directly
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Describe what you see",
    "image_entity": "camera.your_camera",
    "provider": "your_provider_id"
  }' \
  "$URL/api/services/llmvision/image_analyzer?return_response=true"

# Expected: JSON response with analysis results

# 3. Verify camera entity exists
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states/camera.your_camera" | jq '.entity_id'
# Expected: "camera.your_camera"

# 4. Verify provider ID  
curl -H "Authorization: Bearer $TOKEN" "$URL/api/config/integrations" | jq '.[] | select(.domain == "llmvision")'
# Expected: Integration details with provider configuration
```

### Integration GUI Configuration
**Location**: Home Assistant → Settings → Devices & Services → LLM Vision
**Required Settings**:
- AI Provider (Ollama, OpenAI, etc.)  
- API endpoint/credentials
- Default model selection

**Note**: Manual service calls require no automation configuration - just the integration setup.

## Approach 2: Custom YAML Automations

### Use Case
Single camera setups or simple motion → camera mapping where you want to write your own automation logic.

### Configuration Example
```yaml
# Example: Front door motion triggers analysis
- alias: "Front Door LLM Analysis"
  description: "Analyze front door camera when motion detected"
  trigger:
    - platform: state
      entity_id: binary_sensor.front_door_motion
      to: 'on'
  condition:
    - condition: state
      entity_id: camera.front_door
      state: 'recording'  # or 'streaming'
  action:
    - action: llmvision.image_analyzer
      data:
        message: "Describe any people, vehicles, or packages at the front door. If no activity is visible, explain why (lighting, angle, etc.)"
        image_entity: camera.front_door
        provider: "01K1KDVH6Y1GMJ69MJF77WGJEA"  # Your provider ID
        model: "gemma3:4b"
    - action: logbook.log  
      data:
        name: "LLM Vision Analysis"
        message: "Front door motion triggered image analysis"

# Example: Multi-camera with conditional logic
- alias: "Driveway Activity Analysis"  
  trigger:
    - platform: state
      entity_id: binary_sensor.driveway_motion
      to: 'on'
  action:
    - choose:
        - conditions:
            - condition: sun
              after: sunset
          sequence:
            - action: llmvision.image_analyzer
              data:
                message: "Analyze nighttime activity in driveway. Look for vehicles, people, or security concerns."
                image_entity: camera.driveway_ir
        - conditions:
            - condition: sun  
              before: sunset
          sequence:
            - action: llmvision.image_analyzer
              data:
                message: "Analyze daytime driveway activity. Describe vehicles, deliveries, or people."
                image_entity: camera.driveway_color
```

### Verification Steps
```bash
# 1. Validate automation syntax
ssh -p 22222 root@homeassistant.maas "python3 -c 'import yaml; yaml.safe_load(open(\"/mnt/data/supervisor/homeassistant/automations.yaml\"))'"
# Expected: No output (valid YAML)

# 2. Check automation is loaded
TOKEN=$(grep HOME_ASSISTANT_TOKEN proxmox/homelab/.env | cut -d'=' -f2)
URL=$(grep HOME_ASSISTANT_URL proxmox/homelab/.env | cut -d'=' -f2)
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states" | jq '.[] | select(.entity_id == "automation.front_door_llm_analysis")'
# Expected: Automation entity details

# 3. Test motion sensor trigger
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states/binary_sensor.front_door_motion" | jq '{state: .state, last_changed: .last_changed}'
# Expected: Motion sensor state and timing

# 4. Manual automation test
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -d '{"entity_id": "automation.front_door_llm_analysis"}' \
  "$URL/api/services/automation/trigger"

# 5. Check automation execution
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states/automation.front_door_llm_analysis" | jq '.attributes.last_triggered'
# Expected: Recent timestamp
```

### Advantages of Custom YAML
- **Full control** over automation logic
- **Simple to understand** - direct motion sensor → camera mapping
- **Easy to customize** - conditional logic, multiple triggers, etc.
- **No blueprint dependencies** - self-contained automation

### Disadvantages  
- **Manual camera mapping** - you handle all the logic
- **Repetitive configuration** - need separate automation per camera
- **No automatic camera selection** - must specify camera explicitly

## Approach 3: Blueprint Automations (Advanced Multi-Camera)

### Use Case
Complex multi-camera setups where you want automatic camera selection based on which motion sensor triggered.

## Critical Configuration Requirements

### Blueprint Automation Array Alignment (CRITICAL)
**Issue**: Camera mapping fails when motion sensor and camera entity arrays are misaligned
**Location**: `automations.yaml` for any automation using `valentinfrlch/event_summary.yaml` blueprint

```yaml
# ❌ WRONG - Arrays not aligned by index
motion_sensors:
- binary_sensor.reolink_doorbell_motion     # Index 0
- binary_sensor.trendnet_ip_572w_motion     # Index 1
camera_entities:
- camera.trendnet_ip_572w                   # Index 0 (wrong camera for reolink motion!)
- camera.reolink_doorbell                   # Index 1 (wrong camera for trendnet motion!)

# ✅ CORRECT - Arrays aligned by index  
motion_sensors:
- binary_sensor.reolink_doorbell_motion     # Index 0
- binary_sensor.trendnet_ip_572w_motion     # Index 1
camera_entities:
- camera.reolink_doorbell                   # Index 0 (matches reolink motion)
- camera.trendnet_ip_572w                   # Index 1 (matches trendnet motion)
```

**Why**: Blueprint template uses `motion_sensors_list.index(trigger.entity_id)` to find array index, then accesses `camera_entities_list[index]`. Misalignment causes wrong camera selection.

**Validation**: Visual verification required - download actual captured images to confirm correct camera triggered.

### Home Assistant Restart Requirements
**Issue**: Automation reload insufficient for new input field additions
**Specific Case**: Adding `message` field to existing automation inputs

```yaml
# Adding this to existing automation requires HA RESTART, not just reload
automation:
  use_blueprint:
    input:
      # existing fields...
      message: 'Custom LLM prompt...'  # NEW FIELD = RESTART REQUIRED
```

**Commands**:
```bash
# ❌ INSUFFICIENT - Only reloads existing automation structure
curl -X POST "$HA_URL/api/services/automation/reload"

# ✅ REQUIRED - Full restart for new input fields
curl -X POST "$HA_URL/api/services/homeassistant/restart"
```

**Why**: HA needs to reinitialize automation input schemas for new fields.

### LLM Prompt Quality Impact
**Issue**: Default blueprint prompts produce generic unhelpful responses
**Default Prompt**: `"If no movement is detected, respond with: 'No activity observed.'"`
**Problem**: No context about WHY no activity detected

```yaml
# ❌ GENERIC - Unhelpful timeline entries
message: 'Default blueprint prompt...'
# Result: "No activity observed" (100% of entries)

# ✅ DESCRIPTIVE - Useful timeline analysis  
message: 'Analyze the images from this camera and describe any activity detected. Focus on people, vehicles, and movement. If no clear activity is visible, describe why - such as "No activity detected: image too dark/blurry", "No activity detected: camera shows empty hallway", or "No movement visible in outdoor scene". Be specific about what you can see in the image and camera location context.'
# Result: "Person seen at hallway entrance", "No activity: camera shows empty porch"
```

**Impact**: Timeline becomes useful security monitoring tool instead of useless generic log.

## Configuration Validation Methodology

### Visual Image Verification (MANDATORY)
**Why Required**: API responses don't indicate camera mapping correctness
**Process**:
```bash
# 1. Trigger motion sensor or automation
# 2. Download actual captured image
ssh -p 22222 root@homeassistant.maas "cat /mnt/data/supervisor/homeassistant/www/llmvision/LATEST.jpg" > /tmp/verify.jpg
# 3. Visual confirmation: Does image match expected camera location?
# - Indoor hallway = TrendNet camera ✓  
# - Outdoor porch with Reolink watermark = Reolink camera ✓
# - Wrong scene type = Configuration error ❌
```

**Critical**: Don't trust automation execution success - verify actual outputs.

### Motion Sensor Correlation Testing
**Issue**: Manual automation triggers don't test camera mapping logic
**Why**: Blueprint template logic only activates with motion sensor triggers, not manual triggers

```bash
# ❌ DOESN'T TEST CAMERA MAPPING - Bypasses blueprint logic
curl -X POST "$HA_URL/api/services/automation/trigger" -d '{"entity_id": "automation.llm_vision"}'

# ✅ TESTS CAMERA MAPPING - Uses blueprint template logic
# Wait for actual motion sensor trigger or physically trigger motion sensor
# Then verify captured image matches motion sensor type
```

**Validation**: Always test with real motion sensor events, not manual triggers.

### Array Alignment Verification Commands
```bash
# Check automation configuration alignment
ssh -p 22222 root@homeassistant.maas "grep -A 10 -B 2 'motion_sensors:' /mnt/data/supervisor/homeassistant/automations.yaml"
ssh -p 22222 root@homeassistant.maas "grep -A 10 -B 2 'camera_entities:' /mnt/data/supervisor/homeassistant/automations.yaml"

# Verify motion sensor activity correlation  
curl -H "Authorization: Bearer $TOKEN" "$HA_URL/api/states" | \
  jq '.[] | select(.entity_id | contains("motion")) | {entity_id: .entity_id, last_changed: .last_changed}'

# Check corresponding image timestamps
ssh -p 22222 root@homeassistant.maas "ls -lt /mnt/data/supervisor/homeassistant/www/llmvision/*.jpg | head -5"
```

## Common Failure Patterns

### Symptom: Motion Triggers Wrong Camera
**Root Cause**: Array index misalignment in automation configuration
**Detection**: Visual verification shows wrong camera type for motion location  
**Fix**: Reorder camera_entities array to match motion_sensors array indices

### Symptom: Timeline Shows Only "No Activity Observed"
**Root Cause**: Generic LLM prompt design  
**Detection**: Database full of identical generic responses
**Fix**: Update automation message field with descriptive prompt + HA restart

### Symptom: Configuration Changes Not Taking Effect
**Root Cause**: Automation reload insufficient for new input fields
**Detection**: Changes visible in config but behavior unchanged
**Fix**: Full Home Assistant restart required

### Symptom: Manual Tests Pass But Motion Doesn't Work
**Root Cause**: Manual triggers bypass blueprint camera mapping logic
**Detection**: Manual automation triggers work but motion sensor triggers don't
**Fix**: Test with actual motion sensor events, not manual triggers

## Integration-Specific Architecture Notes

### Blueprint Template Dependencies
- Uses Jinja2 template logic for camera selection: `camera_entities_list[motion_sensors_list.index(trigger.entity_id)]`
- Requires exact array index alignment between motion_sensors and camera_entities
- Template logic only executes for motion sensor triggers, not manual automation triggers

### Database Schema
- Timeline events stored in SQLite: `/mnt/data/supervisor/homeassistant/llmvision/events.db`
- Table: `events` with columns: `uid`, `summary`, `start`, `end`, `description`, `key_frame`, `camera_name`
- Generic responses can be bulk deleted: `DELETE FROM events WHERE summary LIKE '%No activity observed%'`

### Image Storage Pattern
- Captured images: `/mnt/data/supervisor/homeassistant/www/llmvision/*.jpg`
- Filename format: `{uuid}-0.jpg` (e.g., `c3f0107c-0.jpg`)
- Images timestamped with capture time for correlation with motion events

## Prevention Checklist

Before deploying LLM Vision automations:
- [ ] Verify motion_sensors and camera_entities arrays are aligned by index
- [ ] Test camera mapping with visual image verification
- [ ] Update default prompts to be descriptive rather than generic
- [ ] Plan for full HA restart after configuration changes
- [ ] Test with actual motion sensor triggers, not manual automation triggers
- [ ] Document expected camera types for each motion sensor location

## Monitoring and Maintenance

### Regular Health Checks
```bash
# Check for excessive generic responses (monthly)
ssh -p 22222 root@homeassistant.maas "sqlite3 /mnt/data/supervisor/homeassistant/llmvision/events.db 'SELECT COUNT(*) FROM events WHERE summary LIKE \"%No activity%\" AND start > datetime(\"now\", \"-30 days\");'"
# Expected: < 10% of total events

# Verify recent motion sensor activity correlation (weekly)  
curl -H "Authorization: Bearer $TOKEN" "$HA_URL/api/states" | \
  jq '.[] | select(.entity_id | contains("motion")) | select(.last_changed > "2025-08-01") | {entity_id: .entity_id, last_changed: .last_changed}'
```

### Configuration Drift Detection
```bash
# Verify automation array alignment hasn't changed
ssh -p 22222 root@homeassistant.maas "grep -A 5 'motion_sensors:' /mnt/data/supervisor/homeassistant/automations.yaml && echo '---' && grep -A 5 'camera_entities:' /mnt/data/supervisor/homeassistant/automations.yaml"
# Manually verify arrays are still aligned by index
```

## Integration Limitations

### Manual Testing Limitations
- Manual automation triggers don't test camera mapping logic
- Blueprint template camera selection only works with motion sensor entity triggers
- Visual verification of captured images is mandatory for validation

### Configuration Change Requirements  
- New automation input fields require full HA restart
- Automation reload insufficient for input schema changes
- Changes to existing input values can use automation reload

### Multi-Camera Complexity
- Each additional camera increases configuration complexity exponentially  
- Array alignment becomes critical with 3+ cameras
- Visual verification required for each camera/motion sensor pair

This integration requires careful configuration management and systematic validation to ensure proper operation in multi-camera environments.