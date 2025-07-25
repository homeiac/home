# Monitoring and Alerting Guide

## Overview
This guide covers setting up email alerting for your K3s cluster using Prometheus and Alertmanager. The system monitors various metrics and sends email notifications when thresholds are exceeded.

## Storage Configuration

### Prometheus Storage Migration (Completed)
Prometheus has been migrated to use high-capacity storage backed by the 20TB ZFS pool:

- **Storage Class**: `prometheus-2tb-storage` (1TB capacity)
- **Storage Path**: `/mnt/smb_data/prometheus` (backed by 20TB ZFS pool)  
- **Node Affinity**: `k3s-vm-still-fawn` (GPU node with RTX 3070)
- **PersistentVolume**: `prometheus-2tb-pv` (1000Gi, Retain policy)

```yaml
# Current storage configuration
storageSpec:
  volumeClaimTemplate:
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: prometheus-2tb-storage
      resources:
        requests:
          storage: 500Gi  # Using 500GB of 1TB available
```

The storage is mounted from the still-fawn node's 20TB ZFS pool, providing ample space for long-term metrics retention with 30-day raw data retention configured.

## Current Alerting Rules

### CPU Monitoring
- **K3sNodeHighCPU**: Triggers when CPU usage > 90% for 1 hour
- **K3sNodeCriticalCPU**: Triggers when CPU usage > 95% for 1 hour

## Email Alert Setup

### Prerequisites
1. **Gmail Setup (Recommended)**:
   - Enable 2-Factor Authentication: https://myaccount.google.com/security
   - Generate App Password: https://myaccount.google.com/apppasswords
   - Select "Mail" → "Kubernetes Alertmanager"
   - Copy the 16-character password (remove spaces)

2. **Yahoo Alternative**:
   - Go to Yahoo Account Security settings
   - Enable 2-step verification if required
   - Generate app password for mail applications

### Configuration Steps

1. **Update Email Settings**:
   ```bash
   # Edit monitoring values
   vim gitops/clusters/homelab/infrastructure/monitoring/monitoring-values.yaml
   
   # Replace "your-email@gmail.com" with your actual email
   # For Yahoo: change smtp_smarthost to 'smtp.mail.yahoo.com:587'
   ```

2. **Create SMTP Secret**:
   ```bash
   kubectl create secret generic alertmanager-smtp-secret \
     --from-literal=smtp-password='YOUR_16_CHAR_APP_PASSWORD' \
     -n monitoring
   ```

3. **Verify Setup**:
   ```bash
   # Check secret exists
   kubectl get secret alertmanager-smtp-secret -n monitoring
   
   # Check Alertmanager pods
   kubectl get pods -n monitoring | grep alertmanager
   
   # View Alertmanager logs
   kubectl logs -n monitoring -l app.kubernetes.io/name=alertmanager
   ```

4. **Test Alerting** (Optional):
   ```bash
   kubectl patch prometheusrule k3s-cpu-alerts -n monitoring --type='merge' \
     -p='{"spec":{"groups":[{"name":"k3s-node-cpu","rules":[{"alert":"TestAlert","expr":"up","for":"0s","labels":{"severity":"critical"},"annotations":{"summary":"Test alert - you can ignore this"}}]}]}}'
   ```

## Adding New Alert Rules

### Example: Disk Space Monitoring

1. **Create Disk Alerting Rules**:
   ```yaml
   # File: gitops/clusters/homelab/infrastructure/monitoring/disk-alerting-rules.yaml
   apiVersion: monitoring.coreos.com/v1
   kind: PrometheusRule
   metadata:
     name: k3s-disk-alerts
     namespace: monitoring
     labels:
       app: kube-prometheus-stack
       release: kube-prometheus-stack
   spec:
     groups:
       - name: k3s-node-disk
         rules:
           - alert: K3sNodeDiskSpaceLow
             expr: (node_filesystem_avail_bytes{fstype!="tmpfs"} / node_filesystem_size_bytes{fstype!="tmpfs"} * 100) < 20
             for: 30m
             labels:
               severity: warning
               service: k3s-cluster
             annotations:
               summary: "K3s node {{ $labels.instance }} disk space low"
               description: "K3s node {{ $labels.instance }} has only {{ $value | humanizePercentage }} disk space remaining on {{ $labels.mountpoint }}."
               
           - alert: K3sNodeDiskSpaceCritical
             expr: (node_filesystem_avail_bytes{fstype!="tmpfs"} / node_filesystem_size_bytes{fstype!="tmpfs"} * 100) < 10
             for: 15m
             labels:
               severity: critical
               service: k3s-cluster
             annotations:
               summary: "K3s node {{ $labels.instance }} disk space critical"
               description: "K3s node {{ $labels.instance }} has only {{ $value | humanizePercentage }} disk space remaining on {{ $labels.mountpoint }}. Immediate action required."
   ```

