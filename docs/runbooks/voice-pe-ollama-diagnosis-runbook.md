# Runbook: Voice PE / Ollama Diagnosis and Recovery

**Last Updated**: 2026-01-01
**Owner**: Homelab
**Related RCA**: [RCA-Voice-PE-Ollama-Outage-2026-01-01](../rca/RCA-Voice-PE-Ollama-Outage-2026-01-01.md)

## Overview

This runbook covers diagnosis and recovery procedures when the Voice PE device is not responding or showing abnormal LED states.

## Voice PE LED States

| LED Color | Meaning | Likely Cause |
|-----------|---------|--------------|
| Off/Dim | Idle, listening for wake word | Normal |
| Blue (pulsing) | Listening/Processing | Normal during interaction |
| Blue (stuck) | Waiting for response | Backend (Ollama/HA) issue |
| Green | Speaking response | Normal |
| Red | Error/Muted | Check mute switch |
| Yellow | Booting/Updating | Wait or check WiFi |

## Quick Diagnosis Checklist

```bash
# 1. Check Ollama conversation agent status in HA
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://192.168.4.240:8123/api/states/conversation.ollama_conversation" | jq '{state}'

# Expected: timestamp like "2025-12-20T00:50:08.025472+00:00"
# Problem: "unavailable"

# 2. Check Voice PE assist satellite status
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://192.168.4.240:8123/api/states/assist_satellite.home_assistant_voice_09f5a3_assist_satellite" | jq '{state}'

# Expected: "idle" or "listening" or "responding"

# 3. Quick reset - send an announce to cycle the state
curl -s -X POST \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "assist_satellite.home_assistant_voice_09f5a3_assist_satellite", "message": "Test"}' \
  "http://192.168.4.240:8123/api/services/assist_satellite/announce"
```

## Diagnosis Flow

```
Voice PE Stuck Blue?
        │
        ▼
Check HA Ollama Status ──────────────────────────────────────┐
        │                                                     │
        ▼                                                     │
   "unavailable"?                                             │
        │ YES                                                 │
        ▼                                                     │
Check Ollama Pod ─────────────────────────────────────────┐  │
        │                                                  │  │
        ▼                                                  │  │
   Pod Running?                                            │  │
        │ NO                                               │  │
        ▼                                                  │  │
Check k3s GPU Node ────────────────────────────────────┐  │  │
        │                                               │  │  │
        ▼                                               │  │  │
   Node Ready?                                          │  │  │
        │ NO                                            │  │  │
        ▼                                               │  │  │
Check VM 105 ───────────────────────────────────────┐  │  │  │
        │                                            │  │  │  │
        ▼                                            │  │  │  │
Check Proxmox/ZFS ──────────────────────────────────┼──┼──┼──┤
                                                    │  │  │  │
                                                    ▼  ▼  ▼  ▼
                                              See specific section below
```

## Section 1: Check HA Ollama Integration

```bash
# Set HA token
export HA_TOKEN="your-long-lived-access-token"

# Check integration state
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://192.168.4.240:8123/api/config/config_entries/entry" | \
  jq '.[] | select(.domain == "ollama") | {title, state}'

# If state is "setup_error":
# 1. Go to HA Settings → Devices & Services → Ollama
# 2. Click 3 dots → Reload
# 3. If still failing, reconfigure with IP: http://192.168.4.85
```

## Section 2: Check Ollama Pod

```bash
# From a k3s node (via Proxmox guest exec)
ssh root@192.168.4.122 "qm guest exec 107 -- kubectl get pods -n ollama -o wide"

# Expected output:
# ollama-gpu-xxx   1/1   Running   ...   k3s-vm-pumped-piglet-gpu

# If Pending:
ssh root@192.168.4.122 "qm guest exec 107 -- kubectl describe pod -n ollama ollama-gpu-xxx"
# Look for: node selector issues, resource constraints, taints

# If no pod exists:
ssh root@192.168.4.122 "qm guest exec 107 -- kubectl get deploy -n ollama"
# Check if deployment exists and desired replicas > 0
```

## Section 3: Check k3s GPU Node

```bash
# Check all nodes
ssh root@192.168.4.122 "qm guest exec 107 -- kubectl get nodes"

# Expected: All nodes Ready
# NAME                       STATUS   ROLES                       AGE    VERSION
# k3s-vm-pumped-piglet-gpu   Ready    control-plane,etcd,master   71d    v1.33.6+k3s1
# k3s-vm-pve                 Ready    control-plane,etcd,master   231d   v1.33.6+k3s1
# k3s-vm-still-fawn          Ready    control-plane,etcd,master   49d    v1.33.6+k3s1

# If GPU node is NotReady:
ssh root@192.168.4.122 "qm guest exec 107 -- kubectl describe node k3s-vm-pumped-piglet-gpu"
# Look for: Conditions, Taints, Events
```

