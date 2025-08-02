# Troubleshooting Home Assistant Automation Issues

When Home Assistant automations fail to work correctly, you may encounter:

```text
Timeline card showing "Off" instead of events
Services not found or failing to execute
Template rendering errors with undefined variables
Provider configuration not found errors
'NoneType' object has no attribute errors
```

This runbook provides systematic steps to diagnose and fix Home Assistant automation issues, specifically for complex integrations like LLM Vision.

## Quick Diagnosis Commands

### Check Integration Status
```bash
# Check if integration is loaded and configured
curl -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/config/integrations" | \
  jq '.[] | select(.domain == "integration_name")'

# Check entity states
curl -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/target.entity" | jq '.'
```

### Check Recent Errors
```bash
# SSH to Home Assistant
ssh -p 22222 root@homeassistant.maas

# Check last 30 minutes for errors
docker logs homeassistant --since='30m' 2>&1 | \
  grep -i 'error\|exception' | tail -10

# Integration-specific errors
docker logs homeassistant --since='1h' 2>&1 | \
  grep -i 'integration_name' | grep -i 'error'
```

## Entity Investigation

### Verify Entity Existence
```bash
# Check if entity exists in Home Assistant
curl -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/entity.id"

# List entities by domain
curl -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
  jq '.[] | select(.entity_id | startswith("domain.")) | .entity_id'

# Check entity registry
cat /mnt/data/supervisor/homeassistant/.storage/core.entity_registry | \
  jq '.data.entities[] | select(.entity_id == "target.entity")'
```

### Check Entity Attributes
```bash
# Verify entity has required attributes
curl -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/camera.target" | \
  jq '.attributes | keys[]'

# Check for entity_picture attribute (cameras)
curl -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/camera.target" | \
  jq '.attributes.entity_picture'
```

## Service Testing

### Test Services Manually
```bash
# List available services for domain
curl -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/services" | \
  jq '.[] | select(.domain == "target_domain")'

# Test basic service call
curl -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "test.entity"}' \
  "$HA_URL/api/services/domain/service"

# Test with return_response for debugging
curl -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"param": "value"}' \
  "$HA_URL/api/services/domain/service?return_response=true"
```

### Verify Service Parameters
```bash
# Check service call in logs
docker logs homeassistant --since='1m' 2>&1 | \
  grep -A 5 "Executing service.*domain.*service"

# Look for parameter validation errors
docker logs homeassistant --since='5m' 2>&1 | \
  grep -i 'invalid.*parameter\|missing.*required'
```

## Automation Debugging

### Check Automation Status
```bash
# List automation states
curl -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
  jq '.[] | select(.entity_id | startswith("automation")) | 
     "\(.entity_id) - \(.state) - \(.attributes.last_triggered)"'

# Check specific automation
curl -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/automation.target_automation"
```

### Manual Automation Testing
```bash
# Trigger automation manually
curl -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "automation.target"}' \
  "$HA_URL/api/services/automation/trigger"

# Check automation execution in logs
docker logs homeassistant --since='2m' 2>&1 | \
  grep -E 'automation.*triggered|automation.*executed'
```

### Blueprint Investigation
```bash
# Find blueprint files
find /mnt/data/supervisor/homeassistant/blueprints/ -name "*.yaml" | \
  grep blueprint_name

# Check template variables in blueprint
grep -E '{{.*}}|\{%.*%\}' /path/to/blueprint.yaml

# Validate automation using blueprint
grep -A 20 "use_blueprint:" /mnt/data/supervisor/homeassistant/automations.yaml
```

## Configuration Investigation

### Check Integration Configuration
```bash
# Integration configuration entries
cat /mnt/data/supervisor/homeassistant/.storage/core.config_entries | \
  jq '.data.entries[] | select(.domain == "integration_name")'

# Device registry
cat /mnt/data/supervisor/homeassistant/.storage/core.device_registry | \
  jq '.data.devices[] | select(.manufacturer == "vendor_name")'
```

