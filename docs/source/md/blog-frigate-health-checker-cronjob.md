# Building a Self-Healing Frigate NVR with Kubernetes CronJobs

*Auto-restart your NVR when the Coral TPU gets stuck, with circuit breakers to prevent restart storms*

---

```
    +-----------------+     Health Check     +------------------+
    |  CronJob        |  ───────────────────>|  Frigate Pod     |
    |  Every 5 min    |                      |  Coral TPU       |
    +-----------------+                      |  AMD VAAPI       |
           │                                 +------------------+
           │ Unhealthy?                              │
           ▼                                         │
    +-----------------+     kubectl rollout   ───────┘
    |  Restart        |     restart deploy
    |  + Email Alert  |
    +-----------------+
```

## The Problem

Frigate with a Coral USB TPU occasionally gets into bad states:
- Coral inference slows from ~28ms to 500ms+
- Detection gets "stuck" and stops processing
- Recording backlogs pile up

The fix? Restart Frigate. But I don't want to babysit my NVR at 3am.

## The Solution: A Kubernetes CronJob Health Checker

A simple bash script running every 5 minutes that:
1. Checks Frigate API responsiveness
2. Monitors Coral TPU inference speed
3. Scans logs for known error patterns
4. Auto-restarts after consecutive failures
5. Rate-limits restarts to prevent storms
6. Sends email notifications on restart

## The Implementation

### CronJob Structure

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: frigate-health-checker
  namespace: frigate
spec:
  schedule: "*/5 * * * *"  # Every 5 minutes
  concurrencyPolicy: Forbid  # Never overlap
  jobTemplate:
    spec:
      ttlSecondsAfterFinished: 3600  # Cleanup after 1 hour
      template:
        spec:
          serviceAccountName: frigate-health-checker
          restartPolicy: OnFailure
          containers:
            - name: health-check
              image: dtzar/helm-kubectl:3.19
              command: ["/bin/bash", "-c"]
              args:
                - |
                  # Health check script here...
```

### Health Check Logic

The script checks three things:

**1. API Responsiveness**
```bash
FRIGATE_POD=$(kubectl get pods -n frigate -l app=frigate \
  -o jsonpath='{.items[0].metadata.name}')

