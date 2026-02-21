# 62 Commits, 6 RCAs, 1 Camera App: Why Production SRE Is So Hard

*2026-02-21*

I've been running Frigate NVR on my homelab K3s cluster since late 2025. It's a camera app. It watches my front door, living room, and hallway. Five cameras. One pod. How hard can it be?

62 GitOps commits. 16 health checker commits. 6 formal RCAs. Two complete rewrites of the monitoring system. And today I discovered a supporting service had been crash-looping for six days with 1,922 restarts — and nobody noticed.

## The Myth of the Simple Deployment

Here's what "deploy Frigate on Kubernetes" actually means:

- Configure Coral USB TPU passthrough through Proxmox → VM → K3s → pod
- Set up AMD GPU passthrough for hardware-accelerated video decoding
- Manage SOPS-encrypted secrets for camera credentials and MQTT
- Configure go2rtc as an RTSP proxy with per-camera stream settings (some cameras need HTTP-FLV, some need RTSP, one needs MJPEG-to-H264 transcoding)
- Set up MetalLB for external IPs, Traefik for ingress, DNS for service discovery
- Build a health checker that can detect camera failures, TPU hangs, and frame-skip degradation
- Build a webhook that auto-updates configs when cameras get new DHCP leases
- Wire alerts through to email without creating notification storms

Each of these has failed at least once. Most have failed multiple times in different ways.

## The Fix Treadmill

Every reliability improvement I've made has created a new problem:

**Auto-restart on failure** seemed obvious. Frigate hangs? Kill the pod. Except when Frigate was restarting, the next health check would see it as down, trigger another restart, send another alert, and I'd wake up to 47 emails.

**Alert-once-per-incident** fixed the storm. But then I added a 24-hour cooldown, and now I worry about missing a new incident during the cooldown window.

**Check camera FPS** caught dead cameras. But one camera was reporting 5 FPS while skipping 100% of frames — technically alive, functionally useless. So I added frame-skip ratio detection. Then the detection itself had a JSON parsing bug because the Kubernetes exec API sometimes returns Python dict repr instead of JSON.

**Restart when unhealthy** made sense until a single WiFi doorbell started flapping. One flaky camera on WiFi would trigger a full Frigate restart every 10 minutes. So I added a majority threshold — only restart when most cameras are down. Now the doorbell can die quietly without taking everything else with it. But what if two cameras drop? Is 2/5 "majority enough"?

## The Layers of Things That Can Break

Today's debugging session was a perfect illustration. I went in to check on the health checker. What I found:

1. **Health checker**: Working perfectly. My recent majority-threshold fix correctly identified the doorbell as down and correctly decided not to restart Frigate. This was the thing I was worried about, and it was fine.

2. **Reolink doorbell**: 0 FPS. Frigate's internal watchdog was cycling ffmpeg every 10 seconds. The go2rtc proxy showed the doorbell trickling data at 12 MB while healthy cameras were at 355 MB. Pings from the Proxmox host showed 33% packet loss. The camera's WiFi was degraded — a hardware problem no software can fix.

3. **IP webhook**: 1,922 restarts over 6 days. Flask's single-threaded dev server eventually hangs, the liveness probe kills it, Kubernetes restarts it, back-off timer increases, rinse and repeat. Nobody monitors the webhook because the webhook is supposed to be the thing that handles failures.

Three layers, three different failure modes, all independent of each other. The application (Frigate) was fine. The monitoring (health checker) was fine. The supporting automation (webhook) was on fire. And the hardware (doorbell WiFi) was the actual root cause of the visible symptom.

## The Reliability Stack

Here's what my "simple camera app" actually sits on:

```
Camera WiFi signal
  → Camera firmware (RTSP/HTTP-FLV server)
    → Home network (DHCP, DNS)
      → Proxmox host (VT-d, IOMMU, USB passthrough)
        → K3s VM (kubelet, containerd)
          → K3s cluster (scheduler, API server)
            → MetalLB (IP advertisement)
              → Traefik (ingress, TLS)
                → Frigate pod (go2rtc, ffmpeg, Coral TPU, GPU)
                  → Health checker CronJob
                    → Alert notifications
                      → IP webhook
```

Thirteen layers. Any one can fail. They fail in combinations. And when they fail, the symptoms often point to the wrong layer — today the doorbell appeared to be a Frigate problem, but it was a WiFi problem.

## What I've Learned

**Reliability is logarithmic.** Getting from 0% to 90% took about 10 commits. Getting from 90% to 99% took another 50. The last 1% — the edge cases, the timing issues, the hardware flaps — might take another 50. And 100% doesn't exist.

**Monitoring is recursive.** You need health checks to detect failures. You need alerts to notify about health checks. You need monitoring to verify alerts work. You need monitoring for the monitoring. Today I found a service that had been failing for six days because nobody monitors the webhook.

**Hardware doesn't care about your abstractions.** Kubernetes promises declarative state management. The Coral USB TPU doesn't know what a Pod is. The camera doesn't know what DHCP is. WiFi signals don't read your runbooks. The most perfectly designed system still breaks when a $50 camera loses its WiFi connection.

**Simple applications have complex failure modes.** Frigate itself is excellent software. I've never had a bug in Frigate. Every single one of my 6 RCAs is about the infrastructure around it: the health checker, the network, the hardware passthrough, the Kubernetes cluster, the monitoring, the monitoring of the monitoring.

## Where I Am Now

Five cameras streaming. Health checker running every 5 minutes, correctly detecting degradation, correctly deciding when to act. Doorbell switched from DNS to direct IP to reduce reconnection latency. Webhook resurrected after a manual pod delete.

It works. Today. Ask me again in a week.

The homelab community loves to say "it's just a hobby." But running infrastructure reliably — even at hobby scale — is genuinely one of the hardest problems in computing. Not because any single piece is hard, but because reliability is an emergent property of every piece working together, all the time, including the pieces you forgot about.

Sixty-two commits in. Still going.
