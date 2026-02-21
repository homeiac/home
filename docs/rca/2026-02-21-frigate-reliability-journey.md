# RCA: The Frigate Reliability Journey — Why "Just Run a Camera App" Takes 62 Commits and 6 RCAs

**Period**: 2025-10 through 2026-02-21
**Scope**: Frigate NVR deployment, health checking, camera management, and all supporting infrastructure
**Category**: Systemic / Meta-RCA

---

## Summary

Getting Frigate NVR to run reliably on a homelab K3s cluster has required **62 GitOps commits**, **16 health checker commits**, **6 dedicated RCAs**, and the system is still not fully autonomous. This meta-RCA examines why achieving production-grade reliability for a single application is so hard — even when you know what you're doing.

---

## The Numbers

| Metric | Count |
|--------|-------|
| GitOps commits (Frigate namespace) | 62 |
| Health checker code commits | 16 |
| Formal RCAs written | 6 |
| Blog posts about Frigate issues | 4+ |
| Hardware migrations | 3 (still-fawn → pumped-piglet → still-fawn) |
| Camera additions/removals/reconfigurations | 8+ |
| Webhook restarts before someone noticed | 1,922 |
| Times the health checker was rewritten | 2 (bash → Python, then simplified) |

---

## The Incident Timeline: Death by a Thousand Cuts

### Phase 1: Initial Deployment (2025-10 to 2025-12)
**Goal**: Just get Frigate running on K3s with GitOps.

| Commit/Event | What went wrong |
|--------------|----------------|
| `b75f352` | Initial GitOps migration — ConfigMap, secrets, SOPS encryption |
| `dbc94f4` | Coral TPU migration between nodes (hardware dependency) |
| `8292b6f` | AMD GPU passthrough for VAAPI — needed LIBVA_DRIVER_NAME env and /sys mount |
| `f2852f9` | PVC-only config for UI mask persistence — then reverted (`f7cb21e`) because complexity |
| `190d639` | Init container to copy ConfigMap to PVC — also reverted |
| `0ada79b` | Writable config attempt #2 |

**Lesson**: Hardware passthrough (GPU, TPU) in Kubernetes is a minefield. Every node migration means reconfiguring device paths, IOMMU groups, and driver mounts.

### Phase 2: Health Checker v1 — Bash (2026-01)
**Goal**: Auto-detect and fix Frigate failures.

| Commit/Event | What went wrong |
|--------------|----------------|
| `48a91cf` | Initial CronJob — wrong image, wrong RBAC |
| `303ab12` | Fix image and RBAC permissions |
| `42ff998` | Fix grep count output parsing |
| RCA 2026-01-06 | 5 separate failures in one debugging session: wrong image tag, Tailscale routing, no bash in alpine, Flux reverting manual applies, grep edge cases |
| `de5697c` | Alert storm — sent duplicate notifications every 5 minutes |
| `ba3813b` | Tried restarting Frigate when the node was down (pointless) |
| RCA 2026-01-17 | Alert storm + pointless restarts when node unavailable |

**Lesson**: A bash script CronJob that shells into pods to check health is inherently fragile. Every layer (image, RBAC, shell parsing, state management via ConfigMap) is a failure mode.

### Phase 3: Health Checker v2 — Python Rewrite (2026-02)
**Goal**: Proper health checking with tests, type safety, and better failure detection.

| Commit/Event | What went wrong |
|--------------|----------------|
| `032f085` | Python health checker deployed |
| `223f173` | Forgot to copy README.md for poetry package install |
| `7a4c11b` | `_preload_content=False` needed to fix JSON quote conversion in K8s API |
| `cdbf2db` | JSON parsing still broken — different failure mode |
| `9857b35` | Gave up on complex metrics, simplified to just check camera FPS |
| `4260017` | Rewrote tests for simplified approach |
| RCA 2026-02-12 | Coral TPU crashed 18 times in 6 hours — health checker didn't catch it |
| `43801d4` | Added frame skip ratio detection |
| RCA 2026-02-13 | trendnet camera degraded (100% frame skip) — health checker still missed it |
| `e869957` | Fixed RBAC, added alert-on-unhealthy-without-restart |
| `57f0f28` | K8s stream returned Python dict repr instead of JSON — had to handle both |
| `8fba735` | 24h alert cooldown (alert fatigue from too many notifications) |
| `b3c8174` | Only restart when majority of cameras are down (single camera flaps caused unnecessary restarts) |

**Lesson**: Every fix reveals the next failure mode. Fix detection → discover alerting is broken → fix alerting → discover it alerts too much → add cooldowns → discover it restarts too aggressively → add thresholds.

### Phase 4: Camera Wrangling (Ongoing)
**Goal**: Keep 5 cameras streaming reliably.

