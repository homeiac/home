# LLM Vision Camera Mapping Troubleshooting Runbook

**Purpose**: Systematic troubleshooting guide for LLM Vision camera mapping issues  
**Last Updated**: August 2, 2025  
**Incident Reference**: Camera mapping misalignment causing wrong camera triggers

## Quick Diagnosis Checklist

### Symptoms that Indicate Camera Mapping Issues
- [ ] Motion sensor triggers but timeline shows irrelevant analysis
- [ ] User stood in front of Camera A but timeline shows Camera B content  
- [ ] Timeline entries all say "No activity observed" despite visible motion
- [ ] Outdoor motion triggers indoor camera images (or vice versa)

### Prerequisites
- [ ] Home Assistant API token available in `proxmox/homelab/.env`
- [ ] SSH access to Home Assistant container (`ssh -p 22222 root@homeassistant.maas`)
- [ ] Understanding of your camera locations (indoor vs outdoor, camera brands)

## Step 1: Verify Current Camera Mapping Configuration

### Check automation configuration
```bash
# View automation camera mapping
ssh -p 22222 root@homeassistant.maas "grep -A 15 -B 5 'camera_entities:' /mnt/data/supervisor/homeassistant/automations.yaml"

# Look for both automations and check array alignment
# Expected format:
# motion_sensors:
# - binary_sensor.reolink_doorbell_motion    # Index 0
# - binary_sensor.trendnet_ip_572w_motion    # Index 1
# camera_entities:  
# - camera.reolink_doorbell                  # Index 0 (must match motion_sensors[0])
# - camera.trendnet_ip_572w                  # Index 1 (must match motion_sensors[1])
```

**✅ Success Criteria**: 
- `motion_sensors[0]` corresponds to `camera_entities[0]`
- `motion_sensors[1]` corresponds to `camera_entities[1]`
- Array indices are aligned logically (reolink motion → reolink camera)

**❌ Failure Indicators**:
- Arrays have different order 
- Camera brands don't match motion sensor brands
- Arrays have different lengths

## Step 2: Test Motion Sensor Correlation

### Check recent motion sensor activity
```bash
TOKEN=$(grep HOME_ASSISTANT_TOKEN proxmox/homelab/.env | cut -d'=' -f2)
URL=$(grep HOME_ASSISTANT_URL proxmox/homelab/.env | cut -d'=' -f2)

# Check all motion sensor states and timing
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states" | \
  jq '.[] | select(.entity_id | contains("binary_sensor") and contains("motion")) | {entity_id: .entity_id, state: .state, last_changed: .last_changed}'
```

**✅ Success Criteria**: 
- Recent motion sensor trigger timestamps available
- Can identify which specific motion sensor triggered

### Find corresponding captured images
```bash
# List recent LLM Vision images with timestamps
ssh -p 22222 root@homeassistant.maas "ls -lt /mnt/data/supervisor/homeassistant/www/llmvision/*.jpg | head -10"

# Look for images that match motion sensor timing (within 1-2 minutes)
```

**✅ Success Criteria**: 
- Image timestamps correlate with motion sensor timing
- Can identify specific images to verify

## Step 3: Visual Image Verification (Critical Step)

### Download and analyze motion-triggered images
```bash
# Download recent motion-triggered image for analysis
ssh -p 22222 root@homeassistant.maas "cat /mnt/data/supervisor/homeassistant/www/llmvision/RECENT_IMAGE.jpg" > /tmp/motion_verify.jpg

# Open image to visually confirm camera type
# - Indoor hallway = TrendNet camera
# - Outdoor porch with "Reolink" watermark = Reolink doorbell
# - Image quality and scene type should match expected camera
```

**✅ Success Criteria**: 
- Motion sensor type matches camera scene type
- TrendNet motion → Indoor hallway image
- Reolink motion → Outdoor porch image with Reolink watermark

**❌ Failure Indicators**:
- Wrong camera triggered (mismatched scene type)
- Outdoor motion triggering indoor images
- Brand watermark doesn't match motion sensor brand

## Step 4: Fix Camera Mapping Configuration

### Backup and fix automation configuration
```bash
# Backup current configuration
ssh -p 22222 root@homeassistant.maas "cp /mnt/data/supervisor/homeassistant/automations.yaml /mnt/data/supervisor/homeassistant/automations.yaml.backup-$(date +%s)"

# Copy config locally for safe editing
ssh -p 22222 root@homeassistant.maas "cat /mnt/data/supervisor/homeassistant/automations.yaml" > /tmp/automations.yaml
```

### Edit camera entity order to match motion sensors
```bash
# Edit /tmp/automations.yaml to align camera_entities with motion_sensors by index
# 
# CORRECT ALIGNMENT EXAMPLE:
# motion_sensors:
# - binary_sensor.reolink_doorbell_motion     # Index 0  
# - binary_sensor.trendnet_ip_572w_motion     # Index 1
# camera_entities:
# - camera.reolink_doorbell                   # Index 0 (matches reolink motion)
# - camera.trendnet_ip_572w                   # Index 1 (matches trendnet motion)
```

### Apply fixed configuration
```bash
# Copy fixed config back
ssh -p 22222 root@homeassistant.maas "cat > /mnt/data/supervisor/homeassistant/automations.yaml" < /tmp/automations.yaml

# Reload automation configuration
TOKEN=$(grep HOME_ASSISTANT_TOKEN proxmox/homelab/.env | cut -d'=' -f2)
URL=$(grep HOME_ASSISTANT_URL proxmox/homelab/.env | cut -d'=' -f2)
curl -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/services/automation/reload"
```

**✅ Success Criteria**: 
- Automation reload returns `[]` (success)
- No YAML syntax errors

## Step 5: Improve LLM Analysis Prompts

