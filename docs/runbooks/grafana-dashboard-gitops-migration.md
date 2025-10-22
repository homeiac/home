# Grafana Dashboard GitOps Migration

**Purpose**: Migrate manually imported Grafana dashboards to GitOps-managed ConfigMaps

**Last Updated**: October 22, 2025
**Status**: Implementation Guide

---

## Current State

- ✅ Grafana sidecar enabled (`grafana-sc-dashboard` container)
- ✅ Sidecar watches ConfigMaps with label `grafana_dashboard: "1"`
- ❌ Dashboards currently manually imported (not in Git)

**Manually Imported Dashboards:**
- NVIDIA DCGM Exporter (ID: 12239)
- Node Exporter Full (ID: 1860)
- Proxmox VE (ID: 10347)
- Kubernetes Persistent Volumes (ID: 13646)
- MetalLB (ID: 14127) - optional
- Traefik (ID: 17346) - optional
- Flux GitOps (ID: 16714) - optional

---

## Implementation Plan

### Phase 1: Directory Structure Setup

```bash
# Create dashboard directory structure
mkdir -p gitops/clusters/homelab/infrastructure/monitoring/dashboards
```

**Directory Layout:**
```
gitops/clusters/homelab/infrastructure/monitoring/
├── dashboards/
│   ├── kustomization.yaml
│   ├── nvidia-dcgm-exporter.yaml
│   ├── node-exporter-full.yaml
│   ├── proxmox-ve.yaml
│   ├── kubernetes-pvcs.yaml
│   ├── metallb.yaml
│   ├── traefik.yaml
│   └── flux-gitops.yaml
├── monitoring-values.yaml
├── helmrelease.yaml
└── kustomization.yaml
```

### Phase 2: Export Dashboard JSON

**For each dashboard in Grafana:**

1. Navigate to dashboard → **⚙️ Settings** (top right)
2. Click **JSON Model** (left sidebar)
3. Click **Copy to Clipboard**
4. Save to temporary file: `/tmp/dashboard-name.json`

**Export Commands:**
```bash
# Example for NVIDIA dashboard
# After copying JSON from Grafana UI:
cat > /tmp/nvidia-dcgm-exporter.json << 'EOF'
# PASTE JSON HERE
EOF
```

### Phase 3: Create Dashboard ConfigMaps

**Template Structure:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboard-<dashboard-name>
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
  annotations:
    grafana_folder: "Homelab"  # Optional: organize dashboards
data:
  <dashboard-name>.json: |-
    # PASTE EXPORTED JSON HERE (entire JSON object)
```

**Example: `nvidia-dcgm-exporter.yaml`**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboard-nvidia-dcgm-exporter
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
  annotations:
    grafana_folder: "Homelab"
data:
  nvidia-dcgm-exporter.json: |-
    {
      "annotations": {
        "list": [
          {
            "builtIn": 1,
            "datasource": "-- Grafana --",
            "enable": true,
            "hide": true,
            "iconColor": "rgba(0, 211, 255, 1)",
            "name": "Annotations & Alerts",
            "type": "dashboard"
          }
        ]
      },
      # ... rest of dashboard JSON
    }
```

**Critical Requirements:**
- ✅ Label `grafana_dashboard: "1"` (REQUIRED for sidecar detection)
- ✅ Namespace must be `monitoring`
- ✅ JSON must be valid (test with `jq` before committing)
- ✅ Indentation: 4 spaces for YAML, preserve JSON structure

### Phase 4: Create Dashboards Kustomization

**File: `gitops/clusters/homelab/infrastructure/monitoring/dashboards/kustomization.yaml`**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: monitoring
resources:
  - nvidia-dcgm-exporter.yaml
  - node-exporter-full.yaml
  - proxmox-ve.yaml
  - kubernetes-pvcs.yaml
  # Optional dashboards:
  # - metallb.yaml
  # - traefik.yaml
  # - flux-gitops.yaml
```

### Phase 5: Link to Monitoring Kustomization

**Edit: `gitops/clusters/homelab/infrastructure/monitoring/kustomization.yaml`**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: monitoring
resources:
  - namespace.yaml
  - helmrepository.yaml
  - helmrelease.yaml
  - prometheus-storage-class.yaml
  - grafana-ingress.yaml
  - cpu-alerting-rules.yaml
  - smtp-credentials.yaml
  - dashboards          # ADD THIS LINE
```

### Phase 6: Validate and Deploy

**Validation Commands:**

```bash
# 1. Validate JSON syntax
for file in gitops/clusters/homelab/infrastructure/monitoring/dashboards/*.yaml; do
  echo "Validating $file..."
  yq eval '.data[].json' "$file" | jq empty || echo "❌ Invalid JSON in $file"
done

# 2. Validate Kustomization
kubectl kustomize gitops/clusters/homelab/infrastructure/monitoring/dashboards

# 3. Dry-run apply
kubectl apply --dry-run=client -k gitops/clusters/homelab/infrastructure/monitoring/dashboards
```

**Deployment via GitOps:**

```bash
# Commit changes
git add gitops/clusters/homelab/infrastructure/monitoring/dashboards/
git add gitops/clusters/homelab/infrastructure/monitoring/kustomization.yaml

git commit -m "feat: add GitOps-managed Grafana dashboards

- Created dashboard ConfigMaps for NVIDIA, Node Exporter, Proxmox, K8s PVCs
- Dashboards automatically loaded via Grafana sidecar
- Organized in 'Homelab' folder
- Version controlled and persistent across pod restarts

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"

git push
```

**Flux Reconciliation:**

