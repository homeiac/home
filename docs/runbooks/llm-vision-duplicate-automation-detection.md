# LLM Vision Duplicate Automation Detection Runbook

**Purpose**: Identify and resolve duplicate LLM Vision automations causing "Please provide image descriptions" timeline entries  
**Frequency**: Run when experiencing timeline quality issues  
**Prerequisites**: SSH access to Home Assistant and database query capabilities

## Problem Identification

### Symptoms
- Timeline entries showing "Please provide the image descriptions or the content of the..."
- Problem events appear in pairs with successful events (1-2 seconds apart)
- All cameras affected equally (not hardware-specific)
- Overall system remains functional with ~95% success rate

### Quick Detection Command
```bash
# Check for recent problem events
ssh -p 22222 root@homeassistant.maas \
  "sqlite3 /mnt/data/supervisor/homeassistant/llmvision/events.db \
   'SELECT datetime(start) as time, 
           CASE WHEN summary LIKE \"%Please provide%\" THEN \"PROBLEM\" ELSE \"SUCCESS\" END as status,
           camera_name 
    FROM events 
    WHERE start > datetime(\"now\", \"-24 hours\") 
    ORDER BY start DESC 
    LIMIT 20;'"
```

**Expected Output if Problem Exists**:
```
2025-08-02 16:18:11|PROBLEM|camera.reolink_doorbell
2025-08-02 16:18:10|SUCCESS|camera.reolink_doorbell  
2025-08-02 15:52:18|PROBLEM|camera.old_ip_camera
2025-08-02 15:52:17|SUCCESS|camera.old_ip_camera
```

**Pattern**: PROBLEM events immediately adjacent to SUCCESS events on same camera

## Root Cause Verification

### Step 1: Check for Duplicate Automations
```bash
# List all automations targeting motion sensors
ssh -p 22222 root@homeassistant.maas \
  "grep -B 2 -A 5 'binary_sensor.*motion' /mnt/data/supervisor/homeassistant/automations.yaml"
```

**Expected Output**:
```yaml
# First automation
- alias: "LLM Vision Analysis"
  trigger:
    - platform: state
      entity_id: binary_sensor.reolink_doorbell_motion

# Second automation (DUPLICATE)  
- alias: "AI Event Summary (v1.5.0)"
  use_blueprint:
    input:
      motion_sensors:
      - binary_sensor.reolink_doorbell_motion  # Same sensor!
```

### Step 2: Verify Automation Count vs Motion Sensor Count
```bash
# Count motion sensor references in automations
MOTION_REFS=$(ssh -p 22222 root@homeassistant.maas \
  "grep -c 'binary_sensor.*motion' /mnt/data/supervisor/homeassistant/automations.yaml")

# Count unique motion sensors  
UNIQUE_SENSORS=$(ssh -p 22222 root@homeassistant.maas \
  "grep 'binary_sensor.*motion' /mnt/data/supervisor/homeassistant/automations.yaml | sort -u | wc -l")

echo "Motion sensor references: $MOTION_REFS"
echo "Unique motion sensors: $UNIQUE_SENSORS"
```

**Problem Indicator**: References > Unique sensors (e.g., 6 references but 3 unique sensors = duplicates)

### Step 3: Check Cooldown Configuration
```bash
# Check which automations have cooldowns configured
ssh -p 22222 root@homeassistant.maas \
  "grep -B 10 -A 5 'cooldown:' /mnt/data/supervisor/homeassistant/automations.yaml"
```

**Expected Finding**: Only some automations have cooldowns, others don't

## Timeline Analysis Commands

### Problem Event Statistics
```bash
# Get problem event percentage for last 24 hours
ssh -p 22222 root@homeassistant.maas \
  "sqlite3 /mnt/data/supervisor/homeassistant/llmvision/events.db \
   'SELECT 
      COUNT(CASE WHEN summary LIKE \"%Please provide%\" THEN 1 END) as problem_events,
      COUNT(*) as total_events,
      ROUND(100.0 * COUNT(CASE WHEN summary LIKE \"%Please provide%\" THEN 1 END) / COUNT(*), 2) as problem_percentage
    FROM events 
    WHERE start > datetime(\"now\", \"-24 hours\");'"
```

**Healthy System**: Problem percentage < 5%  
**Duplicate Automation Issue**: Problem percentage 5-15%

### Timing Pattern Analysis
```bash
# Look for rapid successive events (< 5 seconds apart)
ssh -p 22222 root@homeassistant.maas \
  "sqlite3 /mnt/data/supervisor/homeassistant/llmvision/events.db \
   'SELECT 
      datetime(e1.start) as event1_time,
      datetime(e2.start) as event2_time,
      e1.camera_name,
      CASE WHEN e1.summary LIKE \"%Please provide%\" THEN \"PROBLEM\" ELSE \"SUCCESS\" END as e1_status,
      CASE WHEN e2.summary LIKE \"%Please provide%\" THEN \"PROBLEM\" ELSE \"SUCCESS\" END as e2_status,
      ROUND((julianday(e2.start) - julianday(e1.start)) * 86400, 1) as seconds_apart
    FROM events e1, events e2 
    WHERE e1.camera_name = e2.camera_name 
      AND e1.start > datetime(\"now\", \"-24 hours\")
      AND e2.start > e1.start 
      AND (julianday(e2.start) - julianday(e1.start)) * 86400 < 5
    ORDER BY e1.start DESC 
    LIMIT 10;'"
```

