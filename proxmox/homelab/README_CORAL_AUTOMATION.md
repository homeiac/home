# Coral TPU Automation System

A comprehensive Python automation system that eliminates the manual Coral TPU initialization process after each system restart.

## 🎯 Problem Solved

Previously, after each system restart, you had to manually run:
```bash
cd /root/code/coral/pycoral/examples
python3 classify_image.py --model ../test_data/mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite --labels ../test_data/inat_bird_labels.txt --input ../test_data/parrot.jpg
```

This automation system now handles this process safely and automatically.

## 🏗️ Architecture

### Core Modules
- **`coral_models.py`** - Type-safe data models and enums
- **`coral_detection.py`** - USB device detection (Google/Unichip modes)  
- **`coral_config.py`** - LXC container configuration management
- **`coral_initialization.py`** - Safe Coral TPU initialization
- **`coral_automation.py`** - Main automation engine with decision matrix

### CLI Interface
- **`coral_tpu_automation.py`** - Production CLI script
- **`coral-tpu`** - Convenience wrapper command

## 🛡️ Safety Features

1. **Dual Safety Checks**: Never initializes when Coral is already in Google mode
2. **Frigate Protection**: Prevents breaking Frigate's TPU access  
3. **Automatic Backup**: Creates timestamped LXC config backups before changes
4. **Rollback Capability**: Restores previous configuration on failure
5. **Container Status Verification**: Ensures safe restart sequences

## 📦 Installation

The system is deployed via the included sync script:

```bash
# Deploy to target system
./scripts/sync_coral_automation.sh fun-bedbug.maas

# Deploy to custom host
./scripts/sync_coral_automation.sh hostname.maas root
```

## 🚀 Usage

### Manual Operations

```bash
# Check current system status
coral-tpu --status-only

# Preview what automation would do  
coral-tpu --dry-run

# Run automation manually
coral-tpu

# Run with verbose logging
coral-tpu --verbose

# Use custom container ID
coral-tpu --container-id 113
```

### Automatic Startup

```bash
# Enable automatic initialization on boot
systemctl enable coral-tpu-init.service
systemctl start coral-tpu-init.service

# Check service status
systemctl status coral-tpu-init.service

# View logs
journalctl -u coral-tpu-init.service -f
```

## 📊 System States

The automation engine handles these scenarios:

| Coral Mode | Container | Config | Action |
|------------|-----------|--------|--------|
| Google | Running | Correct | ✅ No action |
| Google | Stopped | Correct | 🔄 Restart container |  
| Google | Running | Wrong | 🔧 Update config + restart |
| Unichip | Stopped | Any | 🎯 Initialize + config + start |
| Unichip | Running | Any | ❌ Abort (unsafe) |
| Not Found | Any | Any | ❌ Abort (no device) |

## 🔧 Configuration

### File Locations
- **Source**: `/root/coral-automation/`
- **CLI**: `/usr/local/bin/coral-tpu`
- **Service**: `coral-tpu-init.service`
- **Backups**: `/root/coral-backups/`
- **Logs**: `/var/log/coral-tpu-automation.log`

### Environment Variables
- `PYTHONPATH`: Automatically set to `/root/coral-automation/src`
- Container ID defaults to `113` (Frigate LXC)
- Coral directory defaults to `/root/code`

## 🧪 Testing

The system includes comprehensive tests covering 50+ scenarios:

```bash
# Run all Coral automation tests (development)
poetry run pytest tests/test_coral_*.py -v

# Test specific modules
poetry run pytest tests/test_coral_models.py -v
```

## 📋 Logs and Monitoring

### Log Locations
- **Application**: `/var/log/coral-tpu-automation.log`
- **Systemd**: `journalctl -u coral-tpu-init.service`

### Key Log Messages
```
INFO - Coral detected in Google mode: Google Inc.
INFO - System is optimal - Coral initialized and config correct  
INFO - ✓ No actions required - system is optimal
```

## 🚨 Troubleshooting

### Common Issues

**Coral not detected**
```bash
# Check USB devices
lsusb | grep -E "(18d1:9302|1a6e:089a)"

# Check device permissions
ls -l /dev/bus/usb/003/004
```

**Container access issues**
```bash
# Check container status
pct status 113

# Check LXC config
cat /etc/pve/lxc/113.conf | grep -E "(dev0|cgroup)"
```

**Service not starting**
```bash
# Check service status
systemctl status coral-tpu-init.service

# Check service logs
journalctl -u coral-tpu-init.service --no-pager
```

### Manual Recovery

If automation fails, you can restore from backup:
```bash
# List available backups
ls -la /root/coral-backups/

# Restore specific backup
cp /root/coral-backups/lxc_113_20250816_115300.conf /etc/pve/lxc/113.conf

# Restart container
pct stop 113 && pct start 113
```

## 🔄 Updates

To update the automation system:

```bash
# Re-run deployment script from repo
./scripts/sync_coral_automation.sh fun-bedbug.maas

# Restart service to pick up changes
systemctl restart coral-tpu-init.service
```

## 📈 Benefits

- ✅ **Zero Manual Intervention**: Automatically handles Coral initialization
- ✅ **100% Safe**: Multiple safety layers prevent breaking Frigate
- ✅ **Comprehensive Logging**: Full audit trail of all actions
- ✅ **Backup Protection**: Automatic config backups before changes
- ✅ **Production Ready**: Systemd integration with proper error handling
- ✅ **Type Safe**: Full Python type hints prevent runtime errors

The system transforms the previously manual, error-prone Coral TPU initialization into a reliable, automated process.