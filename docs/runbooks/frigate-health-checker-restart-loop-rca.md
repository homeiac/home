# RCA: Frigate Health Checker Restart Loop After VM Boot

**Date**: 2026-03-01
**Severity**: Medium
**Impact**: Frigate NVR repeatedly restarted for ~20 minutes after VM 105 booted, causing intermittent camera outage and elevated CPU/fan noise on pumped-piglet. Each restart cycle pushed CPU to 75-77°C and fans to 1900-2100 RPM.
**Resolution**: Added 10-minute startup grace period to health checker. Frigate stabilized after final restart and has been running without interruption since.

## Executive Summary

After powering on pumped-piglet and VM 105, the Frigate health checker CronJob (running every 5 minutes) detected Frigate as unhealthy during its initialization window and repeatedly triggered rolling restarts. Each restart killed the Frigate pod before cameras could finish connecting, resetting the initialization cycle. This created a restart loop that consumed significant CPU, elevated temperatures, and increased fan noise.

The root cause was that the health checker had no awareness of pod age — it treated a 60-second-old pod the same as a 60-minute-old pod. Since Frigate requires 5-10 minutes to initialize (load detector model, connect RTSP streams, start ffmpeg processes per camera), the health checker's 5-minute schedule with 2-consecutive-failure threshold could trigger a restart before initialization completed.

## Investigation

### Discovery Flow

```
pumped-piglet powered on, VM 105 auto-started
    │
    ▼
Temp/load initially settling (46°C, load ~5)
    │
    ▼
Sudden spike: 75°C, load 12.7, Fan1 2131 RPM
    │
    ▼
top inside VM 105:
    ├── frigate (PID 36283): 999.9% CPU  ← initializing
    ├── k3s-server: 18.2% CPU
    ├── 3x ffmpeg processes: 9.1% each
    └── prometheus: 9.1% CPU
    │
    ▼
kubectl get pods -n frigate:
    ├── frigate-54f7c4d867-sz8p4  Running  42s    ← NEW pod hash
    ├── frigate-7bc659b5f5-flbt6  (was running 4 min ago, now gone)
    ├── frigate-5d446f4997-85xgp  Unknown         ← stale from crash
    └── frigate-5d446f4997-kr2s9  ContainerStatusUnknown ← stale
    │
    ▼
Different ReplicaSet names confirm Deployment spec changed (not pod restart)
    │
    ▼
kubectl get events -n frigate:
    ├── ScalingReplicaSet: Scaled down frigate-7bc659b5f5 from 1 to 0
    ├── ScalingReplicaSet: Scaled up frigate-54f7c4d867 from 0 to 1
    └── Pattern: health checker completed → Frigate killed → new pod
    │
    ▼
kubectl get deployment frigate -o jsonpath={.spec.template.metadata.annotations}:
    └── restartedAt: "2026-03-01T16:30:13"  ← health checker's restart mechanism
    │
    ▼
ConfigMap frigate-health-state:
    ├── consecutive_failures: 0  (reset after restart)
    ├── last_restart_times: 1772382613  (= 2026-03-01T16:30:13 UTC)
    └── Confirms health checker triggered the restart
    │
    ▼
kubectl rollout history deployment/frigate:
    └── Revision 151  ← accumulated over weeks of restarts
```

### Key Diagnostic Commands

| Command | Revealed |
|---------|----------|
| `sensors` on pumped-piglet | CPU oscillating 44-77°C (settling then spiking) |
| `top` inside VM via `qm guest exec` | Frigate at 999.9% CPU during initialization |
| `kubectl get pods -n frigate` | Pod age only 42s, different ReplicaSet hash from minutes ago |
| `kubectl get events -n frigate` | Health checker completing → Frigate scaled down → new pod created |
| Deployment annotation `restartedAt` | Timestamp matched health checker's `last_restart_times` |
| `kubectl rollout history` | 151 revisions accumulated |

## Root Cause Analysis

### Problem Chain

