# Troubleshooting: Seamless Homelab Access (TLS/Certs)

**Last Updated**: 2026-01-01
**Tags**: troubleshooting, tls, cert-manager, traefik, dns, runbook

---

## Quick Reference

| Component | Check Command |
|-----------|---------------|
| Certificates | `kubectl get certificates -A` |
| Cert secrets | `kubectl get secret -n kube-system wildcard-app-home-tls` |
| TLSStore | `kubectl get tlsstore -n kube-system` |
| Traefik logs | `kubectl logs -n kube-system deploy/traefik --tail=50` |
| DNS resolution | `dig @8.8.8.8 frigate.app.home.panderosystems.com` |
| Flux status | `flux get kustomization -A` |

---

## Symptom: Browser Shows "Connection Not Private"

### Check 1: Is the certificate issued?

```bash
kubectl get certificates -n kube-system
```

Expected:
```
NAME                        READY   SECRET                  AGE
wildcard-app-home-traefik   True    wildcard-app-home-tls   1h
wildcard-home-traefik       True    wildcard-home-tls       1h
```

If `READY=False`:
```bash
kubectl describe certificate wildcard-app-home-traefik -n kube-system
kubectl get challenges -A  # Check if DNS-01 challenge is pending
```

### Check 2: Is the secret present?

```bash
kubectl get secret wildcard-app-home-tls -n kube-system
```

If missing, cert-manager hasn't issued it yet. Check certificate status above.

### Check 3: Is TLSStore configured?

```bash
kubectl get tlsstore -n kube-system
```

Expected: `default` TLSStore exists.

### Check 4: Is Traefik using the cert?

```bash
curl -v --resolve frigate.app.home.panderosystems.com:443:192.168.4.80 \
  https://frigate.app.home.panderosystems.com 2>&1 | grep -A5 "Server certificate"
```

Should show:
```
* Server certificate:
*  subject: CN=*.app.home.panderosystems.com
*  issuer: C=US; O=Let's Encrypt; CN=...
```

---

## Symptom: DNS Not Resolving

### Check 1: Is external-dns syncing?

```bash
kubectl get dnsendpoint -n external-dns homelab-services -o yaml | grep -A3 "frigate"
```

### Check 2: Is Cloudflare updated?

```bash
dig @8.8.8.8 frigate.app.home.panderosystems.com +short
```

Should return `192.168.4.80`.

### Check 3: OPNsense Unbound Rebind Protection (COMMON!)

If Google DNS works but your router doesn't:
```bash
dig @8.8.8.8 frigate.app.home.panderosystems.com +short   # Works: 192.168.4.80
dig @192.168.4.1 frigate.app.home.panderosystems.com +short  # Empty!
```

**Cause**: Unbound blocks public DNS responses containing private IPs (rebind protection).

**Fix**:
1. OPNsense Web UI → **Services → Unbound DNS → Advanced**
2. Add to **Private Domains**: `panderosystems.com`
3. Click **Apply** to restart Unbound

This tells Unbound "it's OK if Cloudflare returns private IPs for this domain."

### Check 4: Local DNS cache

Browser/OS may cache old DNS. Clear:
- **Firefox**: `about:networking#dns` → Clear DNS Cache
- **Chrome**: `chrome://net-internals/#dns` → Clear host cache
- **macOS**: `sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder`

---

## Symptom: 404 Not Found (TLS works)

The cert is valid but Traefik can't find a matching route.

### Check 1: Does the Ingress have the new host?

```bash
kubectl get ingress -n frigate frigate-ingress -o yaml | grep -A2 "host:"
```

Should include:
```yaml
- host: frigate.app.home.panderosystems.com
```

### Check 2: Flux reconciled?

```bash
flux reconcile kustomization flux-system
kubectl get ingress -n frigate frigate-ingress -o yaml | grep -A2 "host:"
```

---

## Symptom: 400 Bad Request (Home Assistant)

HA rejects proxied requests by default.

### Fix: Add trusted_proxies