## Section 4: Check VM 105 (GPU Node VM)

```bash
# SSH to pumped-piglet Proxmox host
ssh root@192.168.4.175

# Check VM status
qm list
# VMID NAME                 STATUS
# 105  k3s-vm-pumped-piglet running

# If stopped, start it:
qm start 105

# If running but k3s NotReady, check inside VM:
qm guest exec 105 -- systemctl status k3s --no-pager

# If guest exec times out, VM may be hung - see Section 5
```

## Section 5: Check Proxmox/ZFS Health

```bash
ssh root@192.168.4.175

# Check ZFS pool health
zpool status -x

# CRITICAL: If any pool shows SUSPENDED:
# This blocks ALL I/O and requires physical intervention

# Check which disks:
lsblk -o NAME,SIZE,MODEL,TRAN | grep usb

# If USB disk is faulted:
# 1. Identify the faulty drive (see drive table below)
# 2. UNPLUG the faulty USB drive
# 3. Power cycle the host (hold power button or pull plug)
# 4. After reboot, remove disk references from VM:
#    qm set 105 --delete scsi1  # (if 20TB disk)
# 5. Start VM: qm start 105
```

### USB Drive Identification (pumped-piglet)

| Size | Model | ZFS Pool | Action |
|------|-------|----------|--------|
| 2.3TB | WD WD25EZRS | ? | Keep |
| 2.7TB | WD WD30EZRX | local-3TB-backup | Keep |
| 21.8TB | Seagate Expansion HDD | local-20TB-zfs | Safe to unplug if faulted |

**Seagate Logo**: Horizontal oval/disc shape, usually green or white text on black enclosure. It's the largest/heaviest drive.

## Section 6: Recovery Procedures

### Quick Reset Voice PE (No Backend Issue)

```bash
# Cycle the satellite state via announce
curl -s -X POST \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "assist_satellite.home_assistant_voice_09f5a3_assist_satellite", "message": "System reset"}' \
  "http://192.168.4.240:8123/api/services/assist_satellite/announce"

# Or manually set LED to off then let it recover
curl -s -X POST \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "light.home_assistant_voice_09f5a3_led_ring"}' \
  "http://192.168.4.240:8123/api/services/light/turn_off"
```

### Restart Ollama Pod

```bash
ssh root@192.168.4.122 "qm guest exec 107 -- kubectl rollout restart deployment/ollama-gpu -n ollama"
```

### Restart k3s on GPU Node

```bash
ssh root@192.168.4.175 "qm guest exec 105 -- systemctl restart k3s"
```

### Full GPU Node Recovery (VM Hung)

```bash
ssh root@192.168.4.175

# 1. Stop VM (may take time if I/O blocked)
qm stop 105 --skiplock

# 2. If stop hangs, force kill
pkill -9 -f 'qemu.*105'
rm -f /var/lock/qemu-server/lock-105.conf

# 3. If ZFS pool suspended, unplug USB drive and power cycle host

# 4. After host is back, remove problematic disks if needed
qm set 105 --delete scsi1      # 20TB data disk
qm set 105 --delete virtiofs0  # virtiofs share

# 5. Start VM
qm start 105
```

### Reconfigure HA Ollama Integration

If DNS issues prevent HA from reaching Ollama:

1. Go to **Settings → Devices & Services → Ollama**
2. Click **3 dots → Delete**
3. Click **Add Integration → Ollama**
4. Use direct IP: `http://192.168.4.85` (check with `kubectl get svc -n ollama`)

## Key IPs and Hosts

| Component | IP/Host | Notes |
|-----------|---------|-------|
| Home Assistant | 192.168.4.240 | HAOS on chief-horse |
| Ollama LoadBalancer | 192.168.4.85 | MetalLB IP (may change) |
| Traefik Ingress | 192.168.4.80 | For *.app.homelab |
| pumped-piglet (Proxmox) | 192.168.4.175 | Hosts GPU VM |
| k3s-vm-pumped-piglet-gpu | 192.168.4.210 | GPU node (VM 105) |
| k3s-vm-pve | 192.168.4.238 | Control plane (VM 107) |
| pve.maas (Proxmox) | 192.168.4.122 | Hosts k3s-vm-pve |

## Monitoring Gaps to Address

- [ ] ZFS pool health alerts (DEGRADED, SUSPENDED states)
- [ ] k3s node health alerts
- [ ] HA integration health checks
- [ ] USB device connect/disconnect alerts

**Tags**: voice-pe, ollama, runbook, diagnosis, troubleshooting, k3s, proxmox, zfs, pumped-piglet, home-assistant, gpu

