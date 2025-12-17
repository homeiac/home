# Voice PE Pulsing Effects & Dial/Button Integration Plan

## Goal
Upgrade Claude Code LED feedback from static RGB colors to native pulsing effects, and enable physical approval via dial rotation and button press.

## Current State
- P0 automation works using RGB colors only (no animation)
- Dial/button events not exposed to HA (internal to ESPHome firmware)
- No approval state tracking

## Implementation Phases

### Phase 1: ESPHome Firmware Modification (Manual via ESPHome Dashboard)

Create reference file with ESPHome YAML additions:
**File**: `scripts/claudecodeui/voice-pe/esphome-voice-pe-claude-additions.yaml`

**Additions:**
1. **API Services** - Expose LED effects:
   - `set_led_effect(effect_name)` - thinking/listening/waiting/idle
   - `trigger_thinking_effect` - Direct native pulse
   - `stop_effects` - Return to idle

2. **Dial Events** - Fire on rotation:
   - Event: `esphome.voice_pe_dial`
   - Data: `{direction: clockwise|anticlockwise}`

3. **Button Events** - Fire on press:
   - Event: `esphome.voice_pe_button`
   - Data: `{action: press|long_press}`

### Phase 2: Home Assistant Helper

Create approval state tracker:
**File**: `scripts/claudecodeui/voice-pe/07-create-approval-helper.sh`

Creates `input_boolean.claude_awaiting_approval` via HA API.

### Phase 3: Updated Automation

Upgrade automation with native effects + physical input:
**File**: `scripts/claudecodeui/voice-pe/automation-claude-led-v2.yaml`

**Changes:**
| Trigger | Old Behavior | New Behavior |
|---------|--------------|--------------|
| `claude/command` | Static cyan RGB | Native thinking pulse effect |
| `claude/approval-request` | Static amber RGB | Amber + set `input_boolean.claude_awaiting_approval` ON |
| `esphome.voice_pe_dial` clockwise | N/A | Publish `{approved: true}`, helper OFF |
| `esphome.voice_pe_dial` anticlockwise | N/A | Publish `{approved: false}`, helper OFF |
| `esphome.voice_pe_button` press | N/A | Publish `{approved: true}` (quick confirm) |

### Phase 4: Test Scripts

| Script | Purpose |
|--------|---------|
| `08-test-esphome-services.sh` | Test ESPHome services after firmware update |
| `09-test-dial-button-events.sh` | Verify dial/button fire HA events |
| `10-test-full-approval-flow.sh` | E2E: command → approval request → dial → response |

## Files to Create/Modify

```
scripts/claudecodeui/voice-pe/
├── 00-backup-voice-pe-config.sh            # NEW - Backup before changes
├── esphome-voice-pe-claude-additions.yaml  # NEW - ESPHome reference
├── automation-claude-led-v2.yaml           # NEW - Updated automation
├── 07-create-approval-helper.sh            # NEW - Create input_boolean
├── 08-test-esphome-services.sh             # NEW - Test LED effects
├── 09-test-dial-button-events.sh           # NEW - Test dial/button
├── 10-test-full-approval-flow.sh           # NEW - E2E test
├── 98-restore-voice-pe-backup.sh           # NEW - Restore from backup
├── 99-factory-reset-voice-pe.sh            # NEW - Factory reset docs
├── backups/                                # NEW - Backup storage dir
└── ESPHOME-MODIFICATION-GUIDE.md           # UPDATE - Add complete YAML
```

## Execution Sequence

1. **[Parallel Batch 1]** Create backup/restore scripts + ESPHome YAML + helper script
2. **Run** backup script (save current Voice PE config)
3. **Run** helper creation script
4. **MANUAL**: User applies ESPHome YAML via dashboard, OTA update
5. **[Parallel Batch 2]** Create test scripts (08, 09)
6. Test ESPHome services (script 08)
7. Test dial/button events (script 09)
8. Create v2 automation file
9. Deploy v2 automation
10. Create + run full integration test (script 10)

## Risk Mitigation

- **ESPHome variable names** may differ from template - verify in actual firmware
- **OTA update risk** - validate YAML before install
- **GPIO pins** (16/18/17) from guide - verify against hardware docs

## Rollback Plan (Restore to Default HA Voice PE)

**CRITICAL**: Before ANY ESPHome modification, create backup and restore capability.

### Phase 0: Backup Current Firmware (Before Modification)

**File**: `scripts/claudecodeui/voice-pe/00-backup-voice-pe-config.sh`

1. Export current ESPHome YAML config via ESPHome dashboard API
2. Save to `scripts/claudecodeui/voice-pe/backups/voice-pe-YYYY-MM-DD.yaml`
3. Document current firmware version

### Restore Options (If Things Go Wrong)

| Scenario | Solution | Script |
|----------|----------|--------|
| OTA update fails, device unresponsive | Factory reset via USB flash | `99-factory-reset-voice-pe.sh` |
| Modified firmware has bugs | Restore backup YAML via ESPHome dashboard | `98-restore-voice-pe-backup.sh` |
| Want to revert to stock HA firmware | Flash official HA Voice PE firmware | Manual via ESPHome |

### Factory Reset Procedure

If Voice PE becomes unresponsive after OTA:
1. Download official HA Voice PE firmware from ESPHome dashboard
2. Connect Voice PE via USB-C
3. Hold boot button while connecting
4. Flash via `esphome run --device /dev/cu.usbserial-*`

**File**: `scripts/claudecodeui/voice-pe/99-factory-reset-voice-pe.sh`
- Downloads latest stock Voice PE firmware
- Provides USB flash instructions

## Implementation Strategy: Parallel Sub-Agents

Use Task tool with sub-agents to parallelize independent work:

### Batch 1 (Parallel) - Preparation Files
- **Agent A**: Create `00-backup-voice-pe-config.sh` + `98-restore-voice-pe-backup.sh`
- **Agent B**: Create `esphome-voice-pe-claude-additions.yaml`
- **Agent C**: Create `07-create-approval-helper.sh`

### Batch 2 (Sequential) - Run Backup + Helper
- Run backup script (must complete before firmware changes)
- Run helper creation script

### Batch 3 (Manual) - ESPHome Modification
- User applies YAML via ESPHome dashboard

### Batch 4 (Parallel) - Test Scripts
- **Agent A**: Create `08-test-esphome-services.sh`
- **Agent B**: Create `09-test-dial-button-events.sh`

### Batch 5 (Sequential) - Automation + Final Test
- Create `automation-claude-led-v2.yaml`
- Deploy to HA
- Create + run `10-test-full-approval-flow.sh`

## UX Flow After Implementation

```
User speaks: "Hey Claude, delete the temp files"
    ↓
Claude publishes: claude/command
    ↓
Voice PE LED: Native pulsing cyan (thinking)
    ↓
Claude publishes: claude/approval-request {tool: "Bash", description: "rm /tmp/*"}
    ↓
Voice PE LED: Amber (waiting)
input_boolean.claude_awaiting_approval: ON
    ↓
User rotates dial clockwise (approve) or anticlockwise (reject)
    ↓
Automation publishes: claude/approval-response {approved: true/false}
    ↓
Voice PE LED: Green (2s) or Red (2s), then off
```
