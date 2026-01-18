# Frigate Health Checker Runbook

## Overview

Python-based health checker that monitors Frigate NVR and automatically restarts the deployment when unhealthy conditions are detected.

**Location**: `apps/frigate-health-checker/`
**Deployment**: `gitops/clusters/homelab/apps/frigate/cronjob-health-python.yaml`
**Schedule**: Every 5 minutes via CronJob

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   CronJob       │────▶│  Health Checker │────▶│  Frigate Pod    │
│   (5 min)       │     │  Python App     │     │  (curl /api/stats)
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  ConfigMap      │
                        │  (state store)  │
                        └─────────────────┘
```

## Health Checks Performed

1. **Pod exists** - Frigate pod is running
2. **API responsive** - `/api/stats` returns valid JSON
3. **Coral inference speed** - < 100ms threshold (configurable)
4. **Detection stuck events** - Count in log window < threshold
5. **Recording backlog events** - Count in log window < threshold

## Safeguards (Alert Storm Prevention)

| Safeguard | Default | Purpose |
|-----------|---------|---------|
| `consecutive_failures_required` | 2 | Requires N consecutive failures before action |
| `max_restarts_per_hour` | 3 | Circuit breaker to prevent restart loops |
| `alert_sent_for_incident` | flag | Prevents duplicate alerts for same incident |
| Node readiness check | - | Skips restart if node is NotReady |

## Configuration

Environment variables in CronJob:

```yaml
env:
  - name: NAMESPACE
    value: "frigate"
  - name: POD_LABEL_SELECTOR
    value: "app.kubernetes.io/name=frigate"
  - name: DEPLOYMENT_NAME
    value: "frigate"
  - name: CONFIGMAP_NAME
    value: "frigate-health-state"
  - name: INFERENCE_THRESHOLD_MS
    value: "100"
  - name: LOG_WINDOW_MINUTES
    value: "10"
```

## Debugging

### Check CronJob status

```bash
KUBECONFIG=~/kubeconfig kubectl get cronjob frigate-health-checker -n frigate
```

### View recent job runs

```bash
KUBECONFIG=~/kubeconfig kubectl get jobs -n frigate -l app=frigate-health-checker --sort-by=.metadata.creationTimestamp | tail -5
```

### Check health checker logs

```bash
# Latest job
KUBECONFIG=~/kubeconfig kubectl logs -n frigate -l app=frigate-health-checker --tail=50

# Specific job
KUBECONFIG=~/kubeconfig kubectl logs -n frigate job/frigate-health-checker-XXXXX
```

### Manual test run

```bash
KUBECONFIG=~/kubeconfig kubectl create job --from=cronjob/frigate-health-checker -n frigate test-manual-$(date +%s)
```

### Check health state ConfigMap

```bash
KUBECONFIG=~/kubeconfig kubectl get configmap frigate-health-state -n frigate -o yaml
```

### Debug pod for testing

```bash
KUBECONFIG=~/kubeconfig kubectl run debug-exec -n frigate \
  --image=ghcr.io/homeiac/frigate-health-checker:latest \
  --serviceaccount=frigate-health-checker \
  --rm -it --restart=Never -- /bin/sh
```

## Known Issues

### Kubernetes Python Client JSON Bug

**Issue**: `kubernetes` Python client `stream()` function with `_preload_content=True` (default) converts JSON to Python dict syntax (single quotes).

**Symptom**: JSON parsing fails with `Expecting property name enclosed in double quotes`.

**Fix**: Use `_preload_content=False` and read stdout separately:

```python
ws_client = stream(..., _preload_content=False)
ws_client.run_forever(timeout=timeout)
stdout = ws_client.read_stdout()
```

**Reference**: https://github.com/kubernetes-client/python/issues/1032

## RBAC Requirements

The health checker needs these permissions (`rbac-health-checker.yaml`):

| Resource | Verbs | Purpose |
|----------|-------|---------|
| configmaps (frigate-health-state) | get, patch | State persistence |
| pods | get, list | Find Frigate pod |
| pods/exec | create, get | Exec curl command |
| pods/log | get | Read Frigate logs |
| deployments (frigate) | get, patch | Trigger restart |
| nodes | get | Check node readiness |

---

# Shift-Left Testing Guide

## The Problem

Pushing code to GitHub and waiting for CI to fail is slow and frustrating:
- Each CI run takes 2-3 minutes minimum
- Debugging requires reading CI logs, not local errors
- Iterating on fixes burns time and commits

## Local Testing Workflow

### 1. Format and Lint First

```bash
cd apps/frigate-health-checker

