# Simplifying the Frigate Health Checker: When Less is More

**Date:** 2026-01-25

## The Problem

My Frigate NVR stopped recording for over 4 hours, and the "sophisticated" health checker I built didn't catch it.

The health checker was monitoring:
- Coral TPU inference speed (< 100ms threshold)
- "Detection appears to be stuck" log patterns
- "Too many unprocessed recording segments" backlog warnings

All these checks passed. Inference was 21ms. No stuck detection. No backlog warnings. Yet recordings weren't being written.

## What Went Wrong

I over-engineered the health check. I was monitoring *symptoms* instead of *outcomes*.

The actual failure mode was simple: the recording pipeline silently stopped writing segments. The Coral TPU kept humming along at 21ms inference. The detection queue had no backlog. Everything looked healthy from a "system metrics" perspective.

But zero new recording files were being created.

## The Fix: Check What Actually Matters

I stripped the health checker down to two checks:

```python
def check_health(self) -> HealthCheckResult:
    # Check 1: Can we reach the API?
    stats = self._get_frigate_stats(pod_name)
    if stats is None:
        return UNHEALTHY, "API unresponsive"

    # Check 2: Are cameras getting frames?
    for camera, camera_stats in stats["cameras"].items():
        if camera in skip_cameras:  # doorbell on flaky WiFi
            continue
        if camera_stats["camera_fps"] < 1:
            return UNHEALTHY, f"No frames from {camera}"

    return HEALTHY
```

That's it. If `camera_fps >= 1` for each camera, Frigate is working. If frames are flowing, everything downstream (detection, recording, events) will work.

## Why the Old Checks Were Useless

**Inference speed**: A fast Coral TPU doesn't mean recordings are happening. The TPU could be processing frames that never get saved.

**Stuck detection logs**: These only appear when the detection *queue* backs up. If the problem is downstream (recording), detection happily keeps processing.

**Recording backlog**: Only triggers when segments pile up in the queue. If the recording pipeline is completely dead (not just slow), there's no backlog - there's nothing.

## The Skip List

One nuance: my Reolink doorbell is on 5GHz WiFi that drops out when the AT&T router gets flaky. I don't want the health checker restarting Frigate every time the doorbell loses connection.

```python
skip_cameras = ["reolink_doorbell"]
```

Cameras on unreliable networks get skipped. The health check focuses on cameras that *should* be working.

## Lessons Learned

1. **Monitor outcomes, not metrics.** "Are recordings being created?" beats "Is inference fast?"

2. **Simple checks catch more failures.** My complex log parsing missed a 4-hour outage. A simple FPS check would have caught it in 5 minutes.

3. **Skip what you can't control.** Don't let a flaky WiFi camera trigger false positives.

4. **The recording pipeline can fail silently.** Frigate's API shows `status: running` even when recordings stop. The only reliable indicator is whether frames are actually flowing.

## The Code

Health checker source: `apps/frigate-health-checker/`

Key files:
- `health_checker.py` - The simplified check logic
- `config.py` - `skip_cameras` setting
- `models.py` - `UnhealthyReason.NO_FRAMES` enum

CronJob runs every 5 minutes. Two consecutive failures trigger a restart. Circuit breaker prevents restart storms (max 2/hour).

## What I'd Do Differently

If I were starting over, I'd add one more check: recording segment age. Query the most recent segment timestamp and fail if it's older than 10 minutes. This catches the exact failure mode I hit.

But honestly? The FPS check probably covers 95% of failure modes. Keep it simple.

---

*Tags: frigate, nvr, kubernetes, health-check, monitoring, homelab, over-engineering*