| Event | What went wrong |
|-------|----------------|
| `44fbe13` | Disabled doorbell (offline for days) |
| `8531108` | Re-enabled doorbell |
| `cc5b4ff` | DNS resolution broken for doorbell — switched to FQDN |
| `9b03964` | FQDN broken — switched to DNS name |
| `48f7654` | E1 Zoom doesn't support HTTP-FLV — had to use RTSP |
| `d9124d9` | Living room camera changed IP |
| `2f4a7c9` | Both indoor cameras changed IPs |
| `9c1d932` | Doorbell DNS → IP (today — DNS adding latency on flaky WiFi) |
| Today | Doorbell at 0 FPS, self-recovered, IP webhook crashed 1,922 times unnoticed |

**Lesson**: Cameras are the most unreliable component. WiFi drops, DHCP leases change, firmware hangs, streams corrupt. The application layer can be perfect and still fail because a $50 camera lost WiFi.

### Supporting Infrastructure Failures

| RCA | What went wrong |
|-----|----------------|
| RCA 2026-01-25 | K3s upgrade killed kubelet, MetalLB stopped announcing Frigate IP |
| RCA 2025-10-04 | Proxmox cluster failure took down the node running Frigate |
| RCA 2025-12-27 | Time drift caused PVE API 401s, cascading into cluster instability |

**Lesson**: The application sits on a stack of infrastructure, and any layer can fail. Frigate can be healthy while MetalLB, kubelet, Proxmox, or the physical node beneath it breaks.

---

## Why Production SRE Is So Hard

### 1. The Failure Surface Is Combinatorial

Frigate alone touches: K3s scheduler, container runtime, ConfigMap, SOPS secrets, MetalLB, Traefik ingress, Coral USB TPU, AMD GPU (VAAPI), go2rtc, ffmpeg, RTSP/HTTP-FLV protocols, WiFi cameras, DHCP, DNS, MQTT (Home Assistant), PVC storage, and CronJob scheduling.

Any one of these can fail. And they fail in **combinations** — TPU hangs + camera WiFi drops + health checker has a parsing bug = undetected multi-hour outage.

### 2. Every Fix Creates a New Edge Case

| Fix | New problem it created |
|-----|----------------------|
| Auto-restart on failure | Alert storm from restart loop |
| Alert-once-per-incident | Missed new incidents during cooldown |
| Check camera FPS | Missed frame-skip degradation (FPS > 0 but all frames skipped) |
| Restart on unhealthy | Restarted when single flaky camera was down |
| Majority threshold | Now won't restart when 2/5 cameras drop (is that enough?) |
| IP webhook for DHCP | Webhook itself crashed for 6 days unnoticed |

### 3. Observability Is a Fractal Problem

You need monitoring to detect failures. But monitoring itself fails:
- Health checker had JSON parsing bugs
- Alert notifications had duplicate/storm issues
- The webhook that updates camera configs was in CrashLoopBackOff for 6 days
- Nobody monitors the monitors

### 4. Hardware Doesn't Respect Software Abstractions

Kubernetes promises declarative state management. But:
- USB TPU devices need physical passthrough and can't be rescheduled
- GPU passthrough requires IOMMU groups, VT-d BIOS settings, specific device paths
- Camera WiFi drops can't be fixed by restarting a pod
- Node hardware failures cascade through the entire stack

### 5. The Long Tail of Reliability

Getting from 0% to 90% reliability took the first 10 commits. Getting from 90% to 99% took the next 50. The last 1% — the doorbell WiFi drops, the webhook CrashLoopBackOff, the TPU that hangs once every 6 hours — may take another 50.

---

## Current State (2026-02-21)

| Component | Status | Confidence |
|-----------|--------|------------|
| Frigate pod | Running | High |
| Health checker CronJob | Running, correct behavior | High |
| Coral TPU | Stable (since migration) | Medium |
| 4/5 cameras | Streaming | High |
| Reolink doorbell | Recovered, now on direct IP | Low (WiFi-dependent) |
| IP webhook | Running (after manual pod delete) | Low (Flask dev server) |
| Alert notifications | Working with 24h cooldown | Medium |

**Still unresolved**:
- Webhook needs gunicorn (or removal)
- Doorbell WiFi reliability is a hardware problem
- No alerting on webhook health
- Majority-threshold restart logic needs tuning (what if 2/5 cameras drop?)

---

## Conclusion

62 commits. 6 RCAs. 1 application. Still not done.

This is production SRE in miniature. The application works — Frigate itself has been excellent software. The hard part is everything around it: the infrastructure it runs on, the hardware it depends on, the monitoring that watches it, the automation that fixes it, and the automation that watches the automation.

Every layer you add for reliability becomes a new thing that can break.