### Template Validation
```bash
# Check for template errors in logs
docker logs homeassistant --since='10m' 2>&1 | \
  grep -i 'template.*error\|undefined.*rendering'

# Test templates in Developer Tools → Templates
# Or validate YAML syntax:
python -c "import yaml; yaml.safe_load(open('automations.yaml'))"
```

## Custom Component Issues

### Check Component Loading
```bash
# Find custom component files
find /mnt/data/supervisor/homeassistant/custom_components/ \
  -name "*.py" | grep component_name

# Check component setup in logs
docker logs homeassistant --since='startup' 2>&1 | \
  grep -i "setup.*component_name"
```

### Code Analysis
```bash
# Search for error patterns in component code
grep -r "error_message_from_logs" \
  /mnt/data/supervisor/homeassistant/custom_components/component_name/

# Check service registration
grep -A 10 "hass.services.register" \
  custom_components/component_name/__init__.py
```

## Data Flow Debugging

### Input Validation
```bash
# Check what parameters are being passed
docker logs homeassistant --since='1m' 2>&1 | \
  grep -A 5 -B 5 "service.*component.*service_name"

# Verify entity states before service call
curl -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/input.entity" | jq '.state, .attributes'
```

### Output Verification
```bash
# Check created/modified entities after service call
curl -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states" | \
  jq '.[] | select(.last_changed > "recent_timestamp")'

# Check file system outputs (if applicable)
ls -la /mnt/data/supervisor/homeassistant/www/component_name/

# Database outputs (if applicable)
find /mnt/data/supervisor/homeassistant/ -name "*component*db"
sqlite3 component.db '.tables'
```

## Common Error Patterns

### Provider Configuration Not Found
```bash
# Check provider configuration exists
grep -r "provider_id" /mnt/data/supervisor/homeassistant/.storage/

# Verify provider loaded in runtime
docker logs homeassistant --since='restart' 2>&1 | \
  grep -i "provider.*config.*loaded"
```

### NoneType Attribute Errors
```bash
# Find the exact error location
docker logs homeassistant --since='5m' 2>&1 | \
  grep -A 10 "'NoneType' object has no attribute"

# Check null handling in code
grep -A 5 -B 5 "\.get(" custom_components/component/file.py
```

### Template Rendering Errors
```bash
# Check for undefined variables
docker logs homeassistant --since='10m' 2>&1 | \
  grep "undefined.*rendering"

# Validate template syntax in automation
grep -E '{{.*}}|\{%.*%\}' automations.yaml | head -5
```

## Fix Validation

### Test After Changes
```bash
# Reload configuration
curl -X POST -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/services/homeassistant/reload_config_entry" \
  -d '{"entry_id": "config_entry_id"}'

# Check configuration syntax
ssh -p 22222 root@homeassistant.maas "ha core check"

# Restart if needed
ssh -p 22222 root@homeassistant.maas "ha core restart"
```

### End-to-End Testing
```bash
# Trigger original failing scenario
curl -X POST -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/services/automation/trigger" \
  -d '{"entity_id": "automation.test_automation"}'

# Verify expected outputs
sleep 10
curl -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/expected.output_entity"

# Check for new errors
docker logs homeassistant --since='5m' 2>&1 | \
  grep -i 'error\|warning' | wc -l
```

## Environment Variables

Set these for easier debugging:

```bash
export HA_TOKEN="your_token_here"
export HA_URL="http://homeassistant.maas:8123"
```

## Common File Locations

```bash
# Configuration files
/mnt/data/supervisor/homeassistant/automations.yaml
/mnt/data/supervisor/homeassistant/.storage/core.config_entries
/mnt/data/supervisor/homeassistant/.storage/core.entity_registry

# Custom components
/mnt/data/supervisor/homeassistant/custom_components/

# Blueprints
/mnt/data/supervisor/homeassistant/blueprints/automation/

# Generated content (if applicable)
/mnt/data/supervisor/homeassistant/www/component_name/
```

This runbook covers the most common Home Assistant automation debugging scenarios. Use these commands systematically to isolate and fix integration issues.