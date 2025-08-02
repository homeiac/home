# Home Assistant Integration Validation Protocols

**Purpose**: Systematic validation methodology for Home Assistant integration changes  
**Based on**: Real-world debugging of LLM Vision camera mapping issues  
**Last Updated**: August 2, 2025

## Critical Validation Requirements

### 1. Configuration Change Types and Restart Requirements

| Change Type | Validation Method | Restart Required |
|-------------|------------------|------------------|
| Existing automation input values | `automation/reload` + functional test | No |
| New automation input fields | `homeassistant/restart` + full test | **Yes** |
| Blueprint template modifications | `homeassistant/restart` + validation | **Yes** |
| Integration configuration | `homeassistant/restart` + integration test | **Yes** |
| Entity modifications | `automation/reload` + entity verification | No |

### 2. Mandatory Backup Protocol
```bash
# ALWAYS backup before ANY Home Assistant configuration change
ssh -p 22222 root@homeassistant.maas "cp /mnt/data/supervisor/homeassistant/automations.yaml /mnt/data/supervisor/homeassistant/automations.yaml.backup-$(date +%s)"

# For blueprint changes
ssh -p 22222 root@homeassistant.maas "cp /mnt/data/supervisor/homeassistant/blueprints/automation/*/template.yaml /path/to/template.yaml.backup-$(date +%s)"
```

### 3. Configuration Syntax Validation (MANDATORY)
```bash
# MUST run after EVERY configuration change
TOKEN=$(grep HOME_ASSISTANT_TOKEN proxmox/homelab/.env | cut -d'=' -f2)
URL=$(grep HOME_ASSISTANT_URL proxmox/homelab/.env | cut -d'=' -f2)

# Check configuration syntax
ssh -p 22222 root@homeassistant.maas "cd /mnt/data/supervisor/homeassistant && python3 -c 'import yaml; yaml.safe_load(open(\"automations.yaml\"))'" 2>&1
# Expected: No output = valid YAML

# Alternative: HA core check (if available)
curl -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/services/homeassistant/check_config"
# Expected: {"result": "valid"}
```

## Integration-Specific Validation Patterns

### Blueprint-Based Automations
**Critical**: Array alignment validation for multi-entity configurations

```bash
# Validate array alignment (example: motion sensors + cameras)
ssh -p 22222 root@homeassistant.maas "python3 -c '
import yaml
with open(\"/mnt/data/supervisor/homeassistant/automations.yaml\") as f:
    config = yaml.safe_load(f)
for auto in config:
    if \"use_blueprint\" in auto:
        inputs = auto[\"use_blueprint\"][\"input\"]
        if \"motion_sensors\" in inputs and \"camera_entities\" in inputs:
            motion_count = len(inputs[\"motion_sensors\"])
            camera_count = len(inputs[\"camera_entities\"])
            print(f\"Automation {auto[\"alias\"]}: Motion={motion_count}, Cameras={camera_count}\")
            if motion_count != camera_count:
                print(f\"  WARNING: Array length mismatch!\")
            for i in range(min(motion_count, camera_count)):
                motion = inputs[\"motion_sensors\"][i].replace(\"binary_sensor.\", \"\").replace(\"_motion\", \"\")
                camera = inputs[\"camera_entities\"][i].replace(\"camera.\", \"\")
                if motion not in camera:
                    print(f\"  WARNING: Index {i} misalignment: {motion} -> {camera}\")
'"
```

### Visual Output Verification Protocol
**Requirement**: Don't trust API success responses - verify actual system outputs

```bash
# For integrations with file/image outputs
# 1. Record system state before change
ls -la /output/directory/ > /tmp/before_state.txt

# 2. Apply configuration change
# 3. Trigger integration functionality  
# 4. Verify actual outputs created/modified
ls -la /output/directory/ > /tmp/after_state.txt
diff /tmp/before_state.txt /tmp/after_state.txt

# 5. Download and inspect actual outputs (critical step)
# Example: Images, logs, database entries, generated files
```

### Entity State Correlation Validation
**Purpose**: Verify configuration changes affect intended entities

```bash
# Check entity states before change
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states" | \
  jq '.[] | select(.entity_id | contains("target_entity")) | {entity_id: .entity_id, state: .state, last_changed: .last_changed}' > /tmp/entities_before.json

# Apply configuration change and restart if required
# Trigger functionality 
# Check entity states after change
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states" | \
  jq '.[] | select(.entity_id | contains("target_entity")) | {entity_id: .entity_id, state: .state, last_changed: .last_changed}' > /tmp/entities_after.json

# Verify expected entity state changes
diff /tmp/entities_before.json /tmp/entities_after.json
```

## Systematic Testing Methodology

### Phase 1: Pre-Change Validation
1. **Document Current State**: Record working behavior and expected changes
2. **Create Backups**: All configuration files that will be modified
3. **Test Current Functionality**: Establish baseline behavior
4. **Plan Validation Steps**: Define success criteria and verification methods

### Phase 2: Configuration Change Application
1. **Single Change at a Time**: Never modify multiple components simultaneously
2. **Syntax Validation**: Check YAML/configuration syntax after each change
3. **Incremental Application**: Apply, validate, then proceed to next change
4. **Document Each Step**: Record exact changes made and timestamps

