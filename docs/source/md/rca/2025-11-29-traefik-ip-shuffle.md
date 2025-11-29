# RCA: Traefik Ingress IP Shuffle After Cluster Restart

**Date**: 2025-11-29
**Duration**: ~30 minutes
**Severity**: Medium (service degradation)
**Services Affected**: All ingress-based services (Grafana, Ollama via ingress, Stable Diffusion via ingress)

## Executive Summary

After a K3s cluster restart, the Traefik ingress controller was assigned a different MetalLB IP address (192.168.4.82) than what OPNsense DNS was configured for (192.168.4.80). This caused all `*.app.homelab` traffic to route to Ollama instead of Traefik, breaking access to Grafana and other ingress-based services.

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 21:01:15 | K3s core services restart (cause unknown - likely node reboot) |
| 21:01:36 | Traefik HelmChart recreated, assigned IP 192.168.4.82 |
| 21:01:36 | Ollama retains IP 192.168.4.80 (service was not recreated) |
| ~21:22 | Issue detected: grafana.app.homelab showing Ollama response |
| ~21:25 | Root cause identified: DNS pointing to wrong LoadBalancer IP |
| ~21:30 | Fix deployed: Static IP annotations added to all services |
| ~21:32 | Services verified working |

## Root Cause Analysis

### Primary Cause: No Static IP Reservations for MetalLB Services

MetalLB assigns IPs from its pool in order of service creation. When services are recreated (e.g., after cluster restart), they may receive different IPs than before.

**Before restart:**
- Traefik: 192.168.4.80 (first created, got first IP)
- Ollama: 192.168.4.81
- Stable Diffusion: 192.168.4.82

**After restart:**
- Ollama: 192.168.4.80 (service persisted, kept its IP)
- Stable Diffusion: 192.168.4.81 (service persisted)
- Traefik: 192.168.4.82 (recreated by K3s, got next available)

### Contributing Factors

1. **K3s manages Traefik internally**: Unlike user-deployed services, K3s recreates Traefik on every restart via HelmChart
2. **No HelmChartConfig for Traefik**: Static IP annotation was not configured
3. **DNS hardcoded to single IP**: OPNsense DNS override pointed to 192.168.4.80 assuming it would always be Traefik

### Why Ollama Responded on Port 80

The Ollama LoadBalancer service (`ollama-lb`) exposes port 80 externally, mapping to Ollama's internal port 11434. When DNS sent traffic to 192.168.4.80:80, Ollama responded with its default message "Ollama is running" instead of the expected Grafana login page.

## Impact

- **Grafana**: Inaccessible via grafana.app.homelab
- **Ollama Ingress**: Inaccessible via ollama.app.homelab (direct LB still worked)
- **Stable Diffusion Ingress**: Inaccessible via stable-diffusion.app.homelab
- **Monitoring**: Grafana dashboards unavailable during incident

## Resolution

### Immediate Fix

Applied static IP annotations to all LoadBalancer services:

```yaml
# Traefik (via HelmChartConfig)
metadata:
  annotations:
    metallb.universe.tf/loadBalancerIPs: "192.168.4.80"

# Ollama
metadata:
  annotations:
    metallb.universe.tf/loadBalancerIPs: "192.168.4.81"

# Stable Diffusion
metadata:
  annotations:
    metallb.universe.tf/loadBalancerIPs: "192.168.4.82"

# Samba (already had static IP)
metadata:
  annotations:
    metallb.universe.tf/loadBalancerIPs: "192.168.4.120"
```

### Files Modified

1. `gitops/clusters/homelab/infrastructure/traefik/helmchartconfig.yaml` (new)
2. `gitops/clusters/homelab/infrastructure/traefik/kustomization.yaml` (new)
3. `gitops/clusters/homelab/kustomization.yaml` (added traefik reference)
4. `gitops/clusters/homelab/apps/ollama/service.yaml` (added annotation)
5. `gitops/clusters/homelab/apps/stable-diffusion/service.yaml` (added annotation)

### Commit

```
58bb5e2 fix: assign static MetalLB IPs to prevent IP shuffling on restarts
```

## Final IP Allocation

| IP | Service | Purpose |
|----|---------|---------|
| 192.168.4.80 | Traefik | Ingress controller (*.app.homelab) |
| 192.168.4.81 | Ollama | Direct API access |
| 192.168.4.82 | Stable Diffusion | Direct WebUI access |
| 192.168.4.83-119 | (available) | Future services |
| 192.168.4.120 | Samba | File sharing |

## Lessons Learned

1. **Always use static IP annotations for critical services**: Any service that DNS points to must have a predictable IP
2. **K3s-managed components need HelmChartConfig**: Traefik and other K3s addons require special configuration method
3. **MetalLB IP assignment is not stable across restarts**: Without annotations, IPs are assigned based on service creation order

## Prevention

### Implemented

- [x] Static IP annotations on all LoadBalancer services
- [x] HelmChartConfig for Traefik static IP
- [x] GitOps-managed configuration for repeatability

### Recommended Future Actions

- [ ] Add monitoring alert for LoadBalancer IP changes
- [ ] Document IP allocation in homelab inventory
- [ ] Consider using MetalLB IPAddressPool `autoAssign: false` with explicit allocations only

## Tags

metallb, metalb, traefik, trafik, ingress, loadbalancer, load-balancer, dns, ip-address, k3s, kubernetes, kubernettes, cluster-restart, grafana, ollama, static-ip

## Related Documentation

- [MetalLB Configuration](../metallb-configuration.md)
- [K3s Traefik Customization](https://docs.k3s.io/helm#customizing-packaged-components-with-helmchartconfig)
- [OPNsense DNS Overrides](../opnsense-dns-configuration.md)
