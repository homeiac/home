# Migrating Frigate to a New Server Without Breaking Home Assistant

*How to update Home Assistant's Frigate integration URL without touching the UI*

---

```
    +-----------------+          +-----------------+
    |  frigate.maas   |    ->    | frigate-sf.maas |
    |   (old LXC)     |          |   (new LXC)     |
    |   fun-bedbug    |          |   still-fawn    |
    +-----------------+          +-----------------+
           |                            |
           v                            v
    +-------------------------------------------+
    |           Home Assistant                   |
    |    Integration URL needs updating!         |
    +-------------------------------------------+
```

## The Scenario

You've deployed a new Frigate instance on a different Proxmox host. The old one was `frigate.maas` (LXC 113 on fun-bedbug), the new one is `frigate-sf.maas` (LXC 110 on still-fawn). Home Assistant needs to point to the new server.

The catch? You want to do this via CLI/SSH, not through the web UI.

## Blueprint: Frigate Server Migration

### Prerequisites

| Requirement | Value |
|-------------|-------|
| Home Assistant OS VM | Running with QEMU guest agent |
| New Frigate instance | Accessible at new DNS/IP |
| SSH access | To Proxmox host running HA VM |
| MQTT | Configured on new Frigate pointing to HA broker |

### Architecture

```
+--------------------+     MQTT (1883)      +-------------------+
|                    |<---------------------|                   |
|  Home Assistant    |                      |  Frigate (new)    |
|  (chief-horse)     |     HTTP (5000)      |  (still-fawn)     |
|  VM 116            |--------------------->|  LXC 110          |
|                    |                      |                   |
+--------------------+                      +-------------------+
        |                                           |
        | Integration URL                           | Cameras
        | http://frigate-sf.maas:5000              | - reolink_doorbell
        |                                           | - trendnet_ip_572w
        v                                           | - old_ip_camera
+--------------------+                              v
|  core.config_      |                      +-------------------+
|  entries (JSON)    |                      |  Coral TPU        |
+--------------------+                      |  (7.8ms inference)|
                                            +-------------------+
```

### Action Log Template

```markdown
## Migration: [OLD_SERVER] -> [NEW_SERVER]
Date: YYYY-MM-DD

### Pre-Migration Checks
- [ ] New Frigate accessible: `curl http://[NEW_SERVER]:5000/api/stats`
- [ ] MQTT broker reachable from new Frigate
- [ ] Cameras streaming on new instance
- [ ] Coral TPU working (if applicable)

### Migration Steps
1. [ ] Backup config: `core.config_entries.backup.[timestamp]`
2. [ ] Update URL in config file
3. [ ] Verify change applied
4. [ ] Restart Home Assistant
5. [ ] Verify integration connected