```bash
# Force Flux to reconcile
flux reconcile kustomization flux-system --with-source

# Watch for dashboard ConfigMaps
kubectl get configmaps -n monitoring -l grafana_dashboard=1 --watch

# Check Grafana sidecar logs
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana -c grafana-sc-dashboard --tail=50
```

### Phase 7: Verification

**Verify in Grafana UI:**

1. Open http://grafana.app.homelab
2. Navigate to **Dashboards** → **Browse**
3. Check for "Homelab" folder
4. Verify all dashboards appear

**Verify in Kubernetes:**

```bash
# List dashboard ConfigMaps
kubectl get configmaps -n monitoring -l grafana_dashboard=1

# Expected output:
# NAME                                      DATA   AGE
# grafana-dashboard-nvidia-dcgm-exporter    1      5m
# grafana-dashboard-node-exporter-full      1      5m
# grafana-dashboard-proxmox-ve              1      5m
# grafana-dashboard-kubernetes-pvcs         1      5m
```

**Test Dashboard Persistence:**

```bash
# Restart Grafana pod
kubectl rollout restart deployment -n monitoring kube-prometheus-stack-grafana

# Wait for pod ready
kubectl wait --for=condition=ready pod -n monitoring -l app.kubernetes.io/name=grafana --timeout=120s

# Verify dashboards still present (should auto-reload from ConfigMaps)
```

---

## Dashboard JSON Extraction Helper Script

**Optional: Automate JSON extraction from Grafana API**

```bash
#!/bin/bash
# File: scripts/export-grafana-dashboards.sh

GRAFANA_URL="http://grafana.app.homelab"
GRAFANA_USER="admin"
GRAFANA_PASS="admin"

# Get dashboard UIDs
DASHBOARD_UIDS=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" \
  "$GRAFANA_URL/api/search?type=dash-db" | jq -r '.[].uid')

for UID in $DASHBOARD_UIDS; do
  DASHBOARD_JSON=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" \
    "$GRAFANA_URL/api/dashboards/uid/$UID" | jq '.dashboard')

  TITLE=$(echo "$DASHBOARD_JSON" | jq -r '.title' | tr ' ' '-' | tr '[:upper:]' '[:lower:]')

  echo "Exporting: $TITLE (UID: $UID)"
  echo "$DASHBOARD_JSON" > "/tmp/grafana-dashboard-${TITLE}.json"
done

echo "✅ Dashboards exported to /tmp/grafana-dashboard-*.json"
```

---

## Cleanup: Remove Manually Imported Dashboards

**After GitOps dashboards are confirmed working:**

1. In Grafana UI, delete the manually imported dashboards
2. Restart Grafana pod to clear cache
3. Verify dashboards reload from ConfigMaps

**Why:** Prevents duplicate dashboards (manual + GitOps versions)

---

## Troubleshooting

### Dashboard Not Appearing

**Check sidecar logs:**
```bash
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana -c grafana-sc-dashboard --tail=100
```

**Common issues:**
- Missing label `grafana_dashboard: "1"`
- Wrong namespace (must be `monitoring`)
- Invalid JSON syntax
- Sidecar not watching correct namespace

### Dashboard Shows But Doesn't Update

**Force sidecar reload:**
```bash
# Delete and recreate ConfigMap
kubectl delete configmap -n monitoring grafana-dashboard-<name>
kubectl apply -f gitops/clusters/homelab/infrastructure/monitoring/dashboards/<name>.yaml

# Check sidecar detected change
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana -c grafana-sc-dashboard --tail=20
```

### JSON Syntax Errors

**Validate JSON:**
```bash
yq eval '.data."dashboard-name.json"' dashboard-configmap.yaml | jq empty
```

**Common fixes:**
- Remove trailing commas in JSON arrays/objects
- Escape special characters in strings
- Ensure proper indentation (4 spaces for YAML, preserve JSON)

---

## Benefits of GitOps Dashboards

- ✅ **Version Control**: Track dashboard changes in Git
- ✅ **Reproducibility**: Dashboards automatically restored on Grafana pod restart
- ✅ **Auditability**: Git history shows who changed what and when
- ✅ **Disaster Recovery**: Full dashboard restore from Git repository
- ✅ **Multi-Environment**: Easy to replicate dashboards across clusters
- ✅ **Collaboration**: Team reviews via pull requests

---

## Related Documentation

- [Monitoring Setup Guide](../md/monitoring-alerting-guide.md)
- [Flux GitOps Configuration](../../gitops/clusters/homelab/README.md)
- [Grafana Dashboard Sidecar Docs](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack#grafana-sidecar-for-dashboards)

---

## Tags

grafana, grafanna, dashboards, gitops, configmap, kubernetes, k8s, kubernettes, kube-prometheus-stack, monitoring, sidecar, automation, infrastructure-as-code

---

## Implementation Checklist

- [ ] Create `dashboards/` directory structure
- [ ] Export NVIDIA DCGM dashboard JSON from Grafana
- [ ] Export Node Exporter Full dashboard JSON
- [ ] Export Proxmox VE dashboard JSON
- [ ] Export Kubernetes PVCs dashboard JSON
- [ ] Create ConfigMap YAML files for each dashboard
- [ ] Create `dashboards/kustomization.yaml`
- [ ] Update `monitoring/kustomization.yaml` to include dashboards
- [ ] Validate JSON syntax in all ConfigMaps
- [ ] Validate Kustomization builds correctly
- [ ] Commit to Git and push
- [ ] Verify Flux reconciles changes
- [ ] Verify dashboards appear in Grafana UI
- [ ] Test dashboard persistence (restart Grafana pod)
- [ ] Delete manually imported dashboards
- [ ] Document any custom dashboard modifications in Git commit messages