STATS=$(kubectl exec -n frigate "$FRIGATE_POD" -- \
  curl -s --max-time 10 http://localhost:5000/api/stats)

if [[ -z "$STATS" || "$STATS" == "{}" ]]; then
  UNHEALTHY=true
  REASON="API unresponsive"
fi
```

**2. Coral Inference Speed**
```bash
INF_SPEED=$(echo "$STATS" | jq -r '.detectors.coral.inference_speed // 999')

if (( $(echo "$INF_SPEED > 100" | bc -l) )); then
  UNHEALTHY=true
  REASON="Coral inference ${INF_SPEED}ms > 100ms threshold"
fi
```

**3. Log Pattern Analysis**
```bash
LOGS=$(kubectl logs "$FRIGATE_POD" -n frigate --since=5m)

STUCK_CT=$(echo "$LOGS" | grep -c "Detection appears to be stuck" | head -1)
if [[ "$STUCK_CT" -gt 2 ]]; then
  UNHEALTHY=true
  REASON="Detection stuck ${STUCK_CT}x in 5 min"
fi
```

### The Circuit Breaker

This is the key safety feature. Without it, a persistent problem could cause restart loops:

```bash
MAX_RESTARTS_PER_HOUR=2

# Read restart history from ConfigMap
RESTART_TIMES=$(kubectl get cm frigate-health-state -n frigate \
  -o jsonpath='{.data.last_restart_times}')

# Count restarts in last hour
NOW=$(date +%s)
HOUR_AGO=$((NOW - 3600))
RECENT_RESTARTS=0

for ts in $(echo "$RESTART_TIMES" | tr ',' ' '); do
  if [[ $ts -gt $HOUR_AGO ]]; then
    RECENT_RESTARTS=$((RECENT_RESTARTS + 1))
  fi
done

if [[ $RECENT_RESTARTS -ge $MAX_RESTARTS_PER_HOUR ]]; then
  echo "CIRCUIT BREAKER: Already restarted ${RECENT_RESTARTS}x - manual intervention required"
  exit 0
fi
```

### Consecutive Failures Requirement

One bad check shouldn't trigger a restart. We require 2 consecutive failures:

```bash
CONSECUTIVE_FAILURES_REQUIRED=2

FAILURES=$(kubectl get cm frigate-health-state -n frigate \
  -o jsonpath='{.data.consecutive_failures}')

NEW_FAILURES=$((FAILURES + 1))

if [[ $NEW_FAILURES -lt $CONSECUTIVE_FAILURES_REQUIRED ]]; then
  echo "Waiting for confirmation (need $CONSECUTIVE_FAILURES_REQUIRED consecutive)"
  kubectl patch cm frigate-health-state -n frigate --type merge \
    -p "{\"data\":{\"consecutive_failures\":\"$NEW_FAILURES\"}}"
  exit 0
fi
```

### RBAC: Least Privilege

The CronJob needs specific permissions but shouldn't have cluster-admin:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: frigate-health-checker
  namespace: frigate
rules:
  # Read/update health state
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["frigate-health-state"]
    verbs: ["get", "patch"]

  # Find Frigate pod
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]

  # Execute curl inside pod
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]

  # Read logs for pattern analysis
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]

  # Restart deployment
  - apiGroups: ["apps"]
    resources: ["deployments"]
    resourceNames: ["frigate"]
    verbs: ["get", "patch"]
```

## Debugging Journey: Image Selection

### Attempt 1: `bitnami/kubectl:1.28`

```
Failed to pull image "bitnami/kubectl:1.28": not found
```

Bitnami doesn't have semver tags - only `latest` and SHA digests.

### Attempt 2: `lachlanevenson/k8s-kubectl:v1.25.4`

```
exec: "/bin/bash": no such file or directory
```

This image is Alpine-based with only `/bin/sh`, but my script uses bash features like `[[` and `(())`.

### Attempt 3: `dtzar/helm-kubectl:3.19`

This worked because it:
- Has bash (`apk add bash`)
- Has kubectl
- Has jq for JSON parsing
- Has curl
- Has versioned tags (not just `latest`)

**Lesson:** Always verify your container image has the tools your script needs.

## The grep -c Gotcha

Initial output showed syntax errors:

```
Detection stuck events: 0
0 (threshold: 2)
/bin/bash: line 60: [[: 0
0: syntax error in expression (error token is "0")
```

The problem: `echo "$LOGS" | grep -c "pattern"` was outputting `0\n0` (newline in output).

Fix:
```bash
# Before
STUCK_CT=$(echo "$LOGS" | grep -c "pattern" || echo 0)

# After
STUCK_CT=$(echo "$LOGS" | grep -c "pattern" 2>/dev/null | head -1 || echo 0)
STUCK_CT=${STUCK_CT:-0}
```

## GitOps Integration

The real gotcha was Flux reverting my manual `kubectl apply` changes:

```bash
# I ran this...
kubectl apply -f cronjob-health.yaml

# But the cluster showed the OLD image because Flux synced from git
kubectl get cronjob -o jsonpath='{..image}'
# bitnami/kubectl:1.28  <- Old value from last commit!
```

**Solution:** Commit and push changes, then force Flux reconciliation:

```bash
git add gitops/clusters/homelab/apps/frigate/*.yaml
git commit -m "fix: update health checker image"
git push

flux reconcile kustomization flux-system --with-source
```

## Healthy Output

When everything works:

```
=== Frigate Health Check: 2026-01-06 04:06:54 UTC ===
Current state: failures=0, restart_times=
Checking Frigate API...
API responded OK
Coral inference speed: 27.47ms (threshold: 100ms)
Checking recent logs...
Detection stuck events: 1 (threshold: 2)
Recording backlog events: 0 (threshold: 5)
Frigate is HEALTHY
configmap/frigate-health-state patched (no change)
```

## Email Notifications

When a restart happens, the CronJob sends an email with:
- What happened and when
- Which threshold was exceeded
- Context-specific next steps
- Links to Grafana and Frigate dashboards

```bash
case "$REASON" in
  *"inference"*)
    NEXT_STEPS="Check Coral TPU, USB errors, may need physical unplug/replug"
    ;;
  *"stuck"*)
    NEXT_STEPS="Check cameras, go2rtc streams, network connectivity"
    ;;
  *"backlog"*)
    NEXT_STEPS="Check disk space, recording permissions, clear old files"
    ;;
esac
```

## Summary

| Component | Purpose |
|-----------|---------|
| CronJob | Runs health check every 5 minutes |
| ConfigMap | Stores failure count and restart timestamps |
| RBAC Role | Least-privilege access for pod exec, logs, restart |
| Circuit Breaker | Max 2 restarts/hour to prevent storms |
| Consecutive Failures | Require 2 failures before restart |
| Email Notification | Alert with context and next steps |

## Files

- `gitops/clusters/homelab/apps/frigate/cronjob-health.yaml` - CronJob definition
- `gitops/clusters/homelab/apps/frigate/rbac-health-checker.yaml` - ServiceAccount + Role
- `gitops/clusters/homelab/apps/frigate/configmap-health-state.yaml` - State storage

## What's Next

- Add Prometheus metrics for health check results
- Grafana alerts when circuit breaker trips
- Extend pattern to other services (Ollama, go2rtc)
