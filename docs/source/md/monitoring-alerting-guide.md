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

### CPU Monitoring (`cpu-alerting-rules.yaml`)
- **K3sNodeHighCPU**: Triggers when CPU usage > 90% for 1 hour
- **K3sNodeCriticalCPU**: Triggers when CPU usage > 95% for 1 hour

### Essential Homelab Alerts (`essential-alerting-rules.yaml`)
Minimal alert set designed to prevent alert fatigue:

- **NodeDown**: Node completely unreachable for 10+ minutes
- **DiskAlmostFull**: Root filesystem > 98% full for 1+ hour  
- **MemoryCritical**: Memory usage > 98% for 30+ minutes
- **K3sClusterDegraded**: <50% of K3s nodes ready for 15+ minutes

**Alert Philosophy**: Only critical issues that require immediate attention. No warning-level alerts to avoid homelab alert fatigue.

## Email Alert Setup

### Final Working Configuration ✅

**Email alerting is successfully configured using Grafana Unified Alerting with Yahoo SMTP**

- **Platform**: Grafana Unified Alerting (not Prometheus Alertmanager)
- **SMTP Provider**: Yahoo Mail (`smtp.mail.yahoo.com:587`)
- **Destination**: `g_skumar@yahoo.com`
- **Authentication**: Yahoo app password stored in Kubernetes secret
- **Security**: Credentials never stored in GitOps repository

### Prerequisites: Yahoo App Password

1. **Generate Yahoo App Password**:
   - Go to Yahoo Account Security: https://login.yahoo.com/account/security
   - Enable 2-step verification if not already enabled
   - Generate app password for "Mail" applications
   - Copy the 16-character password (no spaces)

### Implementation: Manual Secret Creation

**IMPORTANT**: The SMTP secret must be created manually and is NOT managed by GitOps:

```bash
# Create secret with Yahoo credentials (replace YOUR_APP_PASSWORD)
kubectl create secret generic smtp-credentials \
  --from-literal=user='g_skumar@yahoo.com' \
  --from-literal=pass='YOUR_YAHOO_APP_PASSWORD' \
  -n monitoring
```

### Grafana Configuration

The email alerting is configured in `monitoring-values.yaml` with:

```yaml
grafana:
  smtp:
    enabled: true
    existingSecret: smtp-credentials
    userKey: user
    passwordKey: pass
    host: smtp.mail.yahoo.com:587
    fromAddress: g_skumar@yahoo.com
    skipVerify: false
  grafana.ini:
    unified_alerting:
      enabled: true
    alerting:
      enabled: false  # Legacy alerting disabled
    smtp:
      enabled: true
      host: smtp.mail.yahoo.com:587
      user: $__file{/etc/secrets/smtp-credentials/user}
      password: $__file{/etc/secrets/smtp-credentials/pass}
      from_address: g_skumar@yahoo.com
      skip_verify: false
  extraSecretMounts:
    - name: smtp-credentials
      secretName: smtp-credentials
      mountPath: /etc/secrets/smtp-credentials
      readOnly: true
```

### Usage: Creating Email Alerts in Grafana

1. **Access Grafana**: `http://<node-ip>:32080` (admin/admin)
2. **Contact Points**: Alerting → Contact Points → Add contact point
   - **Name**: `email-notifications`
   - **Type**: `Email`
   - **Addresses**: `g_skumar@yahoo.com`
3. **Notification Policies**: Configure routing to email contact point
4. **Alert Rules**: Create rules that will trigger email notifications

### Troubleshooting and Lessons Learned

#### What Didn't Work (Documented for Reference)

1. **Prometheus Alertmanager via Helm Values**:
   - **Issue**: kube-prometheus-stack ignores custom alertmanager config in helm values
   - **Error**: Configuration parsing errors, secrets not properly mounted
   - **Lesson**: Helm values approach for alertmanager is unreliable in kube-prometheus-stack

2. **AlertmanagerConfig CRD Approach**:
   - **Issue**: CRD not picked up by prometheus-operator despite correct selectors
   - **Error**: Configuration never merged into alertmanager runtime config
   - **Lesson**: AlertmanagerConfig CRD support in kube-prometheus-stack can be inconsistent

3. **Zoho SMTP Configuration**:
   - **Issue**: "554 5.7.8 Access Restricted" error
   - **Cause**: Zoho requires app-specific passwords, complex authentication
   - **Lesson**: Yahoo SMTP is more reliable for automated systems

#### What Worked: Grafana Unified Alerting

- **Reliable**: Direct SMTP configuration in Grafana
- **Secure**: File-based credential mounting from Kubernetes secrets
- **User-Friendly**: Web UI for creating and managing alert rules
- **Flexible**: Supports multiple notification channels and complex routing

#### Key Technical Details

1. **Secret Mounting**: Uses `extraSecretMounts` to mount credentials as files
2. **File-Based Auth**: Grafana reads credentials from mounted files using `$__file{}` syntax
3. **Configuration Reload**: Requires Helm release upgrade and pod restart for config changes
4. **Unified Alerting**: Must disable legacy alerting and enable unified alerting

### Security Notes

- **Never commit SMTP passwords** to Git repositories
- **Use app passwords** instead of account passwords for third-party applications
- **Rotate credentials** regularly and update the Kubernetes secret
- **Secret is cluster-local** and not managed by GitOps for security

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