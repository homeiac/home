# Voice PE Scripts Index

Complete reference for Voice PE automation and backup scripts.

## Script Categories

### 🎯 Core Automation (01-07)
**Integration testing and deployment**

- `01-discover-entities.sh` - Discover Voice PE entities in HA
- `02-get-led-attributes.sh` - Query LED strip attributes
- `03-test-led-color.sh` - Test LED color changes
- `04-deploy-automation.sh` - Deploy Claude LED automation
- `05-test-mqtt-led-flow.sh` - Test MQTT → LED flow
- `06-check-automation-status.sh` - Check automation health
- `07-create-approval-helper.sh` - Create approval input_boolean helper

### 💾 Backup & Recovery (00, 98-99)
**Configuration management and disaster recovery**

- `00-test-backup-system.sh` - Test backup system components
- `00-backup-voice-pe-config.sh` - Backup ESPHome config
- `98-restore-voice-pe-backup.sh` - Restore from backup
- `99-factory-reset-voice-pe.sh` - Factory reset guide

## Quick Start

### First Time Setup
```bash
# 1. Test system
./00-test-backup-system.sh

# 2. Create initial backup
./00-backup-voice-pe-config.sh

# 3. Discover entities
./01-discover-entities.sh

# 4. Deploy Claude integration
./04-deploy-automation.sh
```

### Daily Operations
```bash
# Check automation status
./06-check-automation-status.sh

# Test LED feedback
./03-test-led-color.sh

# Test full MQTT flow
./05-test-mqtt-led-flow.sh
```

### Maintenance
```bash
# Backup before changes
./00-backup-voice-pe-config.sh

# After making changes, verify
./00-test-backup-system.sh
./06-check-automation-status.sh
```

### Disaster Recovery
```bash
# Restore from backup
./98-restore-voice-pe-backup.sh

# Factory reset (if needed)
./99-factory-reset-voice-pe.sh
```

## Configuration Files

### ESPHome Configuration
- `esphome-voice-pe-claude-additions.yaml` - ESPHome YAML additions
- `ESPHOME-MODIFICATION-GUIDE.md` - How to modify ESPHome config

### Home Assistant
- `automation-claude-led.yaml` - HA automation for LED control

### Backups
- `backups/` - Timestamped ESPHome config backups
- `backups/voice-pe-YYYY-MM-DD-HHMMSS.yaml` - Backup format

## Documentation

- `README-BACKUP-RESTORE.md` - Backup/restore workflow
- `ESPHOME-MODIFICATION-GUIDE.md` - ESPHome customization
- `SCRIPT-INDEX.md` - This file

## Workflow Diagrams

### Backup Workflow
```
00-backup-voice-pe-config.sh
    ↓
Download from ESPHome API
    ↓
Save to backups/voice-pe-TIMESTAMP.yaml
    ↓
Verify and report
```

### Restore Workflow
```
98-restore-voice-pe-backup.sh
    ↓
List available backups
    ↓
User selects backup
    ↓
Copy to clipboard
    ↓
User pastes in ESPHome dashboard
    ↓
Install wirelessly
```

### Claude Integration Workflow
```
User approves request
    ↓
input_boolean.claude_approval = ON
    ↓
automation-claude-led.yaml triggers
    ↓
Publish MQTT (approve/deny topic)
    ↓
ESPHome receives MQTT
    ↓
Light effect plays (pulse green/red)
```

## Script Naming Convention

- `00-XX` - System/infrastructure scripts
- `01-07` - Integration and testing scripts
- `98-99` - Recovery and reset scripts

## Environment Variables

All scripts source from: `$SCRIPT_DIR/../../../proxmox/homelab/.env`

Required variables:
- `HA_TOKEN` - Home Assistant long-lived access token

## Common Tasks

### Add new wake word
1. Backup: `./00-backup-voice-pe-config.sh`
2. Edit ESPHome config (follow ESPHOME-MODIFICATION-GUIDE.md)
3. Install via dashboard
4. Verify: `./01-discover-entities.sh`

### Update ESPHome firmware
1. Backup: `./00-backup-voice-pe-config.sh`
2. Update via ESPHome dashboard
3. Test: `./00-test-backup-system.sh`
4. Verify: `./06-check-automation-status.sh`

### Troubleshoot LED issues
1. Check entity: `./02-get-led-attributes.sh`
2. Test manual: `./03-test-led-color.sh`
3. Test MQTT: `./05-test-mqtt-led-flow.sh`
4. Check automation: `./06-check-automation-status.sh`

### Rollback after bad update
1. Run: `./98-restore-voice-pe-backup.sh`
2. Select backup before update
3. Follow restore instructions
4. Verify: `./00-test-backup-system.sh`

## Troubleshooting

### Script fails with "HA_TOKEN not found"
```bash
# Verify .env file exists
ls -l /Users/10381054/code/home/proxmox/homelab/.env

# Check token is set
grep HA_TOKEN /Users/10381054/code/home/proxmox/homelab/.env
```

### ESPHome dashboard not accessible
```bash
# Check HA is running
curl http://homeassistant.maas:8123

# Check ESPHome addon status via HA
# Settings → Add-ons → ESPHome
```

### Backup download fails
```bash
# Verify device name
# Visit http://homeassistant.maas:6052
# Device must be exactly: home_assistant_voice_09f5a3

# Test manual download
curl http://homeassistant.maas:6052/download/home_assistant_voice_09f5a3
```

### LEDs not responding
```bash
# Check entity exists
./01-discover-entities.sh | grep light.voice_pe_led

# Check attributes
./02-get-led-attributes.sh

# Test direct control
./03-test-led-color.sh
```

## Related Repositories

- **ESPHome**: https://github.com/esphome/esphome
- **HA Voice**: https://github.com/home-assistant/voice
- **ESPHome Firmware**: https://github.com/esphome/firmware

## Tags

voice-pe, esphome, backup, automation, led, claude-integration, home-assistant, voice-assistant, mqtt
