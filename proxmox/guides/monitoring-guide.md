# Monitoring Stack Setup

This guide shows how to deploy Prometheus and Grafana using the `kube-prometheus-stack` Helm chart. The default values are stored in `k8s/monitoring-values.yaml`.

## Storage Considerations

Prometheus generates a large write load, so running it on distributed storage like Longhorn is discouraged. Use node-local storage instead. Grafana can remain on Longhorn because it has lighter write requirements. Update `k8s/monitoring-values.yaml` so only Prometheus claims `local-path` storage:

```yaml
# k8s/monitoring-values.yaml
grafana:
  persistence:
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

Apply the Helm chart with these values to ensure data stays on each node's local disk.

## Deploy with Flux

The monitoring stack is now managed through Flux. The manifests live under
`gitops/clusters/homelab/infrastructure/monitoring`. Flux applies the
`kube-prometheus-stack` chart using the same `k8s/monitoring-values.yaml` file,
so existing Grafana dashboards and Prometheus data remain intact.