1. Open HA UI → File Editor add-on
2. Edit `configuration.yaml`:
   ```yaml
   http:
     use_x_forwarded_for: true
     trusted_proxies:
       - 10.42.0.0/16   # K3s pod CIDR
       - 192.168.4.0/24 # Homelab LAN (optional)
   ```
3. Restart HA: Developer Tools → Restart

---

## Symptom: Traefik Error "externalName services not allowed"

### Fix: Enable in HelmChartConfig

Check current config:
```bash
kubectl get helmchartconfig traefik -n kube-system -o yaml | grep -A4 "providers"
```

Should have:
```yaml
providers:
  kubernetesIngress:
    allowExternalNameServices: true
  kubernetesCRD:
    allowExternalNameServices: true
```

If missing, edit `gitops/clusters/homelab/infrastructure/traefik/helmchartconfig.yaml` and push.

---

## Symptom: Certificate Not Renewing

Certs expire in 90 days, renew at 60 days.

### Check 1: Certificate expiry

```bash
kubectl get certificate -n kube-system -o wide
```

### Check 2: cert-manager logs

```bash
kubectl logs -n cert-manager deploy/cert-manager --tail=100 | grep -i "renew\|expire"
```

### Check 3: ClusterIssuer healthy?

```bash
kubectl get clusterissuer letsencrypt-prod
kubectl describe clusterissuer letsencrypt-prod
```

---

## Recovery: Full Cert Re-issue

If certs are corrupted or expired:

```bash
# Delete existing certs (will be re-issued)
kubectl delete certificate -n kube-system wildcard-app-home-traefik wildcard-home-traefik
kubectl delete certificate -n cert-manager wildcard-app-home wildcard-home

# Delete secrets
kubectl delete secret -n kube-system wildcard-app-home-tls wildcard-home-tls
kubectl delete secret -n cert-manager wildcard-app-home-tls wildcard-home-tls

# Reconcile Flux
flux reconcile kustomization cert-manager-config
flux reconcile kustomization traefik-config

# Watch re-issue
kubectl get certificates -A -w
```

---

## Recovery: Rollback to HTTP-only

If TLS is broken and you need services working immediately:

1. Access via old URLs: `http://frigate.app.homelab` (still works)
2. Or comment out TLSStore and push:
   ```bash
   # In gitops/clusters/homelab/infrastructure/traefik-config/resources/kustomization.yaml
   # Comment out: - tlsstore-default.yaml
   git commit -am "temp: disable TLSStore" && git push
   flux reconcile kustomization traefik-config
   ```

---

## Component Locations

| Component | GitOps Path |
|-----------|-------------|
| cert-manager HelmRelease | `infrastructure/cert-manager/helmrelease.yaml` |
| ClusterIssuer | `infrastructure/cert-manager-config/resources/clusterissuer.yaml` |
| Wildcard Certs (cert-manager ns) | `infrastructure/cert-manager-config/resources/wildcard-*.yaml` |
| Wildcard Certs (kube-system ns) | `infrastructure/traefik-config/resources/wildcard-cert-kube-system.yaml` |
| TLSStore | `infrastructure/traefik-config/resources/tlsstore-default.yaml` |
| Traefik config | `infrastructure/traefik/helmchartconfig.yaml` |
| DNS endpoints | `infrastructure/external-dns/dnsendpoints.yaml` |
| Frigate ingress | `apps/frigate/ingress.yaml` |
| Grafana ingress | `infrastructure/monitoring/grafana-ingress.yaml` |
| HA IngressRoute | `infrastructure/traefik-config/resources/homeassistant-ingress.yaml` |

---

## Flux Dependency Chain

```
flux-system (main kustomization)
    │
    ├── cert-manager (HelmRelease)
    │       │
    │       └── cert-manager-config (Flux Kustomization, dependsOn: flux-system)
    │               │
    │               └── traefik-config (Flux Kustomization, dependsOn: cert-manager-config)
    │
    └── apps/frigate, apps/... (Ingresses)
```

If something breaks, reconcile in order:
```bash
flux reconcile kustomization flux-system
flux reconcile kustomization cert-manager-config
flux reconcile kustomization traefik-config
```
