# Seamless Homelab Access Part 1: Valid TLS Certs Without Public Exposure

**Date**: 2026-01-01
**Author**: Nikhil Pandey
**Tags**: homelab, cert-manager, letsencrypt, dns-01, cloudflare, flux, gitops, tailscale

---

## The Problem

My homelab has a persistent annoyance: browser certificate warnings. Every time I access Grafana, Frigate, or any internal service, I'm greeted with "Your connection is not private." Even worse, my Home Assistant iOS app shows a permanent security warning.

The obvious solutions don't work for my setup:

1. **Self-signed certs**: Still trigger browser warnings
2. **HTTP-01 challenge**: Requires port 80 open to the internet (security risk)
3. **Public exposure via Cloudflare Tunnel**: I don't want my services on the public internet

What I wanted:
- Valid LetsEncrypt certificates for `*.app.home.panderosystems.com`
- Zero internet exposure
- Same URLs work from home LAN and remotely via Tailscale
- GitOps-managed (Flux)

## The Solution: DNS-01 Challenge

The DNS-01 ACME challenge proves domain ownership by creating a TXT record, not by serving HTTP. This means:

- No ports need to be open
- No public ingress required
- Works for wildcard certificates
- Perfect for internal-only services

```
LetsEncrypt: "Prove you own *.app.home.panderosystems.com"
cert-manager: "Here's a TXT record at _acme-challenge.app.home..."
LetsEncrypt: "Verified. Here's your wildcard cert."
```

## Architecture

```
                                    ┌─────────────────────┐
                                    │   Cloudflare DNS    │
                                    │  panderosystems.com │
                                    └──────────┬──────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │     LetsEncrypt     │
                                    │   (validates TXT)   │
                                    └──────────┬──────────┘
                                               │
┌──────────────────────────────────────────────┼──────────────────────────┐
│ K3s Cluster                                  │                          │
│                                              │                          │
│  ┌─────────────────┐    ┌───────────────────▼────────────────┐          │
│  │  cert-manager   │───▶│  Cloudflare API (create TXT)       │          │
│  │  (DNS-01)       │    └────────────────────────────────────┘          │
│  └────────┬────────┘                                                    │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────┐     ┌─────────────────┐                           │
│  │   ClusterIssuer │────▶│   Certificate   │                           │
│  │ letsencrypt-prod│     │ *.app.home....  │                           │
│  └─────────────────┘     └────────┬────────┘                           │
│                                   │                                     │
│                                   ▼                                     │
│                          ┌─────────────────┐                           │
│                          │   TLS Secret    │                           │
│                          │ wildcard-app... │                           │
│                          └────────┬────────┘                           │
│                                   │                                     │
│                                   ▼                                     │
│                          ┌─────────────────┐                           │
│                          │     Traefik     │◀── All HTTPS traffic      │
│                          │   (uses cert)   │                           │
│                          └─────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────┘
```

## Implementation

### Step 1: cert-manager HelmRelease

First, deploy cert-manager via Flux:

```yaml
# gitops/clusters/homelab/infrastructure/cert-manager/helmrelease.yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: cert-manager
  namespace: cert-manager
spec:
  chart:
    spec:
      chart: cert-manager
      sourceRef:
        kind: HelmRepository
        name: jetstack
        namespace: flux-system
      version: "1.16.x"
  install:
    crds: Create
  upgrade:
    crds: CreateReplace
  values:
    crds:
      enabled: true
```

### Step 2: ClusterIssuer with Cloudflare DNS-01

```yaml
# gitops/clusters/homelab/infrastructure/cert-manager-config/resources/clusterissuer.yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: nikhil@panderosystems.com
    privateKeySecretRef:
      name: letsencrypt-prod-account-key
    solvers:
      - dns01:
          cloudflare:
            apiTokenSecretRef:
              name: cloudflare-api-token
              key: api-token
        selector:
          dnsZones:
            - "panderosystems.com"
```

### Step 3: Wildcard Certificate

```yaml
# gitops/clusters/homelab/infrastructure/cert-manager-config/resources/wildcard-certificate.yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: wildcard-app-home
  namespace: cert-manager
spec:
  secretName: wildcard-app-home-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  commonName: "*.app.home.panderosystems.com"
  dnsNames:
    - "*.app.home.panderosystems.com"
    - "app.home.panderosystems.com"
  duration: 2160h    # 90 days
  renewBefore: 720h  # 30 days before expiry
```