### Update automation prompts for descriptive analysis
```bash
# Edit /tmp/automations.yaml to add better message prompts
# 
# Add to both automation inputs:
# message: 'Analyze the images from this camera and describe any activity detected. Focus on people, vehicles, and movement. If no clear activity is visible, describe why - such as "No activity detected: image too dark/blurry", "No activity detected: camera shows empty hallway", or "No movement visible in outdoor scene". Be specific about what you can see in the image and camera location context.'
```

### Apply prompt improvements and restart
```bash
# Copy improved config back
ssh -p 22222 root@homeassistant.maas "cat > /mnt/data/supervisor/homeassistant/automations.yaml" < /tmp/automations.yaml

# CRITICAL: Full HA restart required for new automation input fields
curl -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/services/homeassistant/restart"

# Wait for restart to complete
sleep 30
curl -H "Authorization: Bearer $TOKEN" "$URL/api/" | jq '.message'
# Expected: "API running."
```

**✅ Success Criteria**: 
- HA restart completes successfully
- API comes back online

## Step 6: End-to-End Verification

### Test with actual motion trigger
```bash
# Wait for natural motion or trigger motion sensor
# Check motion sensor state
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states/binary_sensor.trendnet_ip_572w_motion" | jq '{state: .state, last_changed: .last_changed}'
```

### Verify correct camera triggered
```bash
# Check for new images matching motion timing
ssh -p 22222 root@homeassistant.maas "ls -lt /mnt/data/supervisor/homeassistant/www/llmvision/*.jpg | head -3"

# Download most recent image for verification
ssh -p 22222 root@homeassistant.maas "cat /mnt/data/supervisor/homeassistant/www/llmvision/LATEST_IMAGE.jpg" > /tmp/final_verify.jpg

# Visual confirmation: Image should match motion sensor type
```

### Check timeline analysis quality
```bash
# Check recent timeline entries for improved analysis
ssh -p 22222 root@homeassistant.maas "sqlite3 /mnt/data/supervisor/homeassistant/llmvision/events.db 'SELECT start, summary FROM events ORDER BY start DESC LIMIT 3;'"

# Expected: Descriptive analysis like "Person seen at hallway entrance" instead of "No activity observed"
```

**✅ Success Criteria**: 
- Motion sensor type matches captured image camera type
- Timeline shows descriptive analysis with context
- No more generic "No activity observed" responses

## Common Issues and Solutions

### Issue: Arrays Still Misaligned After Fix
**Symptoms**: Motion sensors still triggering wrong cameras
**Solution**: 
1. Double-check array indices manually
2. Ensure exact entity_id names match between motion_sensors and camera_entities
3. Verify no extra spaces or characters in YAML

### Issue: Automation Reload Not Picking Up Prompt Changes  
**Symptoms**: Still getting "No activity observed" after prompt update
**Solution**: 
1. **Full HA restart required** for new automation input fields
2. Automation reload insufficient for adding `message` field
3. Wait 30+ seconds after restart before testing

### Issue: Manual Triggers Don't Test Camera Mapping
**Symptoms**: Manual automation triggers work but motion sensors don't
**Solution**:
1. Use actual motion sensor triggers for testing
2. Manual triggers bypass blueprint template logic
3. Blueprint camera selection only works with motion sensor triggers

### Issue: Images Downloaded but Wrong Camera Type
**Symptoms**: TrendNet motion triggering Reolink images  
**Solution**:
1. Re-verify automation configuration array alignment
2. Check for multiple automations with conflicting configurations
3. Ensure automation reload was successful

## Prevention and Monitoring

### Validation Checklist for Future Changes
- [ ] Camera and motion sensor arrays aligned by index
- [ ] Array alignment matches physical camera locations
- [ ] Visual verification with downloaded images after changes  
- [ ] Full HA restart after automation input field changes
- [ ] End-to-end testing with actual motion sensor triggers

### Monitoring Commands for Regular Health Checks
```bash
# Weekly verification: Check recent motion sensor activity
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states" | \
  jq '.[] | select(.entity_id | contains("motion")) | {entity_id: .entity_id, last_changed: .last_changed}' | \
  head -5

# Monthly verification: Verify timeline analysis quality  
ssh -p 22222 root@homeassistant.maas "sqlite3 /mnt/data/supervisor/homeassistant/llmvision/events.db 'SELECT COUNT(*) FROM events WHERE summary LIKE \"%No activity observed%\" AND start > datetime(\"now\", \"-7 days\");'"
# Expected: Low count (< 10% of total events)
```

## Reference Documentation

- **RCA Document**: `docs/troubleshooting/llm-vision-camera-mapping-rca.md`
- **Action Log**: `docs/troubleshooting/action-log-llm-vision-empty-entity.md`  
- **Image Verification Guide**: `docs/reference/llm-vision-image-verification.md`

## Emergency Rollback

### Quick Restore from Backup
```bash
# List available backups
ssh -p 22222 root@homeassistant.maas "ls -la /mnt/data/supervisor/homeassistant/automations.yaml.backup*"

# Restore most recent backup
ssh -p 22222 root@homeassistant.maas "cp /mnt/data/supervisor/homeassistant/automations.yaml.backup-TIMESTAMP /mnt/data/supervisor/homeassistant/automations.yaml"

# Reload and restart
curl -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/services/automation/reload"
curl -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/services/homeassistant/restart"
```

## Success Metrics

**Before Fix**:
- 100% wrong camera selection for motion events
- Timeline filled with "No activity observed" entries
- No correlation between motion location and captured images

**After Fix**:
- 100% correct camera mapping verified with images
- Descriptive timeline analysis with location context
- Clear correlation between motion sensor type and camera feed

This runbook provides a systematic approach to diagnosing and fixing LLM Vision camera mapping issues with visual verification at each step.