# Frigate Camera Addition Runbook

## Overview

This runbook documents the process for adding new cameras to Frigate NVR running on K3s, including lessons learned from the Reolink doorbell and Living Room camera incidents (2026-01-18).

## Prerequisites

- Access to `~/kubeconfig` for K3s cluster
- Camera IP address and credentials
- Camera on reachable subnet (192.168.1.x or 192.168.4.x)

## Pre-Flight Checks

### 1. Verify Network Connectivity

```bash
# From Mac
ping <CAMERA_IP>
nc -zv <CAMERA_IP> 554   # RTSP port
nc -zv <CAMERA_IP> 8000  # ONVIF port (if applicable)

# From Frigate pod
kubectl --kubeconfig ~/kubeconfig exec -n frigate deployment/frigate -- \
  python3 -c "import socket; socket.create_connection(('<CAMERA_IP>', 554), timeout=5); print('OK')"
```

### 2. Test RTSP Stream Locally

```bash
# Test credentials work (use timeout to avoid hanging)
timeout 15 ffprobe -v error -i "rtsp://USER:PASS@CAMERA_IP:554/h264Preview_01_sub" 2>&1
```

**Common RTSP paths by brand:**
- Reolink: `/h264Preview_01_sub` (sub-stream), `/h264Preview_01_main` (main)
- Trendnet: `/play1.sdp`
- Generic: `/stream1`, `/live/ch0`

### 3. Verify Credentials Have No Special Characters

**CRITICAL**: Passwords with `!` break go2rtc URL parsing.

| Character | Problem | Solution |
|-----------|---------|----------|
| `!` | go2rtc can't parse URL | Change password on camera |
| `@` | Conflicts with URL user:pass@host | URL-encode as `%40` |
| `:` | Conflicts with user:pass separator | URL-encode as `%3A` |
| `#` | Treated as URL fragment | URL-encode as `%23` |

**Safe password characters**: `A-Z a-z 0-9 - . _ ~`

## Adding the Camera

### Step 1: Backup Current Config

```bash
# ALWAYS backup before changes
kubectl --kubeconfig ~/kubeconfig exec -n frigate deployment/frigate -- \
  cat /config/config.yml > /tmp/frigate-config-backup-$(date +%Y%m%d-%H%M%S).yml
```

### Step 2: Edit Config Locally

**Never use `sed` on the pod config directly** - edit locally then upload.

```bash
# Get current config
kubectl --kubeconfig ~/kubeconfig exec -n frigate deployment/frigate -- \
  cat /config/config.yml > /tmp/frigate-config-new.yml

# Edit /tmp/frigate-config-new.yml with your editor
```

Add to `go2rtc.streams`:
```yaml
go2rtc:
  streams:
    # ... existing streams ...
    new_camera: "rtsp://{FRIGATE_CAM_NEWCAMERA_USER}:{FRIGATE_CAM_NEWCAMERA_PASS}@CAMERA_IP:554/h264Preview_01_sub"
```

Add to `cameras`:
```yaml
cameras:
  # ... existing cameras ...
  new_camera:
    enabled: true
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/new_camera
          roles:
            - detect
            - record
    detect:
      enabled: true
      width: 1920
      height: 1080
      fps: 5
    objects:
      track:
        - person
    motion:
      threshold: 25
      contour_area: 50
    record:
      enabled: true
      retain:
        days: 7
        mode: motion
```

