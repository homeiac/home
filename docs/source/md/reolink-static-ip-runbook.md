# Reolink Doorbell Static IP Configuration Runbook

## Overview

This runbook documents the process of migrating a Reolink Video Doorbell from DHCP to a static IP with DNS, and updating all dependent services.

## Why Static IP?

- DHCP lease changes break Frigate RTSP streams
- Home Assistant Reolink integration loses connection on IP change
- DNS names provide abstraction - change IP in one place (OPNsense) instead of multiple configs

## Prerequisites

- Access to OPNsense admin UI
- Access to Reolink app (mobile) or web UI
- kubectl access to K8s cluster
- SSH access to Proxmox hosts

## Network Architecture

```
┌──────────────────┐          RTSP (554)           ┌──────────────────────────┐
│   Reolink        │ ────────────────────────────► │  Frigate (K8s)           │
│   Doorbell       │                               │  on still-fawn           │
│reolink-vdb.homelab│  via go2rtc proxy            │  (192.168.4.x network)   │
│   192.168.1.10   │   127.0.0.1:8554              │                          │
└────────┬─────────┘                               └────────────┬─────────────┘
         │                                                      │
         │  HTTPS API (443)                                     │ Frigate API
         │                                                      │ (5000)
         ▼                                                      ▼
┌──────────────────┐                               ┌──────────────────────────┐
│   Home Assistant │◄──────────────────────────────│  HA Frigate Integration  │
│   192.168.4.240  │   Events, snapshots           │  frigate.homelab         │
│   (HAOS VM 116)  │                               │                          │
└────────┬─────────┘                               └──────────────────────────┘
         │
         │  Reolink Integration (native)
         │  - Doorbell press events
         │  - Motion detection
         │  - Two-way audio
         ▼
┌──────────────────┐
│   Automations    │
│   - Notifications│
│   - Package det. │
└──────────────────┘
```

## Consumers That Need Updating

| Consumer | Protocol | Port | Config Location |
|----------|----------|------|-----------------|
| Frigate (K8s) | RTSP | 554 | `/config/config.yml` in PVC |
| Home Assistant | HTTPS | 443 | Reolink integration (UI) |
| Reolink App | Cloud + local | various | Auto-discovers |

## Step-by-Step Migration

### Step 1: Add DNS Entry in OPNsense

1. Go to **Services → Unbound DNS → Overrides**
2. Click **+ Add** under Host Overrides
3. Enter:
   - **Host**: `reolink-vdb`
   - **Domain**: `homelab`
   - **Type**: `A`
   - **IP**: `192.168.1.10`
   - **Description**: `Reolink Video Doorbell WiFi`
4. Click **Save**
5. Click **Apply Changes**

### Step 2: Verify DNS Resolution

Test from all three locations that will use the DNS name:

```bash
# From Mac
dig reolink-vdb.homelab @192.168.4.1

# From Frigate pod
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- getent hosts reolink-vdb.homelab

# From Home Assistant
ssh root@chief-horse.maas "qm guest exec 116 -- nslookup reolink-vdb.homelab"
```

Expected output: `192.168.1.10`

### Step 3: Configure Static IP on Reolink Doorbell

Via **Reolink App** on your phone:

1. Open Reolink app
2. Tap on the doorbell device
3. Go to **Settings** (gear icon) → **Network** → **Network Information**
4. Change from **DHCP** to **Static**
5. Enter:
   - **IP Address**: `192.168.1.10`
   - **Subnet Mask**: `255.255.255.0`
   - **Gateway**: `192.168.1.254` (AT&T modem)
   - **DNS**: `8.8.8.8`
6. Save

The doorbell will reboot (~30 seconds).

### Step 4: Verify Doorbell Connectivity

```bash
ping -c 3 192.168.1.10
```

### Step 5: Update Frigate Configuration

**Important**: Frigate reads config from a PVC, not from the ConfigMap in git. You must update both.

