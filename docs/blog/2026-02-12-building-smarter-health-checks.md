# Building Smarter Health Checks: Lessons from a Coral TPU Outage

*2026-02-12*

This morning I noticed my Frigate NVR showing "no frames" across all cameras. The fix was simple - restart the pod - but the incident exposed a gap in my health monitoring. Here's what I learned about building health checks that catch slow-burn failures.

## The Symptom

Frigate's UI showed no camera feeds. But digging into the logs revealed something interesting:

```
[07:09:50] frigate.record.maintainer WARNING : Too many unprocessed recording segments in cache for reolink_doorbell...
```

The cameras were streaming fine. The problem was detection - the Coral TPU that processes frames for object detection was stuck.

## The Pattern I Missed

Looking at the logs over the past 6 hours:

```bash
$ kubectl logs deploy/frigate --since=6h | grep "Starting detection process" | wc -l
18
```

The TPU had restarted **18 times**. Every 10-30 minutes, it would hang, get killed by the watchdog, and restart. Each restart looked healthy - "TPU found", good inference speed - until it hung again.

## Why My Health Check Failed

My existing health checker ran every 5 minutes and checked:
- API responsiveness
- Coral inference speed (threshold: 100ms)
- "Detection stuck" events in last 5 min (threshold: 2)
- Recording backlog events in last 5 min (threshold: 5)

The problem? The TPU was restarting every 10-30 minutes. In any given 5-minute window, there was typically 0-1 "stuck" events. The checker saw intermittent blips, not a pattern.

## The Fix: Longer Time Windows

I added a new check that looks at a **30-minute window**:

```bash
TPU_RESTART_CT=$(kubectl logs "$POD" --since=30m | \
  grep -c "detector.coral.*Starting detection process")

if [[ "$TPU_RESTART_CT" -gt 2 ]]; then
  UNHEALTHY=true
  REASON="Coral TPU unstable - ${TPU_RESTART_CT} detector restarts in 30 min"
fi
```

A healthy system should have 0-1 detector starts in 30 minutes (initial start, maybe one restart). More than 2 means something is wrong.

## The Broader Lesson

Different failure modes require different observation windows:

| Failure Type | Window | Example |
|--------------|--------|---------|
| Hard down | Instant | API timeout |
| Performance degradation | 1-5 min | Slow inference |
| Flapping/instability | 15-60 min | Repeated restarts |
| Resource exhaustion | Hours-days | Disk filling, memory leak |

My original checks were good at catching immediate failures but blind to the "death by a thousand cuts" pattern.

## Circuit Breakers and Alerts

I also improved the remediation logic:

1. **Consecutive failures required**: 2 (prevents restart on transient blip)
2. **Max restarts per hour**: 3 (prevents restart loops)
3. **Circuit breaker alert**: When max restarts exhausted, push alert to Alertmanager

```bash
if [[ $RECENT_RESTARTS -ge $MAX_RESTARTS_PER_HOUR ]]; then
  # Push alert to Alertmanager
  curl -X POST -d "$ALERT_JSON" \
    "http://alertmanager.monitoring:9093/api/v2/alerts"
fi
```

This way, auto-remediation handles most issues, but I get paged when it's something that needs human attention.

## Takeaways

1. **Match observation window to failure mode** - Fast checks catch fast failures; slow-burn problems need longer windows
2. **Count process restarts** - A process that keeps restarting isn't healthy, even if each restart succeeds
3. **Inference speed isn't enough** - The TPU reported good speed right after restart, then hung. Need to look at stability over time
4. **Circuit breakers prevent runaway** - Auto-remediation is great until it isn't. Cap retries and escalate

The Coral TPU is inherently a bit temperamental - it's a USB device that can become unstable under thermal stress or USB power issues. But with smarter health checks, at least I'll know about it before my cameras go blind.

---

*Code: [gitops/clusters/homelab/apps/frigate/cronjob-health.yaml](https://github.com/homeiac/home)*