```
┌─────────────────────────────────────────────────────────────────┐
│  Root Cause: No startup grace period in health checker          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Context: Health checker design assumptions                     │
│  - CronJob runs every 5 minutes                                │
│  - Restart after 2 consecutive failures (= 10 min)             │
│  - Frigate needs 5-10 min to initialize after cold start        │
│  - No awareness of pod age or recent deployment                 │
│                                                                 │
│  Trigger: VM 105 started after shutdown                         │
│                                                                 │
│  1. Frigate pod starts, begins initialization                   │
│  2. Health checker runs at t+5 min                              │
│     └─ Frigate API unresponsive or cameras not connected        │
│     └─ consecutive_failures → 1                                 │
│  3. Health checker runs at t+10 min                             │
│     └─ Frigate still initializing (or just barely ready)        │
│     └─ consecutive_failures → 2 (= threshold)                  │
│     └─ Triggers rollout restart                                 │
│  4. New pod starts, initialization resets to t=0                │
│  5. Steps 2-4 repeat                                            │
│                                                                 │
│  Amplifiers:                                                    │
│                                                                 │
│  - Each Frigate init cycle burns ~1000% CPU (10 cores)          │
│  - CPU spike → fans ramp to 2100+ RPM                           │
│  - Restart kills ffmpeg processes mid-connect                   │
│  - Circuit breaker (2/hour) should eventually stop it           │
│    but pod hash changes reset the deployment context            │
│                                                                 │
│  Self-limiting factor:                                          │
│  - Circuit breaker caps at 2 restarts/hour                      │
│  - After 2 restarts, next check finds Frigate healthy           │
│    (enough time passed for cameras to connect)                  │
│  - Loop breaks when initialization finally completes            │
│    within the 10-min window between restart attempts             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Why Frigate Takes So Long to Initialize

Frigate 0.16.0 cold start sequence:

1. **Load detector model** (~30s) — Coral TPU model loaded via pycoral
2. **Start ffmpeg processes** (~60s) — One per camera (4 cameras), each negotiating RTSP
3. **Buffer fill** (~60-120s) — Camera FPS counters start at 0, ramp up as buffers fill
4. **Detection warmup** (~30-60s) — First inference cycles are slower, stabilizes after ~50 frames

Total: 3-5 minutes minimum, up to 10 minutes if RTSP sources are slow to respond or if the Coral TPU needs a cold reset after VM reboot.

### Why the Health Checker Didn't Account for This

The health checker was designed for steady-state monitoring — detect when a running Frigate instance becomes unhealthy (camera disconnects, ffmpeg crash loops, API hangs). The cold-boot scenario was never considered because:

1. VMs rarely reboot (last reboot was months ago)
2. Testing was done against already-running Frigate instances
3. The `consecutive_failures_required=2` was meant as a debounce, not a startup delay

## Timeline

| Time (UTC) | Event |
|------------|-------|
| ~16:00 | pumped-piglet powered on, VM 105 auto-starts |
| ~16:00-16:05 | K3s starts, Frigate pod scheduled and begins initialization |
| ~16:05 | Health checker CronJob runs, Frigate API unresponsive → failure 1 |
| ~16:10 | Health checker runs again, cameras still connecting → failure 2 → **restart triggered** |
| ~16:10 | Frigate pod killed, new pod starts, initialization resets |
| 16:11 | Monitoring shows: 75.5°C, load 12.74, Fan1 2131 RPM |
| ~16:15 | Health checker runs, new pod still initializing → failure 1 |
| ~16:20 | Health checker runs → failure 2 → **restart triggered again** |
| 16:22 | `top` shows frigate at 999.9% CPU (initialization), load 15.41 |
| ~16:25 | Health checker runs → failure 1 (or healthy — race condition) |
| 16:27 | Temp drops to 52°C, load 11.45 (settling between restarts) |
| 16:29 | Temp drops to 46°C, load 4.88 (briefly stable) |
| 16:30:13 | Health checker triggers **final restart** (confirmed by ConfigMap timestamp) |
| ~16:31 | New pod `frigate-54f7c4d867-sz8p4` starts |
| 16:31 | Temp spikes to 75°C again (re-initialization) |
| ~16:35 | Health checker runs, Frigate still initializing → failure 1 |
| ~16:40 | Health checker runs, Frigate now healthy → **consecutive_failures reset to 0** |
| 16:45 | Confirmed stable: 46.5°C, load 2.83, Fan1 1239 RPM |
| 16:56 | Still stable: pod age 25 min, no further restarts |

## Resolution

### Immediate (Stabilization)

Frigate self-stabilized after the final restart at 16:30 had enough time to complete initialization before the next health check cycle detected failures.

### Preventive (Code Fix)

Added a **startup grace period** to the health checker (commit `e0da6dc`):

**`config.py`** — New setting:
```python
startup_grace_period_seconds: int = Field(
    default=600, description="Seconds after pod start before restarts are allowed"
)
```

**`kubernetes_client.py`** — New method to get pod start time:
```python
def get_pod_start_time(self, pod: V1Pod) -> int | None:
    # Prefers container start time, falls back to pod creation time
```

**`health_checker.py`** — Grace period check in `evaluate_restart()`:
```python
pod_start_time = health_result.metrics.pod_start_time
if pod_start_time is not None:
    pod_age = int(time.time()) - pod_start_time
    if pod_age < self.settings.startup_grace_period_seconds:
        return RestartDecision(
            should_restart=False,
            reason=f"Startup grace period: pod is {pod_age}s old",
        )