#### Update config inside the pod:

```bash
# Update the config file
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- \
  sed -i 's|192.168.1.160|reolink-vdb.homelab|g' /config/config.yml

# Verify the change
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- \
  grep -A1 "reolink_doorbell:" /config/config.yml | head -4

# Restart Frigate to pick up the change
KUBECONFIG=~/kubeconfig kubectl delete pod -n frigate -l app=frigate
```

#### Update ConfigMap in git (for record-keeping):

Edit `gitops/clusters/homelab/apps/frigate/configmap.yaml`:

```yaml
go2rtc:
  streams:
    reolink_doorbell: "rtsp://{FRIGATE_CAM_REOLINK_USER}:{FRIGATE_CAM_REOLINK_PASS}@reolink-vdb.homelab:554/h264Preview_01_sub"
```

Commit and push:

```bash
git add gitops/clusters/homelab/apps/frigate/configmap.yaml
git commit -m "fix(frigate): use DNS name for Reolink doorbell"
git push
```

### Step 6: Verify Frigate Stream

```bash
# Check for errors
KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate --tail=30 | grep -i "reolink\|error"

# Should see:
# INFO: Camera processor started for reolink_doorbell
# INFO: Capture process started for reolink_doorbell
# (no errors about timeout or connection refused)
```

### Step 7: Reconfigure Home Assistant Reolink Integration

1. Go to **Settings → Devices & Services**
2. Find **Reolink** integration
3. Click the **3-dot menu (⋮)** on the hub
4. Select **Reconfigure**
5. Enter new host: `reolink-vdb.homelab`
6. Submit and wait for "Initializing" to complete

### Step 8: Verify HA Integration

```bash
# Check integration status
~/code/home/scripts/haos/list-integrations.sh | grep -i reolink

# Check an entity
~/code/home/scripts/haos/get-entity-state.sh binary_sensor.reolink_video_doorbell_wifi_visitor
```

## Troubleshooting

### DNS not resolving from Frigate pod

Check CoreDNS is forwarding to OPNsense:

```bash
KUBECONFIG=~/kubeconfig kubectl get configmap -n kube-system coredns -o yaml
```

Ensure it forwards `.homelab` queries to `192.168.4.1`.

### Frigate still using old IP after restart

The config is persisted in a PVC. Verify the change was saved:

```bash
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- cat /config/config.yml | grep reolink
```

### HA Reolink integration stuck in "Initializing"

1. Check HA can reach the doorbell:
   ```bash
   ssh root@chief-horse.maas "qm guest exec 116 -- ping -c 3 192.168.1.10"
   ```

2. Check HA logs:
   ```bash
   ~/code/home/scripts/haos/get-logs.sh core 100 | grep -i reolink
   ```

### Doorbell not responding after static IP change

1. Check if it reverted to DHCP - scan the network:
   ```bash
   nmap -sn 192.168.1.0/24 | grep -i reolink
   ```

2. Factory reset via physical button if needed, then reconfigure.

## Rollback

If issues persist, revert to DHCP:

1. In Reolink app: Settings → Network → Enable DHCP
2. Find new IP via router or nmap
3. Update Frigate config with new IP
4. Reconfigure HA integration with new IP

## Configuration Summary

| Item | Value |
|------|-------|
| DNS Name | `reolink-vdb.homelab` |
| Static IP | `192.168.1.10` |
| Gateway | `192.168.1.254` |
| Subnet | `255.255.255.0` |
| DNS Server | `8.8.8.8` |

## Related Documents

- [Network Architecture](../architecture/reolink-doorbell-network.md)
- Frigate ConfigMap: `gitops/clusters/homelab/apps/frigate/configmap.yaml`
- Voice PE Static IP (similar pattern): `scripts/voice-pe/configs/home-assistant-voice-09f5a3.yaml`

## Tags

reolink, doorbell, static-ip, dns, frigate, home-assistant, opnsense, network, rtsp, go2rtc