For Reolink cameras with ONVIF (uses camera's built-in AI):
```yaml
    onvif:
      host: <CAMERA_IP>
      port: 8000
      user: admin          # ONVIF doesn't support env var substitution
      password: YourPass   # Must be hardcoded (not placeholder)
```

### Step 3: Add Credentials to K8s Secret

```bash
kubectl --kubeconfig ~/kubeconfig patch secret frigate-credentials -n frigate --type='json' -p='[
  {"op": "add", "path": "/data/FRIGATE_CAM_NEWCAMERA_USER", "value": "'$(echo -n 'admin' | base64)'"},
  {"op": "add", "path": "/data/FRIGATE_CAM_NEWCAMERA_PASS", "value": "'$(echo -n 'YourPassword' | base64)'"}
]'
```

### Step 4: Upload Config and Restart

```bash
# Upload new config
cat /tmp/frigate-config-new.yml | kubectl --kubeconfig ~/kubeconfig exec -i -n frigate deployment/frigate -- \
  tee /config/config.yml > /dev/null

# Restart pod to pick up new secret
kubectl --kubeconfig ~/kubeconfig delete pod -n frigate -l app=frigate
```

### Step 5: Verify Camera Works

```bash
# Wait for pod to start
sleep 40

# Check for errors
kubectl --kubeconfig ~/kubeconfig logs -n frigate deployment/frigate --tail=50 2>&1 | grep -iE "new_camera|error"

# Check camera is streaming (should return 200)
kubectl --kubeconfig ~/kubeconfig logs -n frigate deployment/frigate --tail=50 2>&1 | grep "new_camera.*200"
```

### Step 6: Store Credentials in .env

```bash
cat >> proxmox/homelab/.env << 'EOF'
FRIGATE_CAM_NEWCAMERA_USER=admin
FRIGATE_CAM_NEWCAMERA_PASS=YourPassword
EOF
```

## Troubleshooting

### "no such host" Error

**Cause**: DNS name not resolvable from K3s cluster.

**Fix**: Use IP address instead of hostname. K3s pods use MAAS DNS which doesn't know `.homelab` domains.

```yaml
# Bad
reolink_doorbell: "rtsp://...@reolink-vdb.homelab:554/..."

# Good
reolink_doorbell: "rtsp://...@192.168.1.10:554/..."
```

### "wrong user/pass" Error

**Causes**:
1. Camera locked out from failed attempts
2. Password has special character (`!`) breaking URL parsing
3. Wrong username (e.g., `frigate` vs `admin`)

**Fix**:
1. Check camera admin UI for lockout, unlock if needed
2. Change password to remove special characters
3. Test locally: `ffprobe "rtsp://user:pass@ip:554/path"`

### "invalid userinfo" Error

**Cause**: Password contains `!` which breaks go2rtc URL parsing even when URL-encoded.

**Fix**: Change password on the camera to use only safe characters.

### "Connection refused" / Timeout

**Causes**:
1. Camera on different subnet (not routable)
2. Camera rebooting after IP change
3. RTSP not enabled on camera

**Fix**:
1. Check camera IP is on 192.168.1.x or 192.168.4.x
2. Wait and retry
3. Enable RTSP in camera settings

### ONVIF Not Working

**Cause**: ONVIF config doesn't support `{ENV_VAR}` placeholders.

**Fix**: Hardcode username/password in ONVIF section:
```yaml
onvif:
  host: 192.168.1.10
  port: 8000
  user: admin           # Hardcoded, not {PLACEHOLDER}
  password: YourPass    # Hardcoded, not {PLACEHOLDER}
```

### Init Container Doesn't Update Config

**Cause**: Init container only copies config if `/config/config.yml` doesn't exist.

**Fix**: For GitOps configmap changes to take effect:
```bash
kubectl --kubeconfig ~/kubeconfig exec -n frigate deployment/frigate -- rm /config/config.yml
kubectl --kubeconfig ~/kubeconfig rollout restart deployment/frigate -n frigate
```

## RCA: Reolink Doorbell Incident (2026-01-18)

### Timeline

1. User reported Frigate errors processing Reolink doorbell
2. Initial error: `lookup reolink-vdb.homelab: no such host`
3. Changed to FQDN `reolink-vdb.home.panderosystems.com` - still failed with auth errors
4. Changed to IP `192.168.1.10` - got `wrong user/pass`
5. Discovered password contained `!` which breaks go2rtc URL parsing
6. User changed password on camera to remove special character
7. Camera locked out from failed auth attempts
8. User unlocked camera
9. Changed config to use IP instead of FQDN
10. Camera working

### Root Causes

1. **DNS**: K3s pods use MAAS DNS (192.168.4.53) which doesn't know `.homelab` domain. OPNsense Unbound has the records but isn't in the DNS chain.

2. **Special Characters**: go2rtc cannot handle `!` in passwords, even when URL-encoded as `%21`. The URL parser rejects it.

3. **Lockout**: Multiple failed auth attempts during debugging locked out the camera.

### Lessons Learned

1. **Use IPs for cameras** - DNS adds complexity without benefit
2. **Avoid special characters in passwords** - stick to alphanumeric
3. **Test locally first** - `ffprobe` before touching Frigate config
4. **Always backup** - `kubectl exec cat > /tmp/backup` before changes
5. **Edit locally, upload** - never `sed` directly on pod config

## Credentials Reference

All stored in `proxmox/homelab/.env` (gitignored):

| Camera | IP | User | Password |
|--------|-----|------|----------|
| MJPEG cam | 192.168.1.220 | admin | See .env |
| Trendnet | 192.168.1.107 | admin | See .env |
| Reolink doorbell | 192.168.1.10 | frigate | See .env |
| Living room | 192.168.1.140 | admin | See .env |

MQTT: See `proxmox/homelab/.env` for credentials