**Problem Pattern**: Events 1-2 seconds apart with SUCCESS/PROBLEM pairs

## Resolution Options

### Option 1: Identify Conflicting Automations (Recommended)
```bash
# List all automation aliases and their triggers
ssh -p 22222 root@homeassistant.maas \
  "awk '/^- alias:/ {alias=$0} /binary_sensor.*motion/ {print alias, $0}' /mnt/data/supervisor/homeassistant/automations.yaml"
```

**Action**: Document which automations use the same motion sensors, plan consolidation

### Option 2: Add Cooldowns to All Automations
```bash
# Check which automations lack cooldowns
ssh -p 22222 root@homeassistant.maas \
  "awk '/^- alias:/ {alias=$0; has_cooldown=0} /cooldown:/ {has_cooldown=1} /^- alias:|^$/ {if (alias && !has_cooldown) print alias; alias=\"\"; has_cooldown=0}' /mnt/data/supervisor/homeassistant/automations.yaml"
```

**Action**: Add cooldown configuration to automations without them

### Option 3: Disable Redundant Automations (Temporary)
```bash
# List automation entity IDs for disabling
TOKEN=$(grep HOME_ASSISTANT_TOKEN proxmox/homelab/.env | cut -d'=' -f2)
URL=$(grep HOME_ASSISTANT_URL proxmox/homelab/.env | cut -d'=' -f2)

curl -H "Authorization: Bearer $TOKEN" "$URL/api/states" | \
  jq -r '.[] | select(.entity_id | startswith("automation.")) | select(.attributes.friendly_name | contains("LLM") or contains("AI Event")) | .entity_id'
```

**Warning**: Verify camera mapping before disabling to avoid breaking functionality

## Monitoring and Prevention

### Daily Health Check
```bash
#!/bin/bash
# Daily LLM Vision health check script

# Check problem event rate
PROBLEM_RATE=$(ssh -p 22222 root@homeassistant.maas \
  "sqlite3 /mnt/data/supervisor/homeassistant/llmvision/events.db \
   'SELECT ROUND(100.0 * COUNT(CASE WHEN summary LIKE \"%Please provide%\" THEN 1 END) / COUNT(*), 2) 
    FROM events WHERE start > datetime(\"now\", \"-24 hours\");'")

echo "Problem event rate: ${PROBLEM_RATE}%"

if (( $(echo "$PROBLEM_RATE > 5" | bc -l) )); then
    echo "WARNING: High problem event rate detected - check for duplicate automations"
else
    echo "System healthy"
fi
```

### Automation Configuration Monitoring
```bash
# Weekly automation overlap check
ssh -p 22222 root@homeassistant.maas \
  "grep 'binary_sensor.*motion' /mnt/data/supervisor/homeassistant/automations.yaml | sort | uniq -c | awk '$1 > 1 {print \"DUPLICATE:\", $2}'"
```

**Alert Condition**: Any motion sensor referenced more than once

## Sample Outputs

### Healthy System Example
```bash
$ # Problem event check
2025-08-02 16:38:10|SUCCESS|camera.trendnet_ip_572w
2025-08-02 16:34:48|SUCCESS|camera.old_ip_camera  
2025-08-02 16:33:05|SUCCESS|camera.reolink_doorbell

$ # Statistics
problem_events: 2
total_events: 150  
problem_percentage: 1.33%  # <5% = healthy
```

### Problem System Example  
```bash
$ # Problem event check
2025-08-02 16:18:11|PROBLEM|camera.reolink_doorbell
2025-08-02 16:18:10|SUCCESS|camera.reolink_doorbell
2025-08-02 15:52:18|PROBLEM|camera.old_ip_camera
2025-08-02 15:52:17|SUCCESS|camera.old_ip_camera

$ # Statistics  
problem_events: 15
total_events: 120
problem_percentage: 12.5%  # >5% = problem

$ # Automation count check
Motion sensor references: 6
Unique motion sensors: 3  # 6/3 = 2x duplication
```

## Escalation

### When to Escalate
- Problem event rate >15% consistently
- System stops generating events entirely  
- Automation changes don't resolve duplication

### Information to Gather
1. Complete automation configuration export
2. 48-hour timeline event export
3. Home Assistant integration status
4. LLM Vision service logs

### Documentation References
- **Root Cause Analysis**: `docs/troubleshooting/llm-vision-duplicate-automation-rca.md`
- **Configuration Guide**: `docs/reference/integrations/home-assistant/llm-vision/configuration-hints.md`
- **Integration Setup**: `docs/reference/integrations/home-assistant/llm-vision/official-documentation.md`

## Success Criteria

**Issue Resolved When**:
- Problem event rate consistently <5%
- No rapid successive events (1-2 seconds apart) on same camera
- Motion sensor references = unique sensor count
- All automations have appropriate cooldowns

**Post-Resolution Monitoring**:
- Daily health checks for 1 week
- Weekly automation configuration audits
- Monthly timeline quality review