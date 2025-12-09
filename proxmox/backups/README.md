# Frigate LXC 113 Backups (fun-bedbug.maas)

## Files

| File | Location on Host | Purpose |
|------|------------------|---------|
| `lxc-113-container-config.conf` | `/etc/pve/lxc/113.conf` | Proxmox LXC container definition |
| `frigate-app-config.yml` | Container: `/config/config.yml` | Frigate application config |

## LXC Container Config (`lxc-113-container-config.conf`)

Proxmox container settings including:
- **Coral USB passthrough**: `dev0: /dev/bus/usb/003/XXX`
- **cgroup2 permissions**: USB (189:*), DRI (226:*)
- **GPU passthrough**: AMD Radeon R5 for VAAPI acceleration
- **Storage**: 500GB on local-3TB-backup

### After Coral USB Replug

The device number changes when Coral is physically unplugged/replugged:

```bash
# Find new device number
lsusb | grep -i google
# Output: Bus 003 Device 009: ID 18d1:9302 Google Inc.

# Update LXC config
sed -i 's|dev0: /dev/bus/usb/003/.*|dev0: /dev/bus/usb/003/009|' /etc/pve/lxc/113.conf

# Restart container
pct stop 113 && pct start 113
```

## Frigate App Config (`frigate-app-config.yml`)

Application settings including:
- **Cameras**: old_ip_camera, trendnet_ip_572w, reolink_doorbell
- **Detector**: Coral EdgeTPU USB (`type: edgetpu, device: usb`)
- **MQTT**: homeassistant.maas:1883
- **Hardware acceleration**: VAAPI (AMD radeonsi)

## Restore Procedures

### Full Restore (both configs)

```bash
# 1. Restore LXC config (on Proxmox host)
pct stop 113
cp lxc-113-container-config.conf /etc/pve/lxc/113.conf
# Update dev0 device path if needed (see above)
pct start 113

# 2. Restore Frigate config (inside container)
pct exec 113 -- cp /path/to/frigate-app-config.yml /config/config.yml
pct exec 113 -- systemctl restart frigate
```

### Verify Coral TPU Working

```bash
# Check Frigate logs
pct exec 113 -- cat /dev/shm/logs/frigate/current | grep -i "TPU found"

# Check detector stats
pct exec 113 -- curl -s http://127.0.0.1:5000/api/stats | jq '.detectors'
```

## Related Documentation

- [Coral TPU Integration Guide](../guides/google-coral-tpu-frigate-integration.md)
- [Coral TPU Automation Runbook](../../docs/source/md/coral-tpu-automation-runbook.md)
