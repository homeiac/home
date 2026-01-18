# Frigate Health Checker

Automated health monitoring and restart capability for Frigate NVR running in Kubernetes.

## Features

- **API Health Monitoring**: Checks Frigate API responsiveness
- **Coral TPU Monitoring**: Detects slow inference speeds
- **Log Analysis**: Identifies stuck detection and recording backlog issues
- **Smart Restart Logic**:
  - Requires consecutive failures before restart
  - Circuit breaker prevents restart storms
  - Checks node availability before restart
- **Email Notifications**: Alerts with diagnostics and next steps
- **State Persistence**: Uses ConfigMap to track health state

## Installation

### Prerequisites

- Python 3.11+
- Poetry
- Kubernetes cluster with Frigate deployed

### Development Setup

```bash
cd apps/frigate-health-checker
poetry install
```

### Running Tests

```bash
# All tests with coverage
poetry run pytest

# Specific test file
poetry run pytest tests/test_health_checker.py -v

# With coverage report
poetry run pytest --cov-report=html
```

### Type Checking

```bash
poetry run mypy src/
```

### Linting

```bash
poetry run ruff check src/ tests/
poetry run ruff format src/ tests/
```

## Configuration

All settings are configured via environment variables with the `FRIGATE_HC_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `FRIGATE_HC_NAMESPACE` | `frigate` | Kubernetes namespace |
| `FRIGATE_HC_DEPLOYMENT_NAME` | `frigate` | Deployment to restart |
| `FRIGATE_HC_INFERENCE_THRESHOLD_MS` | `100` | Max acceptable Coral inference speed |
| `FRIGATE_HC_STUCK_DETECTION_THRESHOLD` | `2` | Max stuck events in window |
| `FRIGATE_HC_BACKLOG_THRESHOLD` | `5` | Max backlog events in window |
| `FRIGATE_HC_CONSECUTIVE_FAILURES_REQUIRED` | `2` | Failures before restart |
| `FRIGATE_HC_MAX_RESTARTS_PER_HOUR` | `2` | Circuit breaker limit |
| `FRIGATE_HC_SMTP_USER` | - | SMTP username for alerts |
| `FRIGATE_HC_SMTP_PASSWORD` | - | SMTP password |
| `FRIGATE_HC_ALERT_EMAIL` | - | Email recipient for alerts |

## Kubernetes Deployment

### CronJob

The health checker runs as a Kubernetes CronJob every 5 minutes:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: frigate-health-checker
  namespace: frigate
spec:
  schedule: "*/5 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: health-check
              image: ghcr.io/homeiac/frigate-health-checker:latest
              env:
                - name: FRIGATE_HC_NAMESPACE
                  value: "frigate"
```

### Required RBAC

The health checker needs permissions to:
- Get/list pods in the Frigate namespace
- Exec into Frigate pods
- Get/patch ConfigMaps
- Restart deployments
- Read node status

See `rbac-health-checker.yaml` for the full Role definition.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CronJob (every 5 min)                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐   ┌─────────────────┐   ┌──────────────┐  │
│  │HealthChecker │ → │ RestartManager  │ → │ EmailNotifier│  │
│  └──────────────┘   └─────────────────┘   └──────────────┘  │
│         │                   │                               │
│         ▼                   ▼                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              KubernetesClient                         │   │
│  │  - Get pod status                                     │   │
│  │  - Exec curl for API check                            │   │
│  │  - Get pod logs                                       │   │
│  │  - Patch ConfigMap                                    │   │
│  │  - Restart deployment                                 │   │
│  │  - Check node readiness                               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Health Check Flow

1. **Check Pod Exists**: Verify Frigate pod is running
2. **Check API**: Call `/api/stats` endpoint
3. **Check Inference Speed**: Compare Coral speed to threshold
4. **Analyze Logs**: Look for stuck detection / backlog patterns
5. **Evaluate Restart**:
   - Check consecutive failures
   - Check circuit breaker
   - Check node availability
6. **Execute Restart** (if needed)
7. **Send Notification** (once per incident)

## Development

### Adding New Health Checks

1. Add check method to `HealthChecker` class
2. Add reason to `UnhealthyReason` enum
3. Update `_get_next_steps()` in notifier
4. Add unit tests

### Building Docker Image

```bash
docker build -t frigate-health-checker:local .
docker run --rm frigate-health-checker:local --help
```

## License

MIT
