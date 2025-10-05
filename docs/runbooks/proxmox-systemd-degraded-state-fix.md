# Proxmox Systemd Degraded State Fix Runbook

## Problem Description
Proxmox nodes may show systemd state as "degraded" even when fully functional. This is typically caused by services that fail to start but aren't actually needed for the system.

## Common Failed Services

### 1. openipmi.service
**Symptom**: `openipmi.service` fails with "Starting ipmi drivers ipmi failed!"

**Cause**: The service attempts to load IPMI/BMC drivers but the hardware doesn't have IPMI support. Common on consumer-grade hardware or systems without baseboard management controllers.

**Solution**:
```bash
systemctl disable openipmi.service
```

### 2. systemd-networkd-wait-online.service
**Symptom**: Service times out waiting for network connectivity

**Cause**: Proxmox uses traditional networking (`/etc/network/interfaces`), not systemd-networkd. The wait-online service expects systemd-networkd managed interfaces that don't exist.

**Solution**:
```bash
systemctl disable systemd-networkd-wait-online.service
```

## Resolution Steps

1. **Check system status**:
```bash
systemctl status
```

2. **List failed units**:
```bash
systemctl list-units --failed
```

3. **Disable unnecessary failed services**:
```bash
# For IPMI (if hardware doesn't support it)
systemctl disable openipmi.service

# For systemd-networkd (Proxmox uses traditional networking)
systemctl disable systemd-networkd-wait-online.service
```

4. **Reset failed state immediately**:
```bash
systemctl reset-failed
```

5. **Verify system is now "running"**:
```bash
systemctl status
```

## Verification
After disabling services and rebooting:
- System should show `State: running` instead of `State: degraded`
- No failed units should appear in `systemctl list-units --failed`
- Services remain disabled across reboots

## Applied Systems
- **still-fawn**: Both services disabled (October 5, 2025)

## Notes
- These services failing doesn't impact Proxmox functionality
- The degraded state is cosmetic but can mask real issues
- Safe to disable on systems without IPMI hardware
- Proxmox will continue using traditional networking regardless