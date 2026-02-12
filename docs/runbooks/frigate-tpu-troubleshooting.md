# Runbook: Frigate Coral TPU Troubleshooting

## Symptoms

- Frigate UI shows "no frames" or stale images
- Cameras appear offline but RTSP streams work directly
- High CPU on Frigate pod
- Logs show repeated "Detection appears to be stuck"

## Quick Diagnosis

```bash
# Check TPU restarts in last 30 min
KUBECONFIG=~/kubeconfig kubectl logs -n frigate deploy/frigate --since=30m | \
  grep -c "detector.coral.*Starting detection process"
# Healthy: 0-1, Unhealthy: 2+

# Check for stuck detection
KUBECONFIG=~/kubeconfig kubectl logs -n frigate deploy/frigate --since=5m | \
  grep "Detection appears to be stuck"

# Check current inference speed
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deploy/frigate -- \
  curl -s localhost:5000/api/stats | jq '.detectors.coral.inference_speed'
# Healthy: <50ms, Warning: 50-100ms, Critical: >100ms
```

## Resolution Steps

### Level 1: Restart Frigate Pod

Usually clears transient TPU issues.

```bash
KUBECONFIG=~/kubeconfig kubectl rollout restart deployment/frigate -n frigate
KUBECONFIG=~/kubeconfig kubectl rollout status deployment/frigate -n frigate
```

Verify recovery:
```bash
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deploy/frigate -- \
  cat /dev/shm/logs/frigate/current | grep -E "TPU found|Starting detection"
```

### Level 2: Check USB on Host

If restarts don't help or problem recurs quickly.

```bash
# Check USB device visibility on Proxmox host
ssh root@still-fawn.maas 'lsusb | grep -i google'
# Should show: Global Unichip Corp. (Coral USB Accelerator)

# Check for USB errors
ssh root@still-fawn.maas 'dmesg | grep -i usb | tail -30'

# Check VM USB passthrough config
ssh root@still-fawn.maas 'qm config 108 | grep usb'
```

### Level 3: Physical Intervention

If USB errors present or device not visible.

1. **SSH to Proxmox host**: `ssh root@still-fawn.maas`
2. **Stop VM 108**: `qm stop 108`
3. **Physically unplug Coral USB** from host
4. **Wait 10 seconds**
5. **Replug Coral USB**
6. **Verify device**: `lsusb | grep -i google`
7. **Start VM**: `qm start 108`
8. **Wait for Frigate pod** to reschedule

### Level 4: Check Thermal/Power

Coral USB can become unstable under:
- High ambient temperature
- Insufficient USB power (use powered hub if on long cable)
- Sustained high inference load

```bash
# Check Coral temperature (if accessible)
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deploy/frigate -- \
  cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null || echo "Thermal not exposed"

# Check inference queue depth
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deploy/frigate -- \
  curl -s localhost:5000/api/stats | jq '.detectors.coral'
```

## Health Checker Auto-Remediation

The health checker (`frigate-health-checker` CronJob) runs every 5 minutes and will:

1. **Detect** TPU issues via multiple signals
2. **Wait** for 2 consecutive failures (10 min) to confirm
3. **Restart** Frigate automatically
4. **Rate limit** to max 3 restarts per hour
5. **Alert** via Alertmanager if circuit breaker triggers

### Check Health Checker State

```bash
# Current state
KUBECONFIG=~/kubeconfig kubectl get cm frigate-health-state -n frigate -o yaml

# Recent health check logs
KUBECONFIG=~/kubeconfig kubectl logs -n frigate -l app=frigate-health-checker --tail=50
```

### Manual State Reset

If health checker is stuck or you've manually fixed the issue:

```bash
KUBECONFIG=~/kubeconfig kubectl patch cm frigate-health-state -n frigate --type merge \
  -p '{"data":{"consecutive_failures":"0","last_restart_times":"","alert_sent_for_incident":"false"}}'
```

## When to Escalate

- TPU not visible in `lsusb` after physical replug
- USB errors persist in `dmesg`
- Problem recurs within minutes of restart (thermal/hardware failure)
- Multiple Coral devices failing simultaneously

## Related

- RCA: `docs/rca/2026-02-12-frigate-coral-tpu-instability.md`
- Coral setup guide: OpenMemory query "coral tpu frigate setup"
- Health checker: `gitops/clusters/homelab/apps/frigate/cronjob-health.yaml`

## Tags

frigate, coral, tpu, edgetpu, usb, troubleshooting, runbook, detection, health-check
