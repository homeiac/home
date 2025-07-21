# Monitoring Troubleshooting

This guide collects solutions for common issues with the monitoring stack.

## Changing Grafana Storage Class from Longhorn to Local Path

### Background

Changing the `storageClassName` field in `monitoring-values.yaml` is **not**
enough to switch Grafana's persistent volume claim from Longhorn to
`local-path`. Helm will fail if the old PVC still exists.

Even with the following values:

```yaml
grafana:
  persistence:
    enabled: true
    size: 10Gi
    accessModes:
      - ReadWriteOnce
    storageClassName: local-path
```

Flux will keep the existing PVC bound to Longhorn and Helm cannot patch it.

### Symptoms

- Helm reconciliation fails with an immutable field error:

```text
Helm upgrade failed for release monitoring/kube-prometheus-stack with chart \
kube-prometheus-stack@74.2.1: cannot patch "kube-prometheus-stack-grafana" \
with kind PersistentVolumeClaim: PersistentVolumeClaim \
"kube-prometheus-stack-grafana" is invalid: spec: Forbidden: spec is immutable...
```

- The HelmRelease enters a **Stalled** state with `RetriesExceeded`.
- The `kube-prometheus-stack-grafana` pod is never recreated and the PVC remains bound to Longhorn.

### What We Tried (and Failed)

- Manually patching the HelmRelease status.
- Waiting for automatic reconciliation.
- Confirming `monitoring-values.yaml` contained the correct `local-path` storage class.
- Verifying the Flux `Kustomization` applied successfully.
- Restarting the Helm Controller.

None of these resolved the issue.

### What Finally Worked

1. **Delete the HelmRelease** for `kube-prometheus-stack`:

   ```bash
   kubectl delete helmrelease kube-prometheus-stack -n monitoring
   ```

2. Wait for Flux to recreate the release from Git. The new PVC is created with the `local-path` storage class.

### Important Note on Grafana Dashboards

Deleting the PVC removes all stored dashboards. The following were re-imported manually:

| Dashboard ID | Notes |
| ------------ | ----- |
| `10347` | Proxmox via **Prometheus** – Works |
| `13654` | Kube-prometheus metrics overview |
| `1860` | Node Exporter Full |
| `3662` | Kubernetes Cluster Monitoring (via Prometheus) |
| `10048` | **Do not use** – requires InfluxDB |

Update your provisioning steps or README to note the use of dashboard `10347` and avoid importing `10048`.

### Suggested Future Improvement

- Back up Grafana's PVC to avoid data loss.
- Use Grafana provisioning so dashboards load automatically on startup.
