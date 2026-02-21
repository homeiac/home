# RCA: Reolink Doorbell Stream Failure and IP Webhook CrashLoopBackOff

**Incident Date**: 2026-02-21
**Duration**: ~30+ minutes (doorbell), ~6 days (webhook)
**Impact**: reolink_doorbell camera at 0 FPS, frigate-ip-webhook in CrashLoopBackOff with 1,922 restarts
**Detection**: Manual investigation (health checker correctly reported 4/5 cameras OK but did not restart Frigate — by design)

---

## Incident Summary

Two separate issues discovered during a routine check of the frigate-health-checker deployment:

1. **reolink_doorbell** camera stream completely down (0 FPS), with Frigate's internal watchdog cycling ffmpeg every ~10 seconds
2. **frigate-ip-webhook** pod stuck in CrashLoopBackOff for 5 days 23 hours with 1,922 restarts

---

## Issue 1: Reolink Doorbell Stream Failure

### Timeline

| Time | Event |
|------|-------|
| Unknown | Doorbell stream begins failing |
| 21:15 UTC | Health checker reports `reolink_doorbell(fps=0.0)` — 1/5 cameras down |
| 21:20 UTC | Same — doorbell still down |
| 21:25 UTC | Same — doorbell still down |
| 21:30 UTC | Same — Frigate logs show ffmpeg crash loop |
| 21:33 UTC | go2rtc API shows doorbell barely trickling data (12 MB vs 355 MB for healthy cameras) |
| 21:35 UTC | Doorbell self-recovers — health checker reports 5/5 cameras OK |
| 21:44 UTC | Committed configmap change: DNS → direct IP for doorbell streams |

### Root Cause

The doorbell's RTSP/HTTP-FLV stream was unreachable from Frigate. Evidence:

1. **Frigate logs** showed a tight crash loop:
   ```
   watchdog.reolink_doorbell ERROR: No new recording segments were created in the last 120s
   ffmpeg.reolink_doorbell.detect ERROR: Error opening input: Invalid data found when processing input
   ffmpeg.reolink_doorbell.detect ERROR: Error opening input file rtsp://127.0.0.1:8554/reolink_doorbell_sub
   ```

2. **Network diagnostics** from Proxmox host showed 33% packet loss and 59-121ms latency to 192.168.1.10 (the doorbell). The doorbell's WiFi connection was degraded.

3. **go2rtc stream stats** confirmed the doorbell was barely connected:
   - doorbell_main: 8,568 packets / 12 MB (vs hall_main: 272,112 packets / 355 MB)
   - Stream producer IDs in the 450+ range (healthy cameras were in single digits), indicating many reconnection attempts

4. **DNS overhead**: The doorbell was configured via `reolink-vdb.home.panderosystems.com` hostname, adding an unnecessary DNS resolution step on every reconnection attempt.

### Contributing Factor

The doorbell used DNS hostname (`reolink-vdb.home.panderosystems.com`) while all other cameras used direct IP addresses. On a flaky WiFi connection with frequent reconnects, DNS resolution adds latency and another failure mode.

### Resolution

Changed the Frigate configmap go2rtc streams from DNS to direct IP:
```yaml
# Before
reolink_doorbell_main: "ffmpeg:http://reolink-vdb.home.panderosystems.com/flv?..."
# After
reolink_doorbell_main: "ffmpeg:http://192.168.1.10/flv?..."
```

The doorbell also self-recovered before the change was deployed, suggesting the WiFi connection stabilized.

### Health Checker Behavior

The health checker correctly:
- Detected the doorbell was down (1/5 cameras)
- Did NOT restart Frigate (majority-of-cameras threshold not met)
- Logged clear warnings: `"Some cameras have no frames (not restarting)"`

This is the intended behavior from commit `b3c8174` ("fix: only restart Frigate when majority of cameras are down").

---

## Issue 2: IP Webhook CrashLoopBackOff

### Timeline

| Time | Event |
|------|-------|
| 2026-02-15 21:50 | Webhook pod created |
| Unknown | Pod begins crash-looping |
| 2026-02-21 21:34 | Last container start — killed 2 minutes later (exit 137) |
| 2026-02-21 21:44 | Pod deleted to force fresh restart |
| 2026-02-21 21:45 | New pod comes up healthy, all probes passing |

### Root Cause

The pod had accumulated 1,922 restarts over 6 days and was stuck in maximum back-off (5 minutes between restart attempts). Exit code 137 (SIGKILL) indicates the liveness probe was killing the container after 3 consecutive failed health checks.

The Flask development server (single-threaded, no production WSGI server) likely hung on a blocking operation, causing the `/health` endpoint to become unresponsive. With the liveness probe checking every 30 seconds and failing after 3 attempts (~90 seconds), any blocking call > 90 seconds would trigger a restart.

Possible triggers:
- The `kubernetes` Python client performing a blocking API call during garbage collection or background thread
- Flask dev server unable to handle concurrent requests (health probe arrives while another request is in-flight)

### Resolution

Deleted the pod (`kubectl delete pod`). The new pod started cleanly and has been healthy since, with all liveness and readiness probes passing.

### Recommendations

1. **Use a production WSGI server** (gunicorn) instead of Flask's built-in dev server
2. **Add `threaded=True`** to `app.run()` at minimum so health checks aren't blocked
3. **Consider if this webhook is still needed** — the doorbell (the flakiest camera) was just switched to a static IP, and the other cameras have stable DHCP leases

---

## Action Items

| Item | Status |
|------|--------|
| Switch doorbell streams from DNS to IP | Done (commit `9c1d932`) |
| Delete stale webhook pod | Done |
| Consider gunicorn for webhook | TODO |
| Consider removing webhook entirely if IPs are stable | TODO |
| Monitor doorbell stability post-change | TODO |

---

## Lessons Learned

1. **CrashLoopBackOff can be self-perpetuating**: After 1,922 restarts, the 5-minute back-off meant the pod barely ran. Simply deleting it and starting fresh fixed the issue.
2. **Flask dev server is not production-ready**: Even for a simple webhook, a single-threaded server + liveness probes = eventual crash loop.
3. **DNS adds failure modes**: For LAN devices with known IPs, direct IP is more reliable than hostname resolution, especially for devices with flaky network connectivity.
4. **The health checker's majority-threshold logic worked correctly**: It correctly avoided restarting Frigate for a single-camera outage.