# Format code (fixes issues automatically)
poetry run ruff format src/ tests/

# Check for lint errors
poetry run ruff check src/ tests/

# Type checking
poetry run mypy src/
```

### 2. Run Tests Locally

```bash
# All tests with coverage
poetry run pytest

# Specific test file
poetry run pytest tests/test_health_checker.py -v

# Single test
poetry run pytest tests/test_health_checker.py::test_check_health_returns_healthy -v
```

### 3. Build Docker Image Locally

```bash
# Build for local testing
docker build -t frigate-health-checker:local .

# Test the image runs
docker run --rm frigate-health-checker:local python -c "from frigate_health_checker import cli; print('OK')"
```

### 4. Test in Cluster with Debug Pod

**CRITICAL**: Test Kubernetes client behavior in-cluster before pushing!

```bash
# Create debug pod with service account
KUBECONFIG=~/kubeconfig kubectl run debug-exec -n frigate \
  --image=ghcr.io/homeiac/frigate-health-checker:latest \
  --serviceaccount=frigate-health-checker \
  --rm -it --restart=Never -- /bin/sh

# Inside the pod, test Python code interactively
python3 -c "
from kubernetes import client, config
from kubernetes.stream import stream

config.load_incluster_config()
v1 = client.CoreV1Api()

# Test exec with _preload_content=False
ws = stream(
    v1.connect_get_namespaced_pod_exec,
    'frigate-0',  # adjust pod name
    'frigate',
    command=['curl', '-s', 'http://localhost:5000/api/stats'],
    stdout=True, stderr=True, stdin=False, tty=False,
    _preload_content=False
)
ws.run_forever(timeout=10)
print(repr(ws.read_stdout()[:100]))
"
```

### 5. Pre-Push Checklist

```bash
#!/bin/bash
# scripts/frigate-health-checker/pre-push-check.sh

set -e
cd apps/frigate-health-checker

echo "=== Formatting ==="
poetry run ruff format src/ tests/

echo "=== Linting ==="
poetry run ruff check src/ tests/

echo "=== Type Checking ==="
poetry run mypy src/

echo "=== Tests ==="
poetry run pytest

echo "=== Docker Build ==="
docker build -t frigate-health-checker:local .

echo "✅ All checks passed - safe to push"
```

## When to Use Debug Pod

Use a debug pod when:

1. **Testing Kubernetes client behavior** - RBAC, exec, logs
2. **Debugging JSON/output parsing** - See actual bytes returned
3. **Verifying service account permissions** - Before updating RBAC
4. **Testing against real Frigate** - API responses, stats format

## CI Should Be Verification, Not Discovery

| Phase | What to Catch |
|-------|---------------|
| Local format/lint | Style issues, imports |
| Local tests | Logic bugs, regressions |
| Local Docker build | Missing files, dependencies |
| Debug pod | K8s client quirks, RBAC, real API |
| CI | Final verification, multi-arch build |

## Quick Reference

```bash
# One-liner: format, lint, test
cd apps/frigate-health-checker && poetry run ruff format src/ tests/ && poetry run ruff check src/ tests/ && poetry run mypy src/ && poetry run pytest

# Build and verify Docker
docker build -t frigate-health-checker:local . && docker run --rm frigate-health-checker:local python -c "import frigate_health_checker; print('OK')"

# Debug pod
KUBECONFIG=~/kubeconfig kubectl run debug-exec -n frigate --image=ghcr.io/homeiac/frigate-health-checker:latest --serviceaccount=frigate-health-checker --rm -it --restart=Never -- /bin/sh

# Clean up debug pod (if detached)
KUBECONFIG=~/kubeconfig kubectl delete pod debug-exec -n frigate
```