## The CRD Ordering Problem

Here's where I got stuck: Flux applies all resources in a kustomization simultaneously. But `Certificate` and `ClusterIssuer` are CRDs that don't exist until cert-manager's HelmRelease installs them.

**Error**:
```
Certificate/cert-manager/wildcard-app-home dry-run failed:
no matches for kind "Certificate" in version "cert-manager.io/v1"
```

### The Fix: Flux dependsOn Pattern

Per the [Flux docs](https://github.com/fluxcd/flux2/discussions/2282), the solution is to use a separate Flux Kustomization with `dependsOn`:

```
infrastructure/cert-manager/           # HelmRelease only
infrastructure/cert-manager-config/
  ├── flux-kustomization.yaml          # Has dependsOn
  └── resources/
      ├── clusterissuer.yaml
      └── wildcard-certificate.yaml
```

The Flux Kustomization waits for cert-manager to be healthy:

```yaml
# flux-kustomization.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: cert-manager-config
  namespace: flux-system
spec:
  interval: 10m
  path: ./gitops/clusters/homelab/infrastructure/cert-manager-config/resources
  dependsOn:
    - name: flux-system
  healthChecks:
    - apiVersion: helm.toolkit.fluxcd.io/v2
      kind: HelmRelease
      name: cert-manager
      namespace: cert-manager
```

## Watching It Work

After pushing to git and triggering Flux:

```bash
$ kubectl get challenges -n cert-manager
NAME                          STATE     DOMAIN
wildcard-app-home-...-997..   pending   app.home.panderosystems.com

# 2 minutes later...
$ kubectl get certificates -n cert-manager
NAME                READY   SECRET                  AGE
wildcard-app-home   True    wildcard-app-home-tls   5m
wildcard-home       True    wildcard-home-tls       5m
```

The DNS-01 flow:
1. cert-manager creates TXT record via Cloudflare API
2. LetsEncrypt queries `_acme-challenge.app.home.panderosystems.com`
3. TXT record verified, certificate issued
4. Secret created with the TLS cert/key

## SOPS for Secrets

The Cloudflare API token is encrypted with SOPS/age:

```yaml
# cloudflare-secret.yaml (encrypted)
stringData:
  api-token: ENC[AES256_GCM,data:d8xa+V3BvJN...,type:str]
sops:
  age:
    - recipient: age1uwvq3llqjt666t4ckls9wv44wcpxxwlu8svqwx5kc7v76hncj94qg3tsna
```

Flux automatically decrypts when applying. I created helper scripts:

```bash
# Setup local SOPS access
./scripts/sops/setup-local-sops.sh

# Encrypt a new secret
./scripts/sops/encrypt-secret.sh path/to/secret.yaml

# Copy secret to new namespace
./scripts/sops/copy-secret-to-namespace.sh source.yaml new-ns dest.yaml
```

## What's Next (Part 2)

Now I have valid wildcard certs. Part 2 will cover:

1. **Configure Traefik** to use the wildcard cert as default
2. **Route Home Assistant** through Traefik (currently direct)
3. **Test Tailscale access** - same URL from home or away
4. **Google OAuth for Grafana** - SSO without public callbacks

## Key Takeaways

1. **DNS-01 = No public exposure**: Perfect for internal services
2. **Flux dependsOn is essential**: CRD ordering matters
3. **Wildcard certs simplify everything**: One cert for all services
4. **GitOps makes it reproducible**: Everything in version control

The dream: `https://grafana.app.home.panderosystems.com` with a green lock, whether I'm on my couch or at a coffee shop.

---

## References

- [cert-manager Cloudflare DNS-01](https://cert-manager.io/docs/configuration/acme/dns01/cloudflare/)
- [Flux HelmRelease dependsOn](https://github.com/fluxcd/flux2/discussions/2282)
- [SOPS with Flux](https://fluxcd.io/flux/guides/mozilla-sops/)
- [Tailscale Subnet Routers](https://tailscale.com/kb/1019/subnets)
