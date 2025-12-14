# Incident: Home Assistant Config Entries Corruption

**Date:** 2025-12-13
**Duration:** ~2 hours
**Impact:** All HA integrations lost configuration, Frigate cameras unavailable
**Tags:** homeassistant, haos, frigate, mqtt, dns, corruption, config_entries

## Summary

The Home Assistant `core.config_entries` storage file became corrupted (zero-length), causing HA to lose all integration configurations. This cascaded into multiple issues requiring systematic debugging.

## Symptoms

1. HA showed error: "core.config_entries could not be parsed... zero-length, empty document"
2. Frigate cameras showed "Could not find camera entity"
3. Frigate card showed "API error whilst subscribing to events for unknown Frigate instance"

## Root Cause Analysis

### Primary Issue: Config Entries Corruption
The `/config/.storage/core.config_entries` file became empty (0 bytes). HA auto-generated a new default config, but:
- Integration entry IDs changed
- Entity registrations were lost
- MQTT discovery messages weren't being processed

### Secondary Issue: Frigate MQTT User Missing
The Mosquitto broker addon only had `homeassistant` and `addons` users. The `frigate` user (used by Frigate K8s deployment) didn't exist, preventing MQTT connection.

**Location:** HA Mosquitto addon config
**Fix:** Add `frigate` user in Settings → Add-ons → Mosquitto broker → Configuration → logins

### Tertiary Issue: HAOS DNS Resolution
HAOS VM was using MAAS DNS (192.168.4.53) which doesn't have `.homelab` domain entries. The `frigate.app.homelab` hostname couldn't be resolved from inside HA.

**Fix:** Added OPNsense (192.168.4.1) as primary DNS via NetworkManager:
```bash
nmcli connection modify "Supervisor enp0s18" ipv4.dns "192.168.4.1"
nmcli connection reload
nmcli connection up "Supervisor enp0s18"
```

### Quaternary Issue: Advanced-Camera-Card Instance Mismatch
The `custom:advanced-camera-card` was looking for a Frigate instance named `frigate` but the re-added integration had a different identifier. The card's `frigate` config block caused API subscription errors.

**Fix:** Removed the `frigate` block from card config, using basic camera mode instead.

## Resolution Steps

1. **Verified config_entries** - File was auto-regenerated with valid JSON (59KB)
2. **Added Frigate MQTT user** - In Mosquitto addon configuration
3. **Fixed HAOS DNS** - Added OPNsense as primary DNS server
4. **Re-added Frigate integration** - Using direct IP (192.168.4.82:5000)
5. **Updated dashboard cards** - Removed problematic `frigate` block

## Scripts Created/Updated

| Script | Purpose |
|--------|---------|
| `scripts/haos/backup-dashboard.sh` | Backup HAOS dashboard configs before changes |
| `scripts/haos/fix-frigate-dashboard.sh` | Update Frigate dashboard card configs |
| `scripts/frigate/list-frigate-entities.sh` | List all Frigate entities in HA |
| `scripts/frigate/reload-frigate-integration.sh` | Reload Frigate integration via API |
| `scripts/ha-dns-homelab/07-fix-ha-vm-dns.sh` | Fix DNS resolution in HAOS VM |

## Key Learnings

1. **HAOS uses hassio_dns container** - Integrations resolve DNS through this container, not the host's resolv.conf directly. However, hassio_dns forwards to the host's configured DNS servers.

2. **Mosquitto addon users** - External MQTT clients (like Frigate on K8s) need explicit user entries in the Mosquitto addon config. The `homeassistant` and `addons` users are for internal HA use only.

3. **qm guest exec returns JSON** - When scripting against HAOS via Proxmox's `qm guest exec`, output is JSON-wrapped. Parse with `jq -r '.["out-data"]'`.

4. **Frigate integration instance IDs** - The HACS Frigate integration uses entry_id for identification. Dashboard cards may have cached references to old instance names.

## Prevention

1. **Regular backups** - PBS backups of HAOS VM
2. **Monitor storage health** - The corruption may indicate storage issues
3. **Document MQTT users** - Keep track of external MQTT clients and their credentials

## Related Files

- HAOS config storage: `/mnt/data/supervisor/homeassistant/.storage/`
- Mosquitto addon data: `/mnt/data/supervisor/addons/data/core_mosquitto/`
- Dashboard backups: `proxmox/backups/haos-dashboards/`
