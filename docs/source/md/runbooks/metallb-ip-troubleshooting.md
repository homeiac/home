# Runbook: MetalLB LoadBalancer IP Troubleshooting

**Last Updated**: 2025-11-29
**Owner**: homelab
**Related RCA**: [2025-11-29-traefik-ip-shuffle](../rca/2025-11-29-traefik-ip-shuffle.md)

## Overview

This runbook covers diagnosing and resolving MetalLB LoadBalancer IP issues, including IP shuffling after restarts, allocation failures, and DNS mismatches.

## Quick Reference: Current IP Allocation

| IP | Service | Namespace |
|----|---------|-----------|
| 192.168.4.80 | Traefik (ingress) | kube-system |
| 192.168.4.81 | Ollama | ollama |
| 192.168.4.82 | Stable Diffusion | stable-diffusion |
| 192.168.4.120 | Samba | samba |

**MetalLB Pool**: 192.168.4.80-192.168.4.120

## Symptoms

- Service accessible via IP but not via DNS hostname
- Wrong service responding on a hostname (e.g., Grafana showing Ollama)
- `<pending>` in EXTERNAL-IP column for LoadBalancer services
- DNS resolution returning unexpected IP

## Diagnostic Steps

### 1. Check Current LoadBalancer Assignments

```bash
KUBECONFIG=~/kubeconfig kubectl get svc -A -o wide | grep LoadBalancer
```

Expected output:
```
kube-system        traefik              LoadBalancer   10.43.x.x    192.168.4.80    80:xxxxx/TCP,443:xxxxx/TCP
ollama             ollama-lb            LoadBalancer   10.43.x.x    192.168.4.81    80:xxxxx/TCP
stable-diffusion   stable-diffusion-webui LoadBalancer 10.43.x.x   192.168.4.82    80:xxxxx/TCP
samba              samba-lb             LoadBalancer   10.43.x.x    192.168.4.120   445:xxxxx/TCP,139:xxxxx/TCP
```

### 2. Verify DNS Resolution

```bash
# Check what DNS returns
nslookup grafana.app.homelab
nslookup ollama.app.homelab

# Should all return 192.168.4.80 (Traefik) for ingress-based services
```

### 3. Test Direct Connectivity

```bash
# Test Traefik responds correctly
curl -s -H "Host: grafana.app.homelab" http://192.168.4.80/
# Should return 302 redirect to /login

# Test via DNS
curl -s http://grafana.app.homelab/
# Should match above
```

### 4. Check MetalLB Pool Configuration

```bash
KUBECONFIG=~/kubeconfig kubectl get ipaddresspool -n metallb-system -o yaml
```

### 5. Check Service Events for Allocation Issues

```bash
KUBECONFIG=~/kubeconfig kubectl describe svc <service-name> -n <namespace> | tail -20
```

Look for:
- `AllocationFailed` - IP conflict or pool exhausted
- `IPAllocated` - Successful allocation
- `ClearAssignment` - IP being reassigned

## Common Issues and Fixes

### Issue 1: Service Has Wrong IP After Restart

**Symptom**: LoadBalancer IP changed after cluster/node restart

**Cause**: No static IP annotation configured

**Fix**: Add MetalLB annotation to service

```yaml
metadata:
  annotations:
    metallb.universe.tf/loadBalancerIPs: "192.168.4.XX"
```

For GitOps-managed services, edit the service.yaml in the appropriate directory:
- `gitops/clusters/homelab/apps/<app>/service.yaml`

For Traefik (K3s-managed), use HelmChartConfig:
```yaml
# gitops/clusters/homelab/infrastructure/traefik/helmchartconfig.yaml
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    service:
      annotations:
        metallb.universe.tf/loadBalancerIPs: "192.168.4.80"
```

### Issue 2: Service Stuck in `<pending>`

**Symptom**: EXTERNAL-IP shows `<pending>` indefinitely

