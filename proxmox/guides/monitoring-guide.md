# Production-Ready Monitoring Setup

This guide shows how to deploy Prometheus and Grafana using the
`kube-prometheus-stack` Helm chart. The default values live in
`gitops/clusters/homelab/infrastructure/monitoring/monitoring-values.yaml`.

**📧 For Email Alerting Setup**: See [Monitoring and Alerting Guide](monitoring-alerting-guide.md)

## 1. Deploy Prometheus & Grafana

Install the `kube-prometheus-stack` chart and expose Grafana on NodePort `30080`:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prom-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace
```

## 2. Storage Configuration

Prometheus generates a large write load and requires significant disk space for time-series data.
Both Prometheus and Grafana are configured to run on `k3s-vm-still-fawn` which has access to a 2TB drive.

### Prometheus Storage (2TB Drive)
Prometheus uses a hostPath volume pointing directly to the 2TB drive at `/mnt/smb_data/prometheus`:

```yaml
# gitops/clusters/homelab/infrastructure/monitoring/monitoring-values.yaml
prometheus:
  prometheusSpec:
    retention: 30d
    nodeSelector:
      kubernetes.io/hostname: k3s-vm-still-fawn
    volumes:
      - name: prometheus-storage
        hostPath:
          path: /mnt/smb_data/prometheus
          type: Directory
    volumeMounts:
      - name: prometheus-storage
        mountPath: /prometheus
    storage:
      disableMountSubPath: true
```

### Grafana Storage (Local Path)
Grafana uses local-path storage with node affinity:

```yaml
grafana:
  persistence:
    enabled: true
    accessModes:
      - ReadWriteOnce
    size: 10Gi
    storageClassName: local-path
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 100
          preference:
            matchExpressions:
              - key: kubernetes.io/hostname
                operator: In
                values:
                  - k3s-vm-still-fawn
```

This configuration ensures Prometheus data is stored on the large 2TB drive while keeping Grafana's smaller configuration data on local storage.

## 3. Install and Configure Exporters

### Node Exporter

- Run as a systemd service on Proxmox hosts and as a DaemonSet on k3s.
  - Metrics available on port `9100`.

### Proxmox PVE Exporter

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
- **Proxmox via Prometheus** (10347) — recommended for Proxmox metrics
- **Do not import** **Proxmox VE Node** (10048) as it requires InfluxDB
- (Optional) **Cluster Summary** (10049)

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

## Deploy with Flux

The monitoring stack is now managed through Flux. The manifests live under
`gitops/clusters/homelab/infrastructure/monitoring`. Flux applies the
`kube-prometheus-stack` chart using the values from
`gitops/clusters/homelab/infrastructure/monitoring/monitoring-values.yaml`,
ensuring Prometheus data is stored on the 2TB drive and existing Grafana dashboards remain intact.
