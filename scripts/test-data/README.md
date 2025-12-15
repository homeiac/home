# Test Data and Validation Tools

Tools for testing the Claude Code Ambient AI system.

## Quick Start

```bash
# Validate all schema examples
python validate-schemas.py --validate-all

# Generate synthetic data for a use case
python generate.py --usecase p0_1_ask_claude

# List all available use cases
python generate.py --list

# Publish test data to MQTT broker
python generate.py --usecase p0_1_ask_claude --output mqtt --broker mqtt.homelab
```

## Scripts

### generate.py - Synthetic Data Generator

Generates realistic MQTT message sequences for all use cases.

**Usage:**
```bash
# Output all use cases as JSON
python generate.py --usecase all

# Single use case
python generate.py --usecase p0_1_ask_claude

# Filter by priority
python generate.py --priority P0

# Output as shell commands (mosquitto_pub)
python generate.py --usecase all --output shell

# Publish directly to MQTT
python generate.py --usecase p0_1_ask_claude --output mqtt --broker mqtt.homelab
```

**Available Use Cases:**

| Name | Priority | Description |
|------|----------|-------------|
| `p0_1_ask_claude` | P0 | Voice command → response |
| `p0_2_task_complete` | P0 | Task started → completed |
| `p0_2_task_failed` | P0 | Task started → failed |
| `p1_3_proactive_briefing` | P1 | Presence → briefing |
| `p1_5_glanceable_status` | P1 | Home healthy + work offline |
| `p1_5_puck_interaction` | P1 | Puck refresh interaction |
| `p2_6_unknown_person` | P2 | Unknown face → alert |
| `p3_8_cardputer_text` | P3 | Keyboard → command |
| `failure_malformed_json` | Failure | Broken JSON payload |
| `failure_stale_data` | Failure | 48-hour old message |
| `failure_work_offline` | Failure | Server unavailable |
| `failure_missing_field` | Failure | Missing required field |
| `multi_device_notification` | Integration | Critical alert to all |

### validate-schemas.py - Schema Validator

Validates MQTT messages against JSON schemas.

**Usage:**
```bash
# Validate all examples in schema files
python validate-schemas.py --validate-all

# List available schemas
python validate-schemas.py --list-schemas

# Validate a specific file
python validate-schemas.py --file message.json --schema claude-status

# Validate from stdin
echo '{"server":"home","online":true,"sessions":2,"git_dirty":0,"last_activity":"2025-12-14T10:00:00Z"}' | \
    python validate-schemas.py --schema claude-status

# Live MQTT validation
python validate-schemas.py --broker mqtt.homelab --subscribe "claude/#"
```

## Schemas

Located in `/schemas/`:

| Schema | Topics |
|--------|--------|
| `claude-status` | `claude/{server}/status` |
| `claude-task` | `claude/{server}/task/{id}` |
| `claude-notification` | `claude/{server}/notification` |
| `claude-command` | `claude/command` |
| `presence-detected` | `presence/{device}/detected` |

## Testing Workflow

### 1. Validate Schema Examples
```bash
python validate-schemas.py --validate-all
```

### 2. Generate Test Data
```bash
python generate.py --usecase p0_1_ask_claude
```

### 3. Publish to Test Broker
```bash
# Start local mosquitto (if not running)
docker run -d -p 1883:1883 eclipse-mosquitto:2

# Publish test data
python generate.py --usecase p0_1_ask_claude --output mqtt --broker localhost
```

### 4. Monitor Messages
```bash
# In another terminal
mosquitto_sub -h localhost -t "claude/#" -v
```

### 5. Run Schema Validation
```bash
# Live validation on broker
python validate-schemas.py --broker localhost --subscribe "claude/#" -v
```

## Requirements

```bash
pip install jsonschema paho-mqtt
```

## Integration with CI

```yaml
# .github/workflows/test.yml
- name: Validate schemas
  run: python scripts/test-data/validate-schemas.py --validate-all
```

## Related Files

- `/schemas/` - JSON Schema definitions
- `/features/` - BDD feature files (Gherkin)
- `/docs/architecture/claude-code-ambient-ai-testing.md` - Full testing strategy
