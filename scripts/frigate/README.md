# Frigate Migration Scripts

Scripts for safely migrating from still-fawn Frigate LXC to K8s Frigate on pumped-piglet.

## Quick Reference

### New Scripts for Home Assistant Integration

```bash
# 1. Check current HA Frigate integration
./check-ha-frigate-integration.sh

# 2. Verify K8s Frigate is healthy (must pass before switching HA)
export KUBECONFIG=~/kubeconfig
./verify-frigate-k8s.sh

# 3. Switch HA to K8s Frigate (provides manual instructions)
./switch-ha-to-k8s-frigate.sh
```

### Key URLs

- **Old Frigate (LXC)**: http://still-fawn.maas:5000 or http://192.168.4.17:5000
- **New Frigate (K8s)**: http://192.168.4.83:5000
- **Home Assistant**: http://homeassistant.maas:8123
- **MQTT Client ID (K8s)**: frigate-k8s

### Current Status

- K8s Frigate: HEALTHY (all 7 checks passing)
  - Version: 0.16.0-c2f8de9
  - Cameras: 3/3 enabled and streaming at 5.1 FPS
  - Face recognition: Enabled (large model)
  - NVIDIA GPU: Configured and working
  - MQTT: Connected with client_id frigate-k8s

## Overview

These scripts help manage the transition from the LXC-based Frigate deployment on still-fawn.maas to a Kubernetes-based deployment on pumped-piglet.

### Current Setup

**still-fawn Frigate (LXC 110)**:
- Host: still-fawn.maas
- Container ID: 110
- Coral USB TPU: Attached via USB passthrough
- Storage: 116GB recordings on local-3TB-backup ZFS pool
- Status: Production, ready to be phased out

**K8s Frigate**:
- Host: pumped-piglet (K3s cluster)
- Deployment: Managed via GitOps/Flux
- Coral USB TPU: Needs to be migrated from still-fawn
- Storage: New persistent volume

## Scripts

### 1. `check-ha-frigate-integration.sh`

Check current Frigate integration configuration in Home Assistant.

**Checks performed**:
- Home Assistant API accessibility
- Frigate entities (sensors, cameras)
- Integration status
- Provides manual verification instructions

**Usage**:
```bash
./check-ha-frigate-integration.sh
```

**Note**: The Frigate integration URL cannot be retrieved via API. You must check it manually in the HA UI at Settings → Devices & Services → Integrations.

### 2. `verify-frigate-k8s.sh`

Comprehensive verification script for K8s Frigate deployment.

**Checks performed**:
- Kubernetes pod status (Running and Ready)
- Frigate API version (0.16.0-c2f8de9)
- Camera status (all 3 cameras enabled and streaming)
- MQTT configuration (client_id: frigate-k8s)
- Face recognition (enabled with large model)
- Camera streaming FPS
- Hardware acceleration (NVIDIA GPU)

**Usage**:
```bash
export KUBECONFIG=~/kubeconfig
./verify-frigate-k8s.sh
```

**Exit codes**:
- `0`: All checks passed - Frigate K8s is healthy
- `1`: One or more checks failed - do NOT switch HA yet

### 3. `switch-ha-to-k8s-frigate.sh`

Switch Home Assistant Frigate integration from LXC to Kubernetes instance.

**What it does**:
1. Runs K8s Frigate verification (`verify-frigate-k8s.sh`)
2. Provides detailed manual instructions for switching in HA UI
3. Optionally opens HA integrations page in browser
4. Provides post-switch verification steps
5. Includes rollback instructions

**Usage**:
```bash
./switch-ha-to-k8s-frigate.sh
```

**Important**: The Frigate integration URL must be changed manually in Home Assistant UI. The script provides step-by-step instructions.

**Manual steps provided**:
1. Remove old Frigate integration (LXC)
2. Add new Frigate integration with URL: http://192.168.4.83:5000
3. Verify cameras and entities
4. Test automations

### 4. `shutdown-still-fawn-frigate.sh`

Safely shuts down the still-fawn Frigate LXC after K8s migration is verified.

**What it does**:
1. Runs K8s Frigate verification (`verify-frigate-k8s.sh`)
2. Prompts for user confirmation
3. Creates a snapshot: `pre-k8s-migration-YYYYMMDD-HHMMSS`
4. Stops LXC 110
5. Disables auto-start
6. Provides rollback instructions

**Usage**:
```bash
./shutdown-still-fawn-frigate.sh
```

**Important**: This does NOT delete recordings on still-fawn. The 116GB of recordings remain on local-3TB-backup and can be imported later.

### 3. `rollback-to-still-fawn.sh`

Rolls back to still-fawn Frigate if K8s migration encounters issues.

**What it does**:
1. Re-enables auto-start for LXC 110
2. Starts the container
3. Verifies Frigate is running
4. Checks API and Coral TPU
5. Provides instructions for updating Home Assistant

