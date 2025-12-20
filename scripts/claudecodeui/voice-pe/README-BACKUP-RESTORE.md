# Voice PE Backup and Restore Scripts

Scripts for managing Voice PE ESPHome configuration backups and factory resets.

## Quick Reference

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `00-backup-voice-pe-config.sh` | Backup current config | Before any changes, weekly maintenance |
| `98-restore-voice-pe-backup.sh` | Restore from backup | After failed update, rollback changes |
| `99-factory-reset-voice-pe.sh` | Factory reset guide | Device bricked, complete reset needed |

## Backup Workflow

```bash
# Create backup before making changes
./00-backup-voice-pe-config.sh

# Backups stored in: backups/voice-pe-YYYY-MM-DD-HHMMSS.yaml
```

**What gets backed up:**
- Complete ESPHome YAML configuration
- Wake word model configuration
- LED effects
- Voice assistant settings
- Network configuration
- Custom components

## Restore Workflow

```bash
# List available backups and select one
./98-restore-voice-pe-backup.sh

# Follow on-screen instructions:
# 1. Select backup by number
# 2. Config auto-copied to clipboard
# 3. Paste into ESPHome dashboard
# 4. Click Save → Install → Wirelessly
```

**Manual restore steps:**
1. Open ESPHome dashboard: http://homeassistant.maas:6052
2. Click "Edit" on `home_assistant_voice_09f5a3`
3. Paste backup config (replaces all)
4. Save and wirelessly install
5. Monitor logs for success

## Factory Reset

```bash
# Display comprehensive reset instructions
./99-factory-reset-voice-pe.sh
```

**Two reset methods:**

### Option 1: USB Recovery (Hardware)
- Download factory firmware from GitHub
- Enter bootloader mode (BOOT button + USB-C)
- Flash via https://web.esphome.io/
- Reconfigure WiFi and add to HA

### Option 2: Soft Reset (Dashboard)
- Replace config with factory YAML
- Install wirelessly
- No physical access needed

## Backup Strategy

**Recommended schedule:**
- Before every ESPHome update
- Before testing new wake word models
- Weekly automated backups (optional)
- Before major HA upgrades

**Retention:**
- Keep last 5 backups minimum
- One backup per major change
- Archive monthly snapshots

## Integration with Claude Code

These scripts support the Claude Code Voice Assistant integration:

```bash
# Before deploying Claude LED automation
./00-backup-voice-pe-config.sh
./04-deploy-automation.sh

# If something breaks
./98-restore-voice-pe-backup.sh
```

## Troubleshooting

### Backup fails to download
```bash
# Verify ESPHome dashboard is running
curl http://homeassistant.maas:6052

# Check device name matches
# Visit dashboard and confirm device name
```

### Restore not working
- Ensure ESPHome dashboard accessible
- Check file permissions on backup
- Verify backup is valid YAML (cat backup file)
- Try manual copy/paste if clipboard fails

### Factory reset needed when:
- Device won't boot
- OTA updates failing consistently
- Configuration corrupted
- WiFi settings locked out

## Related Documentation

- **ESPHome Modifications**: `ESPHOME-MODIFICATION-GUIDE.md`
- **Claude Integration**: `esphome-voice-pe-claude-additions.yaml`
- **Automation Config**: `automation-claude-led.yaml`

## File Locations

```
scripts/claudecodeui/voice-pe/
├── 00-backup-voice-pe-config.sh      # Backup script
├── 98-restore-voice-pe-backup.sh     # Restore script
├── 99-factory-reset-voice-pe.sh      # Reset guide
├── backups/                           # Backup storage
│   └── voice-pe-YYYY-MM-DD-HHMMSS.yaml
└── README-BACKUP-RESTORE.md          # This file
```

## Environment Variables

Scripts source credentials from:
```
$SCRIPT_DIR/../../../proxmox/homelab/.env
```

Required:
- `HA_TOKEN` - Home Assistant long-lived access token

## Safety Notes

- Always backup before changes
- Test restores in non-critical times
- Keep multiple backup generations
- Document any custom modifications
- Verify backup integrity after creation

## TAGS

esphome, backup, restore, factory-reset, voice-pe, voice-assistant, configuration, recovery
