# Production-Ready Monitoring Setup

This guide describes how to deploy a Prometheus and Grafana monitoring stack on a k3s + Proxmox homelab. The Helm chart values are stored in `k8s/monitoring-values.yaml`.

## 1. Deploy Prometheus & Grafana

Install the `kube-prometheus-stack` chart and expose Grafana on NodePort `30080`:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prom-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace
```

## 2. Enable Persistence with local-path

Prometheus writes heavily, so use node local storage while Grafana can remain on Longhorn.

```yaml
# k8s/monitoring-values.yaml

grafana:
  persistence:
    enabled: true
    accessModes:
      - ReadWriteOnce
    size: 10Gi
    storageClassName: longhorn

prometheus:
  prometheusSpec:
    retention: 30d
    storageSpec:
      volumeClaimTemplate:
        spec:
          accessModes: ["ReadWriteOnce"]
          storageClassName: local-path
          resources:
            requests:
              storage: 100Gi
```

Apply the chart with these values to persist data locally.

## 3. Install and Configure Exporters

**Node Exporter**
- Run as a systemd service on Proxmox hosts and as a DaemonSet on k3s.
- Metrics available on port `9100`.

**Proxmox PVE Exporter**
- Install via `pipx` to `/usr/local/bin/pve_exporter`.
- Configure `/etc/pve_exporter/config.yaml`:

```yaml
default:
    user: root@pam
    token_name: prometheus
    token_value: <YOUR_TOKEN>
    verify_ssl: false
```

- Start with systemd using `--config.file` and expose metrics on `9221` at path `/pve`.

## 4. Configure Prometheus Scrape Jobs

Add the exporters to `additionalScrapeConfigs` in `monitoring-values.yaml`:

```yaml
- job_name: proxmox-node-exporter
  static_configs:
    - targets:
      - 192.168.4.122:9100
      - …
- job_name: proxmox-pve-exporter
  metrics_path: /pve
  static_configs:
    - targets:
      - 192.168.4.122:9221
```

Update the release:

```bash
helm upgrade prom-stack prometheus-community/kube-prometheus-stack \
  -n monitoring -f monitoring-values.yaml
```

## 5. Import Grafana Dashboards

- **Node Exporter Full** (1860)
- **SMART / Disk Health** (13654)
- **Proxmox via Prometheus** (10347)
- (Optional) **Proxmox VE Node** (10048) and **Cluster Summary** (10049)

## 6. Set up Alerting

Define PrometheusRules in `monitoring-values.yaml`:

```yaml
additionalPrometheusRules:
  - name: host-alerts
    groups:
      - name: disk-usage
        rules:
          - alert: HighDiskUsage
            expr: (pve_disk_usage_bytes{id=~"storage/.+"} / pve_disk_size_bytes{id=~"storage/.+"}) > 0.80
            for: 10m
      - name: cpu-temp
        rules:
          - alert: HighCPUTemperature
            expr: node_hwmon_temp_celsius{sensor="temp1"} > 85
            for: 5m
```

## 7. GPU Monitoring (optional)

- Deploy NVIDIA DCGM Exporter as a DaemonSet (port `9400`).
- Create a `ServiceMonitor` for `app=dcgm-exporter`.
- Import the NVIDIA GPU dashboard (12256).

## 8. Next Steps

- Configure notification channels (Slack, email, PagerDuty).
- Secure access via ingress with TLS or Tailscale.
- Add nightly drift checks via CI/cron.
- Create recording rules for rollups and downsampling.
- Integrate Thanos for long-term storage.
