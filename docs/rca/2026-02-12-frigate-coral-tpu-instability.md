# RCA: Frigate Coral TPU Instability - 2026-02-12

## Incident Summary

| Field | Value |
|-------|-------|
| Date | 2026-02-12 |
| Duration | ~6+ hours (TPU unstable), user-reported downtime ~10 min |
| Impact | Frigate showing "no frames" for cameras |
| Root Cause | Coral USB TPU repeatedly crashing and restarting |
| Resolution | Manual pod restart + health checker improvements |

## Timeline (UTC)

| Time | Event |
|------|-------|
| ~01:00 | First detector restart logged |
| 01:00-07:09 | TPU restarted 18 times (~every 10-30 min) |
| 07:09 | User reported "no frames" in Frigate UI |
| 07:11 | Manual `kubectl rollout restart deployment/frigate` |
| 07:11 | Frigate recovered, TPU found |
| 07:15 | Health checker updated with TPU restart detection |

## Root Cause Analysis

### What Happened

The Coral USB TPU entered an unstable state where:
1. Detection process would start normally ("TPU found")
2. After 10-30 minutes, detection would hang
3. Frigate watchdog detected stuck detection: `Detection appears to be stuck. Restarting detection process...`
4. Detector process killed and restarted
5. Cycle repeated 18 times

### Why It Wasn't Auto-Remediated

The existing health checker had these checks:
- API responsiveness
- Coral inference speed (was fine between crashes)
- "Detection stuck" count in 5 min (threshold: 2)
- Recording backlog count

**Gap**: The TPU was restarting every 10-30 minutes, so there was typically only 0-1 "stuck" events per 5-minute window. The pattern was visible only when looking at a longer time window (30+ minutes).

### Why User Saw "No Frames"

When detection is stuck:
1. Frigate continues receiving camera streams
2. Detection queue backs up
3. Recording segments accumulate in cache
4. UI shows stale/no frames while waiting for detection

## Corrective Actions

### Immediate (Completed)

1. **Manual restart** - Cleared TPU state
2. **Added TPU restart detection** - New health check counts `detector.coral.*Starting detection process` over 30-minute window
3. **Increased max auto-restarts** - From 2 to 3 per hour
4. **Added Alertmanager integration** - Circuit breaker now sends critical alert to Grafana

### Health Checker Improvements

| Check | Window | Threshold | Status |
|-------|--------|-----------|--------|
| API responsiveness | instant | 10s timeout | Existing |
| Coral inference speed | instant | >100ms | Existing |
| Detection stuck | 5 min | >2 events | Existing |
| Recording backlog | 5 min | >5 events | Existing |
| **TPU restarts** | **30 min** | **>2 restarts** | **NEW** |

### Future Considerations

1. **USB power management** - Coral USB devices can become unstable if USB power saving is enabled on host
2. **Physical inspection** - If recurring, check USB cable and port
3. **Thermal monitoring** - Coral TPU can throttle/crash under thermal stress

## Affected Systems

- Frigate NVR (K8s deployment in `frigate` namespace)
- Coral USB Accelerator (passed through to K3s VM 108 on still-fawn)
- All cameras (detection disabled during instability)

## Lessons Learned

1. **Look at longer time windows** - 5-minute windows miss slow-burn instability patterns
2. **Count process restarts** - A healthy system shouldn't restart critical processes repeatedly
3. **Inference speed isn't enough** - TPU can report good inference speed right after restart, then hang

## References

- Health checker: `gitops/clusters/homelab/apps/frigate/cronjob-health.yaml`
- Runbook: `docs/runbooks/frigate-tpu-troubleshooting.md`
- Previous incident (vzdump crash): `docs/rca/2026-02-04-frigate-vzdump-crash.md` (OpenMemory)

## Tags

frigate, coral, tpu, edgetpu, usb, detection, health-check, watchdog, k8s, kubernetes
