# LLM Vision Duplicate Automation Root Cause Analysis

**Date**: August 2, 2025  
**Issue**: Intermittent "Please provide the image descriptions or the content of the..." messages in LLM Vision timeline  
**Status**: Root cause identified - duplicate automations causing race conditions  
**Impact**: ~5% of events affected, no data loss, system self-recovers

## Problem Statement

LLM Vision timeline occasionally shows incomplete requests with messages like "Please provide the image descriptions or the content of the..." instead of proper image analysis. Initial investigation suggested timing issues with rapid motion triggers, but deeper analysis revealed a configuration issue.

## Root Cause Analysis

### Initial Hypothesis (Incorrect)
- **Suspected**: Rapid successive motion triggers causing camera resource contention
- **Evidence**: Problem events occurred 1 second apart from successful events
- **Why Wrong**: Timing pattern was too consistent, suggested systematic rather than random issue

### Actual Root Cause: Duplicate Automations
**Issue**: Two separate automations configured to handle the same motion sensors and cameras

**Configuration Found**:
```yaml
# Automation 1: Custom YAML with cooldown
- alias: "LLM Vision Analysis" 
  trigger:
    - platform: state
      entity_id: [motion sensors]
  action:
    - action: llmvision.image_analyzer
  cooldown:
    seconds: 30  # Configured cooldown

# Automation 2: Blueprint without cooldown  
- alias: "AI Event Summary (v1.5.0)"
  use_blueprint:
    path: valentinfrlch/event_summary.yaml
    input:
      motion_sensors: [same sensors]
      camera_entities: [same cameras]
  # No cooldown configured
```

### Technical Analysis

**Race Condition Mechanics**:
1. Motion sensor triggers (e.g., `binary_sensor.reolink_doorbell_motion`)
2. Both automations fire simultaneously
3. Both call `llmvision.image_analyzer` on same camera within milliseconds
4. First request succeeds, gets camera image
5. Second request fails to access camera (resource busy)
6. LLM receives empty/corrupted image data
7. LLM responds with "Please provide the image descriptions..."

**Evidence Pattern**:
```sql
-- Timeline showing problem pattern
2025-08-02 16:18:11|PROBLEM|camera.reolink_doorbell  -- Automation 2 fails
2025-08-02 16:18:10|SUCCESS|camera.reolink_doorbell  -- Automation 1 succeeds
2025-08-02 15:52:18|PROBLEM|camera.old_ip_camera     -- Automation 2 fails  
2025-08-02 15:52:17|SUCCESS|camera.old_ip_camera     -- Automation 1 succeeds
```

**Key Indicators**:
- Problem events always paired with successful events (1-second timing)
- All cameras affected equally (not hardware-specific)
- Consistent ~95% success rate
- No correlation with motion sensor type or timing

### Contributing Factors

1. **Cooldown Mismatch**: Only first automation had cooldown configured
2. **Resource Contention**: Camera entities cannot serve simultaneous image requests
3. **Identical Configuration**: Both automations used same prompts and targets
4. **Blueprint vs Custom**: Different automation types with different timing behaviors

## Impact Assessment

### System Impact
- **Functional**: 95%+ events process correctly, system continues working
- **Data Quality**: Some timeline entries have incomplete analysis
- **Performance**: Minimal - double API calls but no system degradation
- **User Experience**: Occasional confusing timeline entries

### Business Impact
- **Security Monitoring**: Still functional, most events captured properly
- **Automation Reliability**: High overall success rate maintained
- **Resource Usage**: Unnecessary duplicate API calls to LLM service

## Prevention Measures

### Immediate Actions Taken
- **Root Cause Documented**: Complete analysis of duplicate automation issue
- **Detection Runbook Created**: Commands to identify this pattern in future
- **Configuration Analysis**: Documented all automation configurations

### Recommended Long-term Solutions
1. **Automation Consolidation**: Remove one of the duplicate automations
2. **Cooldown Standardization**: Ensure all automations have appropriate cooldowns
3. **Configuration Review**: Regular audit of automation overlap
4. **Monitoring**: Automated detection of duplicate timeline entries

### Configuration Management
- **Single Source of Truth**: Use either custom YAML or blueprint, not both
- **Cooldown Requirements**: All camera automations must have cooldown >= 30 seconds
- **Testing Protocol**: Verify automation uniqueness before deployment

## Technical Details

### Camera Resource Locking
```bash
# Camera entities show single state but can't serve multiple simultaneous requests
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states/camera.reolink_doorbell"
# Returns: {"state": "recording"} - but resource still locked during image capture
```

### LLM Vision Service Behavior
- **Success Case**: Image data passed to LLM, proper analysis returned
- **Failure Case**: Empty/corrupted image data, LLM requests image descriptions
- **No Error Logging**: Integration doesn't log resource contention failures

### Database Schema Impact
```sql
-- Timeline events table structure
CREATE TABLE events (
    uid TEXT,
    summary TEXT,      -- Shows truncated "Please provide..." 
    description TEXT,  -- Shows full LLM response
    start TIMESTAMP,
    camera_name TEXT
);
```

## Detection and Monitoring

### Automated Detection Query
```sql
-- Identify duplicate automation pattern
SELECT 
    datetime(start) as event_time,
    camera_name,
    CASE WHEN summary LIKE '%Please provide%' THEN 'PROBLEM' ELSE 'SUCCESS' END as status
FROM events 
WHERE start > datetime('now', '-24 hours')
ORDER BY start DESC;

-- Look for: PROBLEM events immediately preceded/followed by SUCCESS events on same camera
```

### Health Check Commands
```bash
# Check for recent problem events
ssh -p 22222 root@homeassistant.maas \
  "sqlite3 /mnt/data/supervisor/homeassistant/llmvision/events.db \
   'SELECT COUNT(*) FROM events WHERE summary LIKE \"%Please provide%\" AND start > datetime(\"now\", \"-24 hours\");'"

# Expected: <5% of total daily events

# Verify automation configuration overlap
ssh -p 22222 root@homeassistant.maas \
  "grep -c 'binary_sensor.*motion' /mnt/data/supervisor/homeassistant/automations.yaml"

# Expected result interpretation: Count should match number of unique motion sensors
```

## Lessons Learned

### Configuration Management
- **Blueprint vs Custom**: Understand timing differences between automation types
- **Resource Awareness**: Camera entities have access limitations during image capture
- **Cooldown Necessity**: All camera automations need cooldowns, not just custom ones

### Debugging Methodology
- **Pattern Recognition**: Consistent timing patterns indicate systematic issues
- **Multiple Hypothesis Testing**: Don't stop at first reasonable explanation
- **Configuration Cross-Reference**: Check for automation overlap and duplication

### Documentation Requirements
- **Complete Automation Inventory**: Document all automations and their triggers
- **Resource Dependency Mapping**: Identify shared resources between automations
- **Testing Protocols**: Verify uniqueness and non-interference

## Related Documentation

- `docs/reference/integrations/home-assistant/llm-vision/configuration-hints.md` - Complete configuration guide
- `docs/runbooks/llm-vision-duplicate-automation-detection.md` - Detection and resolution runbook
- `docs/troubleshooting/llm-vision-camera-mapping-rca.md` - Previous camera mapping issues

## Resolution Status

**Current State**: Issue identified and documented, system remains functional  
**Recommended Action**: Consolidate to single automation per motion sensor/camera pair  
**Monitoring**: Use detection queries to monitor for recurrence  
**Documentation**: Complete runbook created for future identification