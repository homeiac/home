# RCA: Frigate Camera Degradation Not Detected by Health Checker

**Incident Date**: 2026-02-13
**Duration**: Unknown (user reported "flaky again")
**Impact**: trendnet_ip_572w camera degraded, skipping all frames, repeated ffmpeg crashes
**Detection**: User-reported (not detected by automated health checker)

---

## Incident Summary

The trendnet_ip_572w camera experienced repeated ffmpeg crashes with "Connection reset by peer" errors. The camera's detect stream was skipping 100% of frames (`skipped_fps: 5.0` = `camera_fps: 5.0`), causing recording segment backlog warnings. Despite this degradation, the health checker reported the system as healthy.

**Key Evidence from Logs:**
```
WARNING: Too many unprocessed recording segments in cache for trendnet_ip_572w
ERROR: trendnet_ip_572w: Unable to read frames from ffmpeg process
ERROR: Ffmpeg process crashed unexpectedly for trendnet_ip_572w
ERROR: [in#0/rtsp @ ...] Error during demuxing: Connection reset by peer
INFO: Restarting ffmpeg...
```

**Stats at time of incident:**
```json
{
  "trendnet_ip_572w": {
    "camera_fps": 5.0,
    "process_fps": 0.1,
    "skipped_fps": 5.0,
    "detection_fps": 0.2
  }
}
```

---

## 5 Whys Analysis

### Why #1: Why wasn't the degradation detected?
**Because** the health checker only checks if `camera_fps >= 1`, and the camera was reporting 5.0 fps.

### Why #2: Why does camera_fps show 5.0 when ffmpeg keeps crashing?
**Because** `camera_fps` measures the input rate from the camera source, not whether frames are being processed. Frigate's watchdog auto-restarts ffmpeg, which briefly gets frames before crashing again.

### Why #3: Why isn't the health checker monitoring skipped_fps or process_fps?
**Because** the health checker was intentionally simplified after a previous incident where complex metrics missed a different failure mode. The design prioritized "frames flowing = working" over granular metrics.

### Why #4: Why doesn't the watchdog's ffmpeg restart count as a failure?
**Because** the health checker has no visibility into ffmpeg restart events - it only queries `/api/stats` at 5-minute intervals. Between checks, ffmpeg can crash and restart multiple times without being noticed.

### Why #5: Why is the camera connection so unstable?
**Because** trendnet_ip_572w is an old IP camera (TrendNet IP-572W) with known firmware issues causing intermittent RTSP connection drops. This is a hardware limitation.

---

## Root Cause

**Technical Root Cause**: The health checker's single metric (`camera_fps >= 1`) is insufficient to detect per-camera degradation where:
1. The camera source provides frames (camera_fps > 0)
2. But the processing pipeline drops most/all of them (skipped_fps ~ camera_fps)
3. And ffmpeg repeatedly crashes/restarts between health checks

**Contributing Factors**:
1. No monitoring of `skipped_fps` ratio
2. No detection of repeated ffmpeg process crashes
3. No per-camera failure history (only global state)
4. 5-minute check interval too coarse to catch rapid crash/restart cycles

---

## Gap Analysis: Current vs Required

| Check | Current | Gap | Impact |
|-------|---------|-----|--------|
| `camera_fps >= 1` | Implemented | None | Catches dead cameras |
| `skipped_fps / camera_fps` | **Not checked** | **CRITICAL** | Misses processing backlog |
| ffmpeg crash detection | Not checked | HIGH | Misses unstable cameras |
| Per-camera failure history | Not tracked | MEDIUM | Can't identify persistently bad cameras |

---

## Resolution

Added `HIGH_SKIP_RATIO` detection to the health checker (PR pending).

### Changes Made

1. **models.py**: Added `HIGH_SKIP_RATIO = "high_skip_ratio"` to `UnhealthyReason` enum

2. **config.py**: Added `skip_ratio_threshold: float = 0.8` setting (80% default)

3. **health_checker.py**: Added `_check_camera_skip_ratio()` method that:
   - Calculates `skip_ratio = skipped_fps / camera_fps` for each camera
   - Flags cameras with skip ratio > threshold (default 80%)
   - Respects the `skip_cameras` list for cameras on flaky networks
   - Gracefully handles missing `skipped_fps` field (defaults to 0)

4. **cronjob-health-python.yaml**:
   - Added `FRIGATE_HC_SKIP_RATIO_THRESHOLD=0.8` env var
   - Removed reolink_doorbell from skip list (WiFi issues fixed)

5. **tests**: Added 6 new test cases covering:
   - High skip ratio detection (90% skipped = unhealthy)
   - Threshold boundary (80% = healthy, 82% = unhealthy)
   - Skipped cameras ignored for skip ratio check
   - Missing `skipped_fps` field gracefully handled

### Verification

```bash
cd apps/frigate-health-checker
poetry run pytest tests/test_health_checker.py -v
# 18 tests passed
```

---

## Future Improvements (Out of Scope)

1. **Per-camera failure history**: Track camera-specific failure counts in ConfigMap
2. **ffmpeg crash detection**: Monitor PID changes or parse logs for crash patterns
3. **Recording age check**: Verify newest segment is <10 minutes old
4. **Alerting granularity**: Alert on specific camera vs full restart

---

## Lessons Learned

1. **Outcome metrics aren't enough**: "Frames flowing" (`camera_fps > 0`) doesn't mean "frames being processed"
2. **Watchdog masks failures**: Auto-restart hides crash loops from interval-based health checks
3. **Review skip lists periodically**: reolink_doorbell was skipped for WiFi issues that have since been fixed - stale skip lists reduce monitoring coverage

---

## Tags

rca, frigate, health-checker, camera-degradation, skipped-fps, ffmpeg-crash, trendnet, mitigation