**Diagnostic**:
```bash
KUBECONFIG=~/kubeconfig kubectl describe svc <service-name> -n <namespace>
```

**Common Causes**:

1. **IP already in use**: Another service has the requested static IP
   ```
   AllocationFailed: can't change sharing key, address also in use by...
   ```
   **Fix**: Delete and recreate the service, or choose different IP

2. **IP outside pool range**: Requested IP not in MetalLB pool
   ```
   AllocationFailed: "192.168.4.XX" is not allowed in config
   ```
   **Fix**: Use IP within 192.168.4.80-120 range

3. **MetalLB speaker not running**: No node can announce the IP
   ```bash
   KUBECONFIG=~/kubeconfig kubectl get pods -n metallb-system
   ```
   **Fix**: Check MetalLB speaker pods are running

### Issue 3: DNS Points to Wrong IP

**Symptom**: nslookup returns IP that doesn't match current LoadBalancer

**Fix**: Update OPNsense DNS override

1. Navigate to: Services → Unbound DNS → Overrides
2. Find the host override for the affected hostname
3. Update IP to match current LoadBalancer IP
4. Apply changes

**Better Fix**: Ensure static IP annotation so LoadBalancer IP is predictable

### Issue 4: IP Conflict During Reassignment

**Symptom**: Service shows `<pending>` with allocation errors

**Fix**: Force clean reassignment
```bash
# Delete the service
KUBECONFIG=~/kubeconfig kubectl delete svc <service-name> -n <namespace>

# Wait a moment
sleep 5

# Reapply from GitOps or manually
KUBECONFIG=~/kubeconfig kubectl apply -f <service.yaml>
```

## Traefik-Specific Procedures

### Apply Traefik Static IP (HelmChartConfig)

```bash
# Check if HelmChartConfig exists
KUBECONFIG=~/kubeconfig kubectl get helmchartconfig -n kube-system traefik

# Apply directly if needed
KUBECONFIG=~/kubeconfig kubectl apply -f gitops/clusters/homelab/infrastructure/traefik/helmchartconfig.yaml

# Verify IP changed
KUBECONFIG=~/kubeconfig kubectl get svc traefik -n kube-system
```

### Force Traefik Restart

```bash
# Delete the Traefik pod to force Helm reconciliation
KUBECONFIG=~/kubeconfig kubectl delete pod -n kube-system -l app.kubernetes.io/name=traefik
```

## Verification Checklist

After any fix, verify:

- [ ] `kubectl get svc -A | grep LoadBalancer` shows expected IPs
- [ ] `nslookup <hostname>` returns correct IP
- [ ] `curl http://<hostname>/` returns expected response
- [ ] Changes committed to GitOps repository

## Emergency: Restore Service Access

If ingress is completely broken:

```bash
# 1. Find current Traefik IP
KUBECONFIG=~/kubeconfig kubectl get svc traefik -n kube-system -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# 2. Test direct access with Host header
curl -H "Host: grafana.app.homelab" http://<TRAEFIK_IP>/

# 3. If working, update OPNsense DNS to point to this IP
# Services → Unbound DNS → Overrides → Edit host override

# 4. Apply permanent fix via GitOps (static IP annotation)
```

## Related Commands Reference

```bash
# List all MetalLB resources
KUBECONFIG=~/kubeconfig kubectl get all -n metallb-system

# Check MetalLB logs
KUBECONFIG=~/kubeconfig kubectl logs -n metallb-system -l app=metallb -c speaker --tail=50

# List all ingresses
KUBECONFIG=~/kubeconfig kubectl get ingress -A

# Check ingress details
KUBECONFIG=~/kubeconfig kubectl describe ingress <name> -n <namespace>
```

## Tags

metallb, metalb, loadbalancer, load-balancer, traefik, trafik, ingress, static-ip, dns, opnsense, k3s, kubernetes, kubernettes, troubleshooting, runbook