```

**Behavior change**: Health checker still detects and logs unhealthy status during startup, still increments `consecutive_failures`, but will not trigger a restart until the pod is at least 10 minutes old. This means:
- Failures during startup are visible in logs (good for debugging)
- Circuit breaker still accumulates if needed
- After 10 minutes, if Frigate is genuinely unhealthy, restart proceeds normally

### Stale Pod Cleanup (TODO)

Two stale pods remain from the original PBS disk-full crash (Feb 28):
- `frigate-5d446f4997-85xgp` — Status: Unknown
- `frigate-5d446f4997-kr2s9` — Status: Init:ContainerStatusUnknown

These are harmless but should be cleaned up: `kubectl delete pod -n frigate frigate-5d446f4997-85xgp frigate-5d446f4997-kr2s9 --force --grace-period=0`

## Verification

```bash
# Verify health checker image updated with grace period fix
ssh root@pumped-piglet.maas 'qm guest exec 105 -- bash -c \
  "kubectl get cronjob frigate-health-checker -n frigate -o jsonpath={.spec.jobTemplate.spec.template.spec.containers[0].image}"'

# Simulate: check that health checker logs show grace period skip
ssh root@pumped-piglet.maas 'qm guest exec 105 -- bash -c \
  "kubectl logs -n frigate -l app=frigate-health-checker --tail=50 2>&1"'

# Check Frigate pod has been stable (no recent restarts)
ssh root@pumped-piglet.maas 'qm guest exec 105 -- bash -c \
  "kubectl get pods -n frigate -o wide"'

# Check health state ConfigMap (consecutive_failures should be 0)
ssh root@pumped-piglet.maas 'qm guest exec 105 -- bash -c \
  "kubectl get configmap frigate-health-state -n frigate -o jsonpath={.data}"'
```

## Lessons Learned

### What Went Wrong

1. **Health checker assumed steady-state operation** — No consideration for cold-boot initialization time. The 5-minute check interval and 2-failure threshold (10 min total) overlapped with Frigate's 5-10 minute startup window, creating a race condition.

2. **Restart mechanism resets initialization** — Each `rollout restart` creates a new pod, resetting the startup clock. This turned a one-time initialization delay into a repeating loop.

3. **No pod-age awareness** — The health checker checked Frigate's health status but not how long the pod had been running. A 60-second-old pod was treated identically to a 60-minute-old pod.

4. **CPU amplification** — Frigate initialization is extremely CPU-intensive (~1000% across 10 cores). Repeated restarts multiplied this cost and caused physical symptoms (fan noise, elevated temperature).

### What Went Right

1. **Circuit breaker limited damage** — Max 2 restarts/hour prevented infinite restart storms
2. **Self-stabilizing** — Eventually one restart cycle completed initialization within the health check window
3. **Quick diagnosis** — Pod age (42s) and different ReplicaSet hash immediately pointed to deployment changes, not pod crashes
4. **ConfigMap state preserved evidence** — `last_restart_times` timestamp matched exactly, confirming the health checker was the trigger

### Related Incident

This incident was triggered by the VM 105 reboot, which itself was caused by the PBS disk-full incident (see `pbs-disk-full-vm-crash-rca.md`). The chain:

```
PBS pool full → VM crash (Feb 27) → VM offline 28h → Manual restart (Mar 1)
  → Frigate initializing → Health checker restart loop → Fan noise → This RCA
```

## Prevention

### For This Health Checker

- [x] Add startup grace period (600s default) — commit `e0da6dc`
- [ ] Make grace period configurable via env var `FRIGATE_HC_STARTUP_GRACE_PERIOD_SECONDS`
- [ ] Add integration test simulating cold-boot scenario (pod age < grace period)
- [ ] Clean up stale Unknown/ContainerStatusUnknown pods after node recovery

### General Pattern: Health Checkers with Restart Authority

Any health checker that can trigger restarts should consider:

1. **Startup grace period** — Don't restart recently-created pods
2. **Initialization detection** — If possible, check if the application signals readiness (Frigate has no explicit startup probe)
3. **Exponential backoff on restarts** — Instead of fixed 2/hour, increase delay between restarts
4. **Log vs. restart distinction** — Report health issues during startup, but only act on them after grace period

## Related Documents

- PBS incident that caused the reboot: `docs/runbooks/pbs-disk-full-vm-crash-rca.md`
- PBS maintenance runbook: `docs/runbooks/pbs-backup-maintenance-runbook.md`
- Crossplane CPU fix (same investigation): `gitops/clusters/homelab/infrastructure/crossplane/helmrelease.yaml`
- Health checker source: `apps/frigate-health-checker/src/frigate_health_checker/`
- Health checker CronJob: `gitops/clusters/homelab/apps/frigate/cronjob-health-python.yaml`
- Fix commit: `e0da6dc` — "fix: add startup grace period to frigate health checker"

## Tags

frigate, health-checker, restart-loop, startup, grace-period, initialization, cronjob, cold-boot, cpu, fan-noise, temperature, pumped-piglet, vm-105, k3s, kubernetes, deployment, rollout, rca, root-cause-analysis, frigate-health-checker, circuit-breaker, ffmpeg, rtsp, camera

**Owner**: Homelab
**Last Updated**: 2026-03-01
