# Frigate K8s Migration Checklist

Quick reference checklist for migrating from still-fawn Frigate LXC to K8s Frigate.

## Pre-Migration (Do These First)

- [ ] K8s Frigate pod is running and healthy
- [ ] Coral USB TPU is accessible from K8s pod
- [ ] All cameras are configured in K8s Frigate ConfigMap
- [ ] Face recognition is enabled (Frigate 0.16.0+)
- [ ] MQTT client_id is set to "frigate-k8s" (prevents HA conflicts)
- [ ] LoadBalancer IP is assigned (should be 192.168.4.83)
- [ ] DNS entry exists: frigate.homelab → 192.168.4.83
- [ ] Recording storage is configured and mounted

## Verification Steps

### 1. Run Verification Script

```bash
cd /Users/10381054/code/home/scripts/frigate
./verify-frigate-k8s.sh
```

**Expected output**: All checks should pass (exit code 0)

### 2. Manual Testing

- [ ] Open Frigate web UI: http://192.168.4.83:5000
- [ ] Verify all 3 cameras show live feeds:
  - old_ip_camera
  - trendnet_ip_572w
  - reolink_doorbell
- [ ] Check Coral TPU is working (System → Stats → Detectors)
- [ ] Verify face recognition is enabled (Config)
- [ ] Test recording playback
- [ ] Verify MQTT messages are publishing (check HA MQTT topics)

## Migration Day

### 3. Update Home Assistant (Optional - Can Do After)

Update Frigate integration before shutdown to minimize downtime:

1. Go to Settings → Devices & Services → Frigate
2. Click Configure
3. Change URL from:
   - Old: `http://<still-fawn-ip>:5000`
   - New: `http://192.168.4.83:5000` or `http://frigate.homelab:5000`
4. Save and restart HA

**Note**: You can also do this after shutdown if you prefer.

### 4. Shutdown still-fawn Frigate

```bash
cd /Users/10381054/code/home/scripts/frigate
./shutdown-still-fawn-frigate.sh
```

**What this does**:
- Runs verification again (safety check)
- Asks for confirmation
- Creates snapshot: `pre-k8s-migration-YYYYMMDD-HHMMSS`
- Stops LXC 110
- Disables auto-start

### 5. Post-Shutdown Verification

- [ ] K8s Frigate is still responding: http://192.168.4.83:5000
- [ ] Home Assistant Frigate integration shows "Available"
- [ ] Camera automations still work
- [ ] Recordings are being created in K8s Frigate
- [ ] Face recognition events are detected
- [ ] MQTT messages are still publishing

## Rollback (If Needed)

If anything goes wrong:

```bash
cd /Users/10381054/code/home/scripts/frigate
./rollback-to-still-fawn.sh
```

Then update HA back to still-fawn URL.

## Post-Migration (Optional)

### Coral USB TPU

The Coral is currently still physically attached to still-fawn.maas:

- [ ] **Option 1**: Leave it on still-fawn and use USB/IP for K8s access
- [ ] **Option 2**: Move it to pumped-piglet (requires USB cable re-routing)
- [ ] **Option 3**: Already using USB/IP (verify this is working)

### Recording Import

116GB of recordings remain on still-fawn (local-3TB-backup):

- [ ] Decide if you want to import old recordings to K8s Frigate
- [ ] If yes, mount still-fawn storage in K8s pod
- [ ] Copy recordings: `/var/lib/frigate/recordings` → K8s volume
- [ ] Restart Frigate to index imported recordings

### Cleanup (After Confirmation Everything Works)

After 1-2 weeks of successful K8s operation:

- [ ] Delete old snapshots from still-fawn: `pct delsnapshot 110 <name>`
- [ ] Optionally delete LXC 110 container: `pct destroy 110`
- [ ] Optionally archive/delete old recordings on still-fawn

**Warning**: Don't rush cleanup - keep rollback option available for at least 2 weeks.

## Troubleshooting Guide

### K8s Frigate Not Responding

```bash
# Check pod status
kubectl get pods -n frigate -l app=frigate

# Check pod logs
kubectl logs -n frigate -l app=frigate

# Check events
kubectl describe pod -n frigate -l app=frigate
```

### Cameras Not Streaming

```bash
# Check Frigate logs for camera errors
kubectl logs -n frigate -l app=frigate | grep -i "camera\|error"

# Verify camera URLs in ConfigMap
kubectl get configmap frigate-config -n frigate -o yaml
```

### Coral TPU Not Detected

```bash
# Check USB devices in pod
kubectl exec -n frigate -l app=frigate -- ls -l /dev/bus/usb/

# Check Frigate detector logs
kubectl logs -n frigate -l app=frigate | grep -i coral
```

### MQTT Conflicts (Duplicate Messages)

If you see duplicate MQTT messages, check:
- Both Frigates might be running simultaneously
- Verify still-fawn is stopped: `ssh root@still-fawn.maas 'pct status 110'`
- Check MQTT client_id is different between instances

### Face Recognition Not Working

Requires Frigate 0.16.0+:
```bash
# Check Frigate version
curl -s http://192.168.4.83:5000/api/version

# Check face recognition config
curl -s http://192.168.4.83:5000/api/config | jq '.face_recognition'
```

## Support

For issues:
1. Check script output for specific error messages
2. Review troubleshooting guide above
3. Check Frigate logs: `kubectl logs -n frigate -l app=frigate`
4. Verify all pre-migration checklist items
5. If stuck, rollback and debug before trying again

## Quick Reference

| Component | Old (LXC) | New (K8s) |
|-----------|-----------|-----------|
| Host | still-fawn.maas | pumped-piglet |
| Container | LXC 110 | K8s pod |
| URL | http://<still-fawn-ip>:5000 | http://192.168.4.83:5000 |
| MQTT client_id | frigate | frigate-k8s |
| Storage | local-3TB-backup (116GB) | K8s PV |
| Coral TPU | USB passthrough | USB/IP or direct |
| Version | 0.14.x | 0.16.0+ |
| Face Recognition | No | Yes |