**Usage**:
```bash
./rollback-to-still-fawn.sh
```

## Migration Workflow

### Pre-Migration Checklist

- [x] K8s Frigate deployment is complete (pumped-piglet)
- [x] NVIDIA GPU acceleration is configured
- [x] All 3 cameras are configured in K8s Frigate
- [x] MQTT is enabled with client_id: frigate-k8s
- [x] Face recognition is enabled (large model)
- [x] LoadBalancer IP is assigned: 192.168.4.83
- [x] All cameras are streaming (5.1 FPS)
- [ ] Home Assistant integration switched to K8s URL

### Migration Steps

1. **Check current HA integration**:
   ```bash
   ./check-ha-frigate-integration.sh
   ```
   This will show which Frigate entities exist and provide manual check instructions.

2. **Verify K8s Frigate is healthy**:
   ```bash
   export KUBECONFIG=~/kubeconfig
   ./verify-frigate-k8s.sh
   ```
   **Expected result**: All checks pass (7/7 green checkmarks)

3. **Test K8s Frigate thoroughly**:
   - Open Frigate UI: http://192.168.4.83:5000
   - Verify all camera feeds are working
   - Check face recognition is working
   - Test recording functionality

4. **Switch Home Assistant to K8s Frigate**:
   ```bash
   ./switch-ha-to-k8s-frigate.sh
   ```
   Follow the detailed manual instructions provided by the script:
   - Remove old integration (LXC URL)
   - Add new integration with URL: http://192.168.4.83:5000
   - Verify cameras and entities appear
   - Test automations

5. **Verify HA integration after switch**:
   ```bash
   ./check-ha-frigate-integration.sh
   ```
   Verify Frigate entities are still working with K8s instance.

6. **Shutdown still-fawn Frigate** (optional - only after HA is working):
   ```bash
   ./shutdown-still-fawn-frigate.sh
   ```

### Rollback (if needed)

If you encounter issues with K8s Frigate after shutdown:

1. **Rollback to still-fawn**:
   ```bash
   ./rollback-to-still-fawn.sh
   ```

2. **Update Home Assistant** back to still-fawn URL

3. **Fix K8s Frigate issues** before attempting migration again

## Data Migration

### Recordings

The 116GB of recordings on still-fawn are **NOT deleted** during shutdown.

**To import recordings later** (optional):

1. **Mount still-fawn storage in K8s Frigate pod**:
   - Add NFS mount or direct storage access
   - Mount local-3TB-backup ZFS pool

2. **Copy recordings**:
   ```bash
   # From still-fawn LXC path
   /var/lib/frigate/recordings

   # To K8s Frigate path
   /media/frigate/recordings
   ```

3. **Restart Frigate** - it will automatically detect and index the recordings

### Configuration

Configuration is managed separately:
- **still-fawn**: `/etc/frigate/config.yml` in LXC
- **K8s**: ConfigMap in Kubernetes

You'll need to manually ensure both configs match before migration.

## Coral USB TPU Migration

The Coral USB TPU is currently attached to still-fawn.maas.

**After shutting down still-fawn Frigate**:

1. The Coral USB device will still be physically connected to still-fawn
2. You can either:
   - **Keep it on still-fawn** and use USB/IP to expose it to K8s
   - **Move it to pumped-piglet** (requires physical USB cable re-routing)
   - **Use a different Coral** if you have multiple devices

**Current approach** (based on scripts):
- K8s Frigate on pumped-piglet should already have Coral access configured
- Verify with `verify-frigate-k8s.sh` before shutdown

## Troubleshooting

### K8s Frigate API not responding

```bash
# Check pod logs
kubectl logs -n default -l app=frigate

# Check pod events
kubectl describe pod -n default -l app=frigate

# Verify LoadBalancer IP
kubectl get svc frigate -n default
```

### Coral TPU not detected in K8s

```bash
# Check if USB device is visible in pod
kubectl exec -n default -l app=frigate -- ls -l /dev/bus/usb/

# Check Frigate logs for Coral initialization
kubectl logs -n default -l app=frigate | grep -i coral
```

### Rollback fails to start container

```bash
# Manually start on still-fawn
ssh root@still-fawn.maas 'pct start 110'

# Check container logs
ssh root@still-fawn.maas 'pct exec 110 -- tail -100 /dev/shm/logs/frigate/current'
```

## Reference

- **LXC Host**: still-fawn.maas
- **LXC ID**: 110
- **Recordings**: /var/lib/frigate/recordings (116GB on local-3TB-backup)
- **K8s Host**: pumped-piglet
- **K8s Namespace**: default
- **Service**: frigate (LoadBalancer)

## Safety Features

All scripts include:
- ✅ Pre-flight verification checks
- ✅ User confirmation prompts
- ✅ Snapshot creation before destructive operations
- ✅ Detailed status reporting
- ✅ Clear rollback instructions
- ✅ Non-destructive approach (recordings preserved)
