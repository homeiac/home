# Debugging Camera Streams at Midnight: A Tale of Two Failures

*2026-02-21*

I recently shipped a bunch of fixes to my Frigate health checker — majority-threshold restart logic, 24-hour alert cooldowns, better image tagging. Time to check if everything's actually working. What I found was two unrelated problems hiding in plain sight.

## The Setup

My homelab runs Frigate NVR on K3s with 5 cameras, a CronJob health checker every 5 minutes, and an IP webhook that auto-updates camera configs when DHCP leases change. The health checker was the star of recent work. The webhook? I'd forgotten about it.

## Finding 1: The Doorbell That Cried Wolf

The health checker logs told a clear story:

```json
{"cameras_down": 1, "total_monitored": 5,
 "cameras": ["reolink_doorbell(fps=0.0)"],
 "event": "Some cameras have no frames (not restarting)"}
```

One camera down, four healthy. The health checker correctly decided not to restart Frigate — that's the majority-threshold logic I'd just shipped. Working as designed.

But why was the doorbell down?

### Following the Breadcrumbs

Frigate's internal logs showed a tight crash loop, roughly every 10 seconds:

```
watchdog.reolink_doorbell ERROR: No new recording segments in the last 120s
ffmpeg.reolink_doorbell   ERROR: Error opening input: Invalid data found
watchdog.reolink_doorbell INFO:  Restarting ffmpeg...
```

The ffmpeg process would start, fail to read the stream, get killed by the watchdog, restart, fail again. Meanwhile the go2rtc API revealed how bad things were. The doorbell had pushed 12 MB of data since pod start. The hall camera? 355 MB. Same timeframe.

A ping from the Proxmox host confirmed it — 33% packet loss, 60-120ms latency. The doorbell's WiFi was struggling.

### The DNS Tax

Here's the thing that bugged me. Every other camera in my config uses a direct IP:

```yaml
hall_main: "rtsp://admin:pass@192.168.1.137:554/..."
living_room_main: "rtsp://admin:pass@192.168.1.138:554/..."
```

But the doorbell? DNS hostname:

```yaml
reolink_doorbell_main: "ffmpeg:http://reolink-vdb.home.panderosystems.com/flv?..."
```

Every time go2rtc reconnected (which was constantly), it had to resolve that hostname. On a flaky connection that's reconnecting every few seconds, that's an extra round-trip and failure mode for no reason.

I switched it to the direct IP. The doorbell actually recovered on its own before the change deployed, but removing that DNS dependency should help on the next WiFi hiccup.

## Finding 2: The Webhook That Wouldn't Die

While checking the namespace, this jumped out:

```
frigate-ip-webhook-774cfd856c-m8c7w  0/1  CrashLoopBackOff  1916 restarts  5d23h
```

Nearly two thousand restarts. Six days of crash-looping. And I hadn't noticed because... it doesn't have alerting.

The webhook is a simple Flask app — receives camera IP updates from Home Assistant, patches the Frigate ConfigMap, triggers a restart. Maybe 200 lines of Python. Its `/health` endpoint returns `{"status": "healthy"}`. That's it.

### Death by Liveness Probe

Exit code 137: SIGKILL. The liveness probe was executing the container every ~2 minutes. The probe hits `/health` every 30 seconds, fails after 3 misses. Somewhere in those 90 seconds, Flask stopped responding.

The culprit? Flask's built-in development server. Single-threaded. No concurrent request handling. If the Kubernetes Python client does anything blocking in a background thread — a stale watch, a connection timeout — the health endpoint hangs waiting its turn.

### The Fix Was Embarrassingly Simple

```bash
kubectl delete pod frigate-ip-webhook-774cfd856c-m8c7w
```

New pod came up. Health checks passing. Still running hours later.

After 1,922 restarts, the back-off timer was maxed at 5 minutes between attempts. The container would start, run for 2 minutes, get killed, wait 5 minutes, repeat. Deleting the pod reset the back-off counter and gave it a clean start.

## The Irony

The health checker I spent days perfecting? Working flawlessly. Correctly detecting the degraded camera, correctly deciding not to restart Frigate, logging everything clearly.

The webhook I built weeks ago and forgot about? On fire for six days straight. No health checker watching the health checker's neighbor.

## Takeaways

**Flask's dev server is not a web server.** I know this. Everyone knows this. Yet there it is in production, `app.run(host="0.0.0.0", port=port)`, no gunicorn, no threading. For a webhook that gets called maybe twice a month, it felt like overkill to add a real WSGI server. It wasn't.

**CrashLoopBackOff is quicksand.** The more a pod restarts, the longer the back-off, the less time it has to prove it's healthy, the more likely the probe kills it again. Sometimes the best fix is to delete the pod and let it start fresh with no history.

**DNS is a feature, not a requirement.** For LAN devices with known static-ish IPs, DNS hostnames add a dependency that provides no value. Every other camera was on a direct IP. The one using DNS was the one that couldn't stay connected.

**Monitor your monitors.** The health checker watches Frigate. Nobody watches the webhook. The cobbler's children have no shoes.