2. **Add to Kustomization**:
   ```yaml
   # File: gitops/clusters/homelab/infrastructure/monitoring/kustomization.yaml
   resources:
     - namespace.yaml
     - helmrepository.yaml
     - helmrelease.yaml
     - cpu-alerting-rules.yaml
     - disk-alerting-rules.yaml  # Add this line
   ```

3. **Commit and Deploy**:
   ```bash
   git add .
   git commit -m "Add disk space monitoring alerts"
   git push
   # Flux will automatically deploy the new rules
   ```

### Example: Memory Usage Monitoring

```yaml
# File: gitops/clusters/homelab/infrastructure/monitoring/memory-alerting-rules.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: k3s-memory-alerts
  namespace: monitoring
  labels:
    app: kube-prometheus-stack
    release: kube-prometheus-stack
spec:
  groups:
    - name: k3s-node-memory
      rules:
        - alert: K3sNodeMemoryHigh
          expr: (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 85
          for: 30m
          labels:
            severity: warning
            service: k3s-cluster
          annotations:
            summary: "K3s node {{ $labels.instance }} memory usage high"
            description: "K3s node {{ $labels.instance }} memory usage is {{ $value | humanizePercentage }}."
```

## Common Alert Expressions

### System Metrics
```promql
# CPU Usage
(100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100))

# Memory Usage
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100

# Disk Usage
(1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)) * 100

# Load Average
node_load1 > 2

# Network Errors
rate(node_network_receive_errs_total[5m]) > 0
```

### Kubernetes Metrics
```promql
# Pod Restarts
increase(kube_pod_container_status_restarts_total[1h]) > 5

# Node Not Ready
kube_node_status_condition{condition="Ready",status="true"} == 0

# Pod CPU Throttling
rate(container_cpu_cfs_throttled_seconds_total[5m]) > 0.1
```

## Alert Rule Structure

```yaml
- alert: AlertName
  expr: prometheus_query > threshold
  for: duration                    # How long condition must be true
  labels:
    severity: warning|critical     # Alert severity
    service: service-name         # Service affected
  annotations:
    summary: "Brief description"   # Email subject line
    description: "Detailed info"   # Email body content
    runbook_url: "link-to-docs"   # Optional documentation link
```

## Troubleshooting

### Check Alert Status
```bash
# View active alerts in Prometheus
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
# Open http://localhost:9090/alerts

# View Alertmanager status
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093
# Open http://localhost:9093
```

### Common Issues
1. **Emails not sending**: Check SMTP secret and credentials
2. **Alerts not firing**: Verify metric names and expressions
3. **Alerts firing too often**: Increase `for` duration
4. **Missing labels**: Ensure PrometheusRule has correct labels for discovery

### Log Checking
```bash
# Alertmanager logs
kubectl logs -n monitoring -l app.kubernetes.io/name=alertmanager

# Prometheus logs
kubectl logs -n monitoring -l app.kubernetes.io/name=prometheus
```

## Best Practices

1. **Alert Fatigue**: Don't alert on everything, focus on actionable items
2. **Appropriate Thresholds**: Set realistic thresholds based on your environment
3. **Proper For Duration**: Use appropriate time windows to avoid false positives
4. **Clear Descriptions**: Include context and suggested actions in alert descriptions
5. **Severity Levels**: Use consistent severity labeling (warning, critical)
6. **Testing**: Test new alerts before deploying to production
7. **Documentation**: Keep runbooks updated for alert resolution steps

## Security Considerations

- Never commit SMTP passwords to git
- Use app passwords instead of account passwords
- Regularly rotate SMTP credentials
- Limit email recipients to necessary personnel
- Consider using dedicated monitoring email accounts