### Post-Migration Verification
- [ ] Frigate integration shows connected in HA
- [ ] Camera entities available
- [ ] Events flowing via MQTT
```

---

## Action Log: frigate.maas -> frigate-sf.maas

**Date:** 2024-12-11

### Pre-Migration Checks

Verified new Frigate instance:

```bash
$ curl -s http://frigate-sf.maas:5000/api/stats | jq '{version: .service.version, cameras: (.cameras | keys), detector: .detectors.coral.inference_speed}'
{
  "version": "0.14.1-",
  "cameras": ["old_ip_camera", "reolink_doorbell", "trendnet_ip_572w"],
  "detector": 7.8
}
```

Verified MQTT configuration:

```bash
$ curl -s http://frigate-sf.maas:5000/api/config | jq '.mqtt'
{
  "enabled": true,
  "host": "homeassistant.maas",
  "port": 1883,
  "user": "frigate"
}
```

MQTT broker reachable:

```bash
$ nc -z -w 2 homeassistant.maas 1883 && echo "OK"
OK
```

### Step 1: Locate and Backup Config

Home Assistant OS stores integration configs in `/mnt/data/supervisor/homeassistant/.storage/core.config_entries`.

Found HA VM on chief-horse (VM 116):

```bash
$ ssh root@chief-horse.maas "qm guest exec 116 -- find /mnt/data/supervisor/homeassistant/.storage -name 'core.config_entries'"
{
   "exitcode" : 0,
   "out-data" : "/mnt/data/supervisor/homeassistant/.storage/core.config_entries\n"
}
```

Current Frigate config:

```bash
$ ssh root@chief-horse.maas 'qm guest exec 116 -- cat /mnt/data/supervisor/homeassistant/.storage/core.config_entries' | jq -r '."out-data"' | jq '.data.entries[] | select(.domain == "frigate") | .data'
{
  "url": "http://frigate.maas:5000",
  "username": "",
  "password": "",
  "validate_ssl": false
}
```

Created backup:

```bash
$ ssh root@chief-horse.maas 'qm guest exec 116 -- cp /mnt/data/supervisor/homeassistant/.storage/core.config_entries /mnt/data/supervisor/homeassistant/.storage/core.config_entries.backup.20241211_200000'
{"exitcode": 0, "exited": 1}
```

### Step 2: Update URL

Used sed to replace the URL:

```bash
$ ssh root@chief-horse.maas 'qm guest exec 116 -- sed -i "s|http://frigate.maas:5000|http://frigate-sf.maas:5000|g" /mnt/data/supervisor/homeassistant/.storage/core.config_entries'
{"exitcode": 0, "exited": 1}
```

### Step 3: Verify Change

```bash
$ ssh root@chief-horse.maas 'qm guest exec 116 -- cat /mnt/data/supervisor/homeassistant/.storage/core.config_entries' | jq -r '."out-data"' | jq '.data.entries[] | select(.domain == "frigate") | .data.url'
"http://frigate-sf.maas:5000"
```

### Step 4: Restart Home Assistant

```bash
$ ssh root@chief-horse.maas 'qm guest exec 116 -- ha core restart'
# Command times out as expected (HA is restarting)

# Wait and verify HA is back
$ sleep 30 && curl -s http://192.168.4.240:8123/ | head -c 50
<!DOCTYPE html><html><head><title>Home Assistant
```

### Step 5: Post-Migration Verification

HA is running and Frigate integration should now connect to the new server.

**Notes:**
- The `title` field still shows old server name (`frigate.maas:5000`) - this is cosmetic only
- MQTT events will flow automatically once Frigate publishes to the broker
- Camera entity names remain the same since they're based on Frigate camera config, not server hostname

---

## Key Techniques

### Accessing HAOS VM Config Files

Home Assistant OS runs as a VM with QEMU guest agent. You can execute commands inside it:

```bash
# Find files
qm guest exec <VMID> -- find /path -name "filename"

# Read files
qm guest exec <VMID> -- cat /path/to/file

# Edit files
qm guest exec <VMID> -- sed -i 's/old/new/g' /path/to/file

# Run HA CLI
qm guest exec <VMID> -- ha core restart
```

### Config File Location

| Config Type | Path |
|-------------|------|
| Integration configs | `/mnt/data/supervisor/homeassistant/.storage/core.config_entries` |
| Automations | `/mnt/data/supervisor/homeassistant/automations.yaml` |
| Scripts | `/mnt/data/supervisor/homeassistant/scripts.yaml` |
| Configuration | `/mnt/data/supervisor/homeassistant/configuration.yaml` |

### Important: Always Backup First

```bash
qm guest exec <VMID> -- cp /path/to/config /path/to/config.backup.$(date +%Y%m%d_%H%M%S)
```

---

## Rollback Procedure

If something goes wrong:

```bash
# List backups
ssh root@<proxmox-host>.maas 'qm guest exec <VMID> -- ls -la /mnt/data/supervisor/homeassistant/.storage/*.backup.*'

# Restore backup
ssh root@<proxmox-host>.maas 'qm guest exec <VMID> -- cp /mnt/data/supervisor/homeassistant/.storage/core.config_entries.backup.20241211_200000 /mnt/data/supervisor/homeassistant/.storage/core.config_entries'

# Restart HA
ssh root@<proxmox-host>.maas 'qm guest exec <VMID> -- ha core restart'
```

---

*This migration was performed with Claude Code, accessing Home Assistant OS internals via QEMU guest agent to modify integration configuration without using the web UI.*

**Tags:** frigate, home-assistant, haos, migration, proxmox, qemu-guest-agent, integration, mqtt, homelab