### Phase 3: Post-Change Validation  
1. **Restart Requirements**: Apply appropriate restart type based on change
2. **Functional Testing**: Verify intended behavior works as expected
3. **Visual Output Verification**: Check actual system outputs, not just API responses
4. **End-to-End Testing**: Test complete workflow from trigger to final output
5. **Regression Testing**: Verify existing functionality still works

### Phase 4: Documentation and Monitoring
1. **Update Configuration Hints**: Document any integration-specific requirements discovered
2. **Create Monitoring**: Set up detection for configuration drift or integration failures
3. **Rollback Plan**: Document exact steps to restore previous working state

## Common Home Assistant Gotchas

### Restart Type Requirements
```bash
# Quick reload (existing values only)
curl -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/services/automation/reload"

# Full restart (new fields, schema changes, integration changes)  
curl -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/services/homeassistant/restart"
# Wait for restart: sleep 30 && curl -H "Authorization: Bearer $TOKEN" "$URL/api/" | jq '.message'
```

### Entity ID Case Sensitivity and Format Validation
```bash
# Verify entity IDs exist and are formatted correctly
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states" | \
  jq '.[] | select(.entity_id == "exact_entity_id") | .entity_id'
# Expected: Return the entity_id if found, null if not found

# Check for similar entity IDs (case/format variations)
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states" | \
  jq '.[] | select(.entity_id | contains("partial_match")) | .entity_id'
```

### Blueprint Template Logic Dependencies
- Templates with array operations require exact configuration alignment
- Manual automation triggers may bypass template logic (test with real triggers)
- Template errors often manifest as silent failures, not obvious errors

### Integration Storage Patterns
- Custom integrations may store data in `/mnt/data/supervisor/homeassistant/custom_components/`
- Integration databases often in `/mnt/data/supervisor/homeassistant/` with integration name
- Configuration stored in `.storage/` files (JSON format, requires restart for changes)

## Validation Command Templates

### Automation Testing
```bash
# Manual automation trigger (test automation logic)
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_id": "automation.target_automation"}' \
  "$URL/api/services/automation/trigger"

# Check automation execution
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states/automation.target_automation" | \
  jq '.attributes.last_triggered'
# Expected: Recent timestamp if executed
```

### Integration Health Check
```bash
# Check integration status
curl -H "Authorization: Bearer $TOKEN" "$URL/api/config/integrations" | \
  jq '.[] | select(.domain == "target_integration")'

# Verify integration entities are available  
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states" | \
  jq '.[] | select(.entity_id | startswith("target_integration")) | .entity_id'
```

### Service Availability Testing
```bash
# Check available services for integration
curl -H "Authorization: Bearer $TOKEN" "$URL/api/services" | \
  jq '.target_integration // empty'

# Test service call with return response
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"test": "parameters"}' \
  "$URL/api/services/target_integration/test_service?return_response=true"
```

## Emergency Rollback Procedures

### Automation Configuration Rollback
```bash
# List available backups
ssh -p 22222 root@homeassistant.maas "ls -la /mnt/data/supervisor/homeassistant/automations.yaml.backup*"

# Restore most recent backup
ssh -p 22222 root@homeassistant.maas "cp /mnt/data/supervisor/homeassistant/automations.yaml.backup-TIMESTAMP /mnt/data/supervisor/homeassistant/automations.yaml"

# Validate and reload
ssh -p 22222 root@homeassistant.maas "python3 -c 'import yaml; yaml.safe_load(open(\"/mnt/data/supervisor/homeassistant/automations.yaml\"))'"
curl -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/services/automation/reload"
```

### Integration Rollback
```bash
# Stop Home Assistant
curl -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/services/homeassistant/stop"

# Restore integration files (if custom integration)
ssh -p 22222 root@homeassistant.maas "cp -r /backup/custom_components/integration_name/ /mnt/data/supervisor/homeassistant/custom_components/"

# Restart Home Assistant
ssh -p 22222 root@homeassistant.maas "docker restart homeassistant"
```

## Success Metrics and Monitoring

### Configuration Health Indicators
- Configuration syntax validation passes
- All expected entities are available and responding
- Automation last_triggered times update appropriately
- Integration status shows as "loaded" and operational

### Functional Health Indicators  
- End-to-end workflows complete successfully
- Actual system outputs match expected results (files, database entries, etc.)
- No increase in error logs related to the integration
- Integration-specific success metrics (e.g., timeline entries, image captures)

### Continuous Monitoring Setup
```bash
# Daily configuration syntax check
0 6 * * * ssh -p 22222 root@homeassistant.maas "python3 -c 'import yaml; yaml.safe_load(open(\"/mnt/data/supervisor/homeassistant/automations.yaml\"))'" || echo "ALERT: HA configuration syntax error"

# Weekly integration health check
0 8 * * 1 curl -H "Authorization: Bearer $TOKEN" "$URL/api/config/integrations" | jq '.[] | select(.domain == "critical_integration") | .state' | grep -q "loaded" || echo "ALERT: Integration not loaded"
```

This validation protocol ensures systematic verification of Home Assistant integration changes with proper restart requirements, backup procedures, and end-to-end testing methodology.