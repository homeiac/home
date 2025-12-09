# Frigate Upgrade Decision Framework

## MANDATORY Pre-Upgrade Checks

**BEFORE considering any Frigate upgrade, ALWAYS follow this checklist:**

### 1. Check PVE Helper Scripts Version Support

```bash
# Check current PVE Helper Scripts Frigate version
curl -s https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/install/frigate-install.sh | grep -E "(v[0-9]+\.[0-9]+\.[0-9]+|Installing Frigate)"

# Expected output format:
# msg_info "Installing Frigate v0.14.1 (Perseverance)"
# curl -fsSL "https://github.com/blakeblackshear/frigate/archive/refs/tags/v0.14.1.tar.gz"
```

### 2. Compare with Latest Frigate Release

```bash
# Check latest Frigate release
curl -s https://api.github.com/repos/blakeblackshear/frigate/releases/latest | jq -r '.tag_name'

# Check if PVE Helper Scripts are up to date
SCRIPT_VERSION=$(curl -s https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/install/frigate-install.sh | grep -o "v[0-9]\+\.[0-9]\+\.[0-9]\+" | head -1)
LATEST_VERSION=$(curl -s https://api.github.com/repos/blakeblackshear/frigate/releases/latest | jq -r '.tag_name')
echo "PVE Scripts: $SCRIPT_VERSION"
echo "Latest Frigate: $LATEST_VERSION"
```

### 3. Decision Matrix

| PVE Scripts Status | Action | Rationale |
|-------------------|--------|-----------|
| **Scripts = Latest Version** | ✅ **Proceed with upgrade** | Safe, supported path |
| **Scripts < Latest Version** | ❌ **WAIT** | Manual upgrade breaks LXC integration |
| **Scripts > Latest Version** | ⚠️ **Investigate** | Unusual - check for beta/dev versions |

## Current Configuration (LXC 113)

### Installation Method
- **Type**: LXC container (NOT Docker)
- **Script**: PVE Helper Scripts community-scripts/ProxmoxVE
- **Host**: fun-bedbug.maas (AMD A9-9400, 2 cores, 7.22GB RAM)
- **Current Version**: 0.14.1

### Hardware Acceleration Stack
```yaml
GPU Acceleration: AMD Radeon R5 with VA-API
- Environment: LIBVA_DRIVER_NAME=radeonsi
- FFmpeg: hwaccel_args: preset-vaapi
- Performance: Offloads video decode/encode from CPU

TPU Acceleration: Google Coral USB
- Device: /dev/bus/usb/003/XXX (changes after replug!)
- Automation: coral-tpu-init.service (auto-initialization)
- Working Config Backup: proxmox/backups/lxc-113-container-config.conf
- Purpose: Object detection inference
- Status Check: coral-tpu --status-only
- Critical Info: docs/reference/frigate-016-upgrade-lessons.md#coral-tpu-critical-configuration-version-independent
```

### Why Manual Updates Are Prohibited

1. **LXC Integration**: PVE Helper Scripts create custom systemd services, file paths, and permissions
2. **Dependency Management**: Scripts handle complex Python wheel building and FFmpeg compilation
3. **Hardware Acceleration**: Custom VA-API and Coral TPU setup specific to LXC environment
4. **Service Configuration**: Custom s6-overlay to systemd service translation
5. **Rollback Complexity**: Manual updates break clean rollback via PVE snapshots

## Upgrade Monitoring Process

### Weekly Check (Automated)
```bash
#!/bin/bash
# Add to cron: 0 9 * * 1 /root/scripts/check-frigate-updates.sh

SCRIPT_VERSION=$(curl -s https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/install/frigate-install.sh | grep -o "v[0-9]\+\.[0-9]\+\.[0-9]\+" | head -1)
LATEST_VERSION=$(curl -s https://api.github.com/repos/blakeblackshear/frigate/releases/latest | jq -r '.tag_name')

if [ "$SCRIPT_VERSION" != "$LATEST_VERSION" ]; then
    echo "FRIGATE UPDATE AVAILABLE:"
    echo "  PVE Scripts: $SCRIPT_VERSION"
    echo "  Latest Release: $LATEST_VERSION"
    echo "  Status: Waiting for PVE Helper Scripts update"
else
    echo "Frigate PVE Scripts are up to date: $SCRIPT_VERSION"
fi
```

### Manual Monitoring
- **Repository**: Watch https://github.com/community-scripts/ProxmoxVE
- **File**: install/frigate-install.sh
- **Notifications**: Enable GitHub notifications for releases
- **Forum**: Monitor Proxmox VE community forums for update discussions

## Face Recognition Feature Status

### Requirements
- **Minimum Version**: Frigate v0.16.0+
- **Hardware**: AMD GPU recommended for "large" model accuracy
- **Current Status**: Waiting for PVE Helper Scripts v0.16.0 support

### Configuration (Future)
```yaml
# When v0.16.0 becomes available via PVE Helper Scripts
face_recognition:
  enabled: true
  # Large model recommended for AMD Radeon R5 GPU
```

## Emergency Manual Update (Last Resort Only)

**⚠️ ONLY use if PVE Helper Scripts are discontinued or emergency security fix needed**

### Prerequisites
```bash
# Full backup strategy
pct snapshot 113 emergency-manual-update-$(date +%Y%m%d_%H%M%S)
pct exec 113 -- tar -czf /tmp/full-config-backup.tar.gz /config/ /opt/frigate/ /etc/systemd/system/*frigate* /etc/systemd/system/*go2rtc* /etc/systemd/system/*nginx*
```

### Rollback Plan
```bash
# Immediate rollback via snapshot
pct rollback 113 emergency-manual-update-YYYYMMDD_HHMMSS

# Or restore PVE Helper Scripts state
# 1. Destroy current container
# 2. Create new container via PVE Helper Scripts
# 3. Restore configuration and data from backup
```

## Integration with CLAUDE.md

This decision framework should be referenced in CLAUDE.md for AI agents:

```markdown
### Frigate Upgrade Policy
- **Pre-Check Required**: Always verify PVE Helper Scripts version support first
- **Reference**: docs/reference/frigate-upgrade-decision-framework.md
- **No Manual Updates**: Wait for official PVE Helper Scripts support
- **Hardware Constraints**: fun-bedbug is resource-constrained (AMD A9-9400)
```

## Version History

| Date | PVE Scripts Version | Latest Frigate | Status | Notes |
|------|-------------------|----------------|---------|--------|
| 2025-01-XX | v0.14.1 | v0.16.0 | ❌ Waiting | Face recognition available in v0.16.0 |
| 2024-XX-XX | v0.14.1 | v0.14.1 | ✅ Current | Initial documentation |

---

**Key Principle**: Patience with PVE Helper Scripts updates prevents manual installation complexity and maintains supportable LXC configuration.