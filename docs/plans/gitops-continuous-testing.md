# Continuous Testing for Homelab GitOps

## Problem
Traefik was down for 5+ days because a Helm chart breaking change (`expose: true` → `expose: { default: true }`) went undetected. No alerts, no pre-deploy validation.

---

## COMPLETED

### Email Alerting (Reactive)
- ✅ Grafana SMTP configured (Yahoo)
- ✅ Test email sent successfully
- ✅ `homelab-email` contact point created
- ✅ Notification policy routes all alerts to email
- ✅ ServiceMonitor for Flux controllers deployed
- ✅ PrometheusRule for Flux failures deployed
- ✅ Flux Grafana dashboards imported (14936, 16714)

**Scripts created:**
- `scripts/monitoring/test-grafana-email.sh`
- `scripts/monitoring/configure-email-alerts.sh`
- `scripts/monitoring/import-flux-dashboard.sh`

---

## TODO

### 1. Flux Grafana Dashboards

**Official dashboards from [Grafana Labs](https://grafana.com/grafana/dashboards/):**
- [Flux Cluster Stats (14936)](https://grafana.com/grafana/dashboards/14936-flux-cluster-stats/) - Overall Flux health
- [Flux2 (16714)](https://grafana.com/grafana/dashboards/16714-flux2/) - Improved version with more panels

**Alternative: Azure dashboards**
- [fluxv2-grafana-dashboards](https://github.com/Azure/fluxv2-grafana-dashboards) - Application Deployments Dashboard

**Implementation:**
```bash
# Import via Grafana UI: Dashboards → Import → Enter ID: 14936
# Or add to GitOps:
gitops/clusters/homelab/infrastructure/monitoring/flux-dashboard-configmap.yaml
```

### 2. Pre-commit Hooks (Preventive)

**File:** `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/gruntwork-io/pre-commit
    rev: v0.1.23
    hooks:
      - id: helmlint

  - repo: https://github.com/yannh/kubeconform
    rev: v0.6.7
    hooks:
      - id: kubeconform
        args: ['-strict', '-ignore-missing-schemas']

  - repo: https://github.com/adrienverge/yamllint
    rev: v1.35.1
    hooks:
      - id: yamllint
        args: ['-d', '{extends: relaxed, rules: {line-length: disable}}']
```

**Setup:**
```bash
pip install pre-commit
pre-commit install
```

### 3. GitHub Actions CI (Gate)

**File:** `.github/workflows/validate-gitops.yml`

```yaml
name: Validate GitOps
on:
  push:
    branches: [master]
    paths: ['gitops/**', 'k8s/**']
  pull_request:
    paths: ['gitops/**', 'k8s/**']

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Kustomize
        uses: fluxcd/pkg/actions/kustomize@main

      - name: Validate Kustomize Build
        run: kustomize build gitops/clusters/homelab --enable-helm > /dev/null

      - name: Install kubeconform
        run: |
          curl -sL https://github.com/yannh/kubeconform/releases/download/v0.6.7/kubeconform-linux-amd64.tar.gz | tar xz
          sudo mv kubeconform /usr/local/bin/

      - name: Validate Manifests
        run: |
          kustomize build gitops/clusters/homelab --enable-helm | \
            kubeconform -strict -ignore-missing-schemas -summary
```

---

## Flux Metrics (FIXED)

Using `controller_runtime_reconcile_errors_total` instead of `gotk_reconcile_condition` (which requires kube-state-metrics CRD support).

**Current ServiceMonitor scrapes:**
- flux-metrics (helm-controller) ✅
- flux-source-metrics (source-controller) ✅
- flux-kustomize-metrics (kustomize-controller) ✅

---

## Sources
- [Flux Prometheus Metrics](https://fluxcd.io/flux/monitoring/metrics/)
- [Flux Cluster Stats Dashboard](https://grafana.com/grafana/dashboards/14936-flux-cluster-stats/)
- [kubeconform](https://github.com/yannh/kubeconform)
- [flux2-monitoring-example](https://github.com/fluxcd/flux2-monitoring-example)
