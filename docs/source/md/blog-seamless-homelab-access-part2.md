# Seamless Homelab Access Part 2: Traefik TLS Termination

**Date**: 2026-01-01
**Author**: Nikhil Pandey
**Tags**: homelab, traefik, tls, ingress, wildcard-cert, flux, gitops

---

## Recap: What Part 1 Did

Part 1 deployed cert-manager with DNS-01 challenge to get valid LetsEncrypt wildcard certificates:
- `*.app.home.panderosystems.com`
- `*.home.panderosystems.com`

No public exposure, no port forwarding. Just DNS TXT records via Cloudflare API.

## Part 2 Goal

Make services actually use those certs:
- `https://frigate.app.home.panderosystems.com` - valid TLS, green lock
- `https://grafana.app.home.panderosystems.com` - valid TLS, green lock

## The Architecture

```
                         INTERNET
                            │
                            │ DNS Query: frigate.app.home.panderosystems.com
                            ▼
                    ┌───────────────┐
                    │  Cloudflare   │
                    │     DNS       │
                    └───────┬───────┘
                            │
                            │ Returns: 192.168.4.80 (private IP!)
                            ▼
        ┌───────────────────────────────────────────────────────┐
        │                    HOME LAN                           │
        │                                                       │
        │   Browser ──────────────────────────────────────┐    │
        │   (or Tailscale)                                │    │
        │                                                 │    │
        │                                                 ▼    │
        │                                         ┌─────────┐  │
        │                                         │ Traefik │  │
        │                                         │  :443   │  │
        │                                         │192.168. │  │
        │                                         │  4.80   │  │
        │                                         └────┬────┘  │
        │                                              │       │
        │            ┌─────────────────────────────────┤       │
        │            │                                 │       │
        │            ▼                                 ▼       │
        │     ┌────────────┐                   ┌────────────┐  │
        │     │  Frigate   │                   │  Grafana   │  │
        │     │  (K8s pod) │                   │  (K8s pod) │  │
        │     └────────────┘                   └────────────┘  │
        │                                                       │
        └───────────────────────────────────────────────────────┘
```

**Key insight**: Cloudflare DNS returns a private IP (192.168.4.80). This is intentional:
- Attackers can't reach it (no route to 192.168.x.x from internet)
- You can reach it from home LAN directly
- You can reach it from anywhere via Tailscale subnet router

## What We Did

### 1. Created Certificates in kube-system Namespace

The wildcard certs from Part 1 were in `cert-manager` namespace. Traefik runs in `kube-system`. Kubernetes secrets don't cross namespaces by default.

**Solution**: Create duplicate Certificate resources in `kube-system`:

```yaml
# gitops/clusters/homelab/infrastructure/traefik-config/resources/wildcard-cert-kube-system.yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: wildcard-app-home-traefik
  namespace: kube-system
spec:
  secretName: wildcard-app-home-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
    - "*.app.home.panderosystems.com"
    - "app.home.panderosystems.com"
```

cert-manager issues a new cert (same wildcard, different secret location).

### 2. Created TLSStore Default

Traefik's `TLSStore` named `default` automatically applies to all HTTPS traffic:

```yaml
# gitops/clusters/homelab/infrastructure/traefik-config/resources/tlsstore-default.yaml
apiVersion: traefik.io/v1alpha1
kind: TLSStore
metadata:
  name: default
  namespace: kube-system
spec:
  defaultCertificate:
    secretName: wildcard-app-home-tls
```

Now any IngressRoute on `websecure` entrypoint gets the wildcard cert automatically.

### 3. Added New Hosts to Existing Ingresses

The existing ingresses used `*.app.homelab` (old domain). Added the new domain as additional host:

```yaml
# gitops/clusters/homelab/apps/frigate/ingress.yaml
spec:
  rules:
  - host: frigate.app.homelab          # Old - still works
    http: ...
  - host: frigate.app.home.panderosystems.com  # New - valid TLS
    http: ...
```

Both URLs work. Old one for backwards compatibility, new one for valid TLS.

### 4. Enabled ExternalName Services (for HA)

Traefik disables ExternalName services by default (security). We enabled it for routing to VMs:

```yaml
# gitops/clusters/homelab/infrastructure/traefik/helmchartconfig.yaml
providers:
  kubernetesIngress:
    allowExternalNameServices: true
  kubernetesCRD:
    allowExternalNameServices: true
```

This allows Traefik to route to non-K8s backends (like Home Assistant VM).

## The Flow (Step by Step)

1. **You type**: `https://frigate.app.home.panderosystems.com`
2. **Browser asks DNS**: "What's the IP?"
3. **Cloudflare responds**: `192.168.4.80` (managed by external-dns)
4. **Browser connects** to 192.168.4.80:443 (Traefik's LoadBalancer IP)
5. **TLS handshake**: Traefik presents `*.app.home.panderosystems.com` cert
6. **Browser validates**: Cert signed by LetsEncrypt, hostname matches wildcard
7. **Traefik routes**: Host header matches Ingress rule, forwards to Frigate pod
8. **You see**: Frigate UI with green lock

## File Structure

```
gitops/clusters/homelab/
├── infrastructure/
│   ├── cert-manager/           # HelmRelease (deploys cert-manager)
│   ├── cert-manager-config/    # ClusterIssuer + Certs (depends on CRDs)
│   ├── traefik/                # HelmChartConfig (ExternalName enabled)
│   ├── traefik-config/         # TLSStore + Certs in kube-system
│   │   ├── flux-kustomization.yaml
│   │   └── resources/
│   │       ├── wildcard-cert-kube-system.yaml
│   │       ├── tlsstore-default.yaml
│   │       └── homeassistant-ingress.yaml
│   └── external-dns/           # DNSEndpoints (Cloudflare records)
└── apps/
    ├── frigate/
    │   └── ingress.yaml        # Both .homelab and .panderosystems.com hosts
    └── ...
```

## What's Working Now

| Service | Old URL | New URL (Valid TLS) |
|---------|---------|---------------------|
| Frigate | `http://frigate.app.homelab` | `https://frigate.app.home.panderosystems.com` |
| Grafana | `http://grafana.app.homelab` | `https://grafana.app.home.panderosystems.com` |

## What's Not Working Yet

| Service | Issue | Fix |
|---------|-------|-----|
| Home Assistant | 400 Bad Request | Needs `trusted_proxies` in HA config |

HA refuses proxied requests by default. Need to add to `configuration.yaml`:
```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 10.42.0.0/16   # K3s pod CIDR
```

## Key Learnings

1. **TLSStore `default`** = automatic cert for all HTTPS
2. **Secrets don't cross namespaces** - create certs where needed
3. **ExternalName disabled by default** - explicit opt-in for security
4. **Flux dependsOn chain** - cert-manager → cert-manager-config → traefik-config
5. **DNS caching is real** - Firefox needs manual cache clear or wait 5 min

---

## References

- [Part 1: Valid TLS Certs Without Public Exposure](blog-seamless-homelab-access-part1.md)
- [Traefik TLSStore](https://doc.traefik.io/traefik/routing/providers/kubernetes-crd/#kind-tlsstore)
- [cert-manager Certificate](https://cert-manager.io/docs/usage/certificate/)
