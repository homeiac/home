# Architecture: Seamless Homelab Access

**Version**: 1.0
**Date**: 2026-01-01
**Status**: Approved (validated by Claude Web + ChatGPT)

---

## Executive Summary

This architecture enables accessing homelab services using the **same FQDN** from anywhere—at home or via Tailscale—with **valid LetsEncrypt certificates** and **no public internet exposure**.

**Core Pattern**: Public DNS → Private IPs + Tailscale Subnet Router + DNS-01 Certificates

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              SEAMLESS ACCESS ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────────────────────┘

                         ┌─────────────────────────────────────┐
                         │          CLOUDFLARE DNS             │
                         │                                     │
                         │  *.app.home.panderosystems.com      │
                         │          → 192.168.4.80             │
                         │                                     │
                         │  ha.home.panderosystems.com         │
                         │          → 192.168.4.80             │
                         │                                     │
                         │  (Public DNS, private IPs - this    │
                         │   is intentional and safe)          │
                         └─────────────────────────────────────┘
                                          │
                                          │ DNS Response: 192.168.4.80
                                          │
          ┌───────────────────────────────┼───────────────────────────────┐
          │                               │                               │
          ▼                               ▼                               ▼
   ┌─────────────┐                ┌─────────────────┐             ┌─────────────┐
   │  AT HOME    │                │  TAILSCALE      │             │   AWAY      │
   │             │                │  SUBNET ROUTER  │             │             │
   │ 192.168.4.x │                │                 │             │  Coffee     │
   │  network    │                │  Advertises:    │             │  Shop WiFi  │
   │             │                │  192.168.4.0/24 │             │             │
   └──────┬──────┘                │  10.42.0.0/16   │             └──────┬──────┘
          │                       │  10.43.0.0/16   │                    │
          │                       └────────┬────────┘                    │
          │                                │                             │
          │ Direct route                   │ Tunnel                      │ Tailscale
          │                                │                             │ WireGuard
          │                                ▼                             │
          │                    ┌───────────────────┐                     │
          └───────────────────▶│  192.168.4.80     │◀────────────────────┘
                               │                   │
                               │     TRAEFIK       │◀──── Wildcard Cert
                               │  (K8s Ingress)    │      *.app.home.panderosystems.com
                               │                   │      (via cert-manager + DNS-01)
                               └─────────┬─────────┘
                                         │
              ┌──────────────────────────┬┴─────────────────────────┐
              │                          │                          │
              ▼                          ▼                          ▼
       ┌────────────┐             ┌────────────┐             ┌────────────┐
       │  Grafana   │             │  Frigate   │             │    HA      │
       │  (K8s pod) │             │  (K8s pod) │             │   (VM)     │
       │            │             │            │             │192.168.4.240│
       └────────────┘             └────────────┘             └────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           CERTIFICATE ISSUANCE FLOW                                  │
└─────────────────────────────────────────────────────────────────────────────────────┘

   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
   │ cert-manager │─────▶│  LetsEncrypt │─────▶│  Cloudflare  │─────▶│   Success    │
   │              │      │   ACME API   │      │   DNS API    │      │              │
   └──────────────┘      └──────────────┘      └──────────────┘      └──────────────┘
          │                     │                     │
          │ 1. Request cert     │                     │
          │    for *.app.home.  │                     │
          │    panderosystems   │                     │
          │                     │ 2. "Prove you       │
          │                     │    own this domain" │
          │                     │                     │
          │ 3. Create TXT record│                     │
          │    _acme-challenge  ├────────────────────▶│
          │                     │                     │
          │                     │ 4. Verify TXT       │
          │                     │◀────────────────────│
          │                     │                     │
          │ 5. Issue cert       │                     │
          │◀────────────────────│                     │
          │                     │                     │
          │ 6. Store in K8s     │                     │
          │    Secret           │                     │

   KEY INSIGHT: No inbound HTTP required. DNS-01 works for internal-only services.


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              GOOGLE OAUTH FLOW                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘

   ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
   │  Your    │     │ Grafana  │     │  Google  │     │ Grafana  │     │  Logged  │
   │ Browser  │     │          │     │  OAuth   │     │ Callback │     │   In!    │
   └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └──────────┘
        │                │                │                │
        │ 1. Click       │                │                │
        │ "Login Google" │                │                │
        ├───────────────▶│                │                │
        │                │                │                │
        │ 2. Redirect to │                │                │
        │    Google      │                │                │
        │◀───────────────│                │                │
        │                │                │                │
        │ 3. Auth with   │                │                │
        │    Google      │                │                │
        ├───────────────────────────────▶│                │
        │                │                │                │
        │ 4. Google      │                │                │
        │    redirects   │                │                │
        │    YOUR BROWSER│                │                │
        │    to callback │                │                │
        │◀───────────────────────────────│                │
        │                │                │                │
        │ 5. Browser     │                │                │
        │    hits        │                │                │
        │    callback    │                │                │
        ├───────────────────────────────────────────────▶│
        │                │                │                │
        │                │                │    6. Done!    │
        │◀───────────────────────────────────────────────│

   KEY INSIGHT: Google NEVER connects to your service.
                Your BROWSER does. Works fine with Tailscale.
```

---

## Component Details

### 1. Cloudflare DNS (external-dns)

**Purpose**: Authoritative DNS for `panderosystems.com`

**Configuration**:
```yaml
# Already exists: gitops/clusters/homelab/infrastructure/external-dns/dnsendpoints.yaml
endpoints:
  - dnsName: "*.app.home.panderosystems.com"
    recordType: A
    targets: ["192.168.4.80"]

  - dnsName: "ha.home.panderosystems.com"
    recordType: A
    targets: ["192.168.4.80"]  # Route through Traefik, not direct to HA
```

**Why private IPs in public DNS?**
- This is intentional and common for homelabs
- Info leak: attackers learn internal IP (not a security risk)
- Access requires being on LAN or Tailscale (the real security boundary)

---

### 2. Tailscale Subnet Router

**Purpose**: Make 192.168.4.0/24 reachable from anywhere via Tailscale

**Configuration** (already exists):
```yaml
# gitops/clusters/homelab/infrastructure/tailscale/connector.yaml
apiVersion: tailscale.com/v1alpha1
kind: Connector
metadata:
  name: homelab-subnet-router
spec:
  hostname: ts-homelab-router
  subnetRouter:
    advertiseRoutes:
      - "192.168.4.0/24"    # Homelab LAN
      - "10.42.0.0/16"      # K3s pod CIDR
      - "10.43.0.0/16"      # K3s service CIDR
  exitNode: true
```

**Status**: ✅ Already running and advertising routes

---

### 3. cert-manager + Cloudflare DNS-01

**Purpose**: Issue LetsEncrypt certificates without public exposure

**Components**:

| Resource | Purpose |
|----------|---------|
| HelmRelease | Deploys cert-manager |
| ClusterIssuer | Configures LetsEncrypt + Cloudflare |
| Certificate | Requests wildcard cert |
| Secret | Stores issued cert (auto-created) |

**Why DNS-01?**
- HTTP-01 requires inbound port 80 (we don't expose this)
- DNS-01 proves ownership via TXT record (no inbound needed)
- Works for wildcard certs (HTTP-01 doesn't support wildcards)

---

### 4. Traefik Configuration

**Purpose**: TLS termination + routing to backends

**Key Changes**:
- Configure default TLS cert (the wildcard)
- Add IngressRoute for HA (external backend)
- Enable HTTPS redirect

```
                    ┌─────────────────────────────────────────┐
                    │              TRAEFIK                    │
                    │                                         │
   HTTPS ──────────▶│  TLS Termination                       │
   (port 443)       │  (wildcard cert)                       │
                    │                                         │
                    │  ┌─────────────────────────────────┐   │
                    │  │  IngressRoutes:                 │   │
                    │  │                                 │   │
                    │  │  grafana.app.home.* → grafana   │   │
                    │  │  frigate.app.home.* → frigate   │   │
                    │  │  ollama.app.home.*  → ollama    │   │
                    │  │  ha.home.*          → HA VM     │◀──┼── External backend
                    │  │                                 │   │   192.168.4.240:8123
                    │  └─────────────────────────────────┘   │
                    └─────────────────────────────────────────┘
```

---

### 5. Home Assistant via Traefik

**Previous Plan**: Install cert directly on HA VM (complex)
**Better Plan**: Route HA through Traefik (simple, one cert pipeline)

**Benefits**:
- No cert management on HAOS (which is annoying)
- Same cert-manager pipeline for everything
- Same URL pattern (`ha.home.panderosystems.com`)
- Can add auth middleware later

**Configuration**:
```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: homeassistant
  namespace: kube-system
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`ha.home.panderosystems.com`)
      kind: Rule
      services:
        - name: homeassistant-external
          port: 8123
  tls:
    secretName: wildcard-app-home-tls

---
apiVersion: v1
kind: Service
metadata:
  name: homeassistant-external
  namespace: kube-system
spec:
  type: ExternalName
  externalName: 192.168.4.240  # HA VM IP
  ports:
    - port: 8123
```

---

### 6. Google OAuth (Grafana)

**Purpose**: Login with Google account

**Key Insight**: OAuth callbacks work with Tailscale because:
- Google redirects YOUR BROWSER (not Google's servers)
- Your browser can reach the callback URL via Tailscale
- No public exposure needed

**Grafana Config**:
```ini
[auth.google]
enabled = true
allow_sign_up = true
auto_login = false
client_id = YOUR_GOOGLE_CLIENT_ID
client_secret = YOUR_GOOGLE_CLIENT_SECRET
scopes = openid email profile
auth_url = https://accounts.google.com/o/oauth2/v2/auth
token_url = https://oauth2.googleapis.com/token
allowed_domains = gmail.com panderosystems.com
```

**Google Cloud Console**:
- Authorized redirect URIs: `https://grafana.app.home.panderosystems.com/login/google`

---

## Security Model

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              SECURITY BOUNDARIES                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

   PUBLIC INTERNET                    TAILSCALE BOUNDARY              HOME LAN
   ───────────────                    ──────────────────              ────────

   Cloudflare DNS                          │
   (knows internal IPs)                    │
        │                                  │
        │ DNS only, no access              │
        ▼                                  │
   ┌──────────┐                           │              ┌──────────────────┐
   │ Attacker │ ────── BLOCKED ───────────┼──────────── │ Services         │
   │          │  (no route to             │              │ 192.168.4.0/24   │
   └──────────┘   192.168.4.x)            │              └──────────────────┘
                                          │                      ▲
                                          │                      │
   ┌──────────┐                           │                      │
   │ Nikhil   │ ──── Tailscale ───────────┼──────────────────────┘
   │ (away)   │      authenticated        │
   └──────────┘                           │
                                          │
   ┌──────────┐                           │              ┌──────────────────┐
   │ Nikhil   │ ────── Direct ────────────┼──────────── │ Services         │
   │ (home)   │                           │              │ 192.168.4.0/24   │
   └──────────┘                           │              └──────────────────┘


   TRUST MODEL:
   ─────────────
   1. Tailscale = authentication (only devices in my tailnet can reach services)
   2. TLS = encryption (valid certs, no MITM)
   3. OAuth = authorization (optional, for Grafana user identity)

   NO PUBLIC EXPOSURE:
   ────────────────────
   - No port forwarding on router
   - No Cloudflare Tunnel
   - No public ingress
   - Services literally unreachable from internet
```

---

## Implementation Order

| Step | Component | Depends On | Estimated Effort |
|------|-----------|------------|------------------|
| 1 | cert-manager deployment | - | Small |
| 2 | ClusterIssuer (Cloudflare) | Step 1 | Small |
| 3 | Wildcard Certificate | Step 2 | Small |
| 4 | Traefik TLS config | Step 3 | Small |
| 5 | HA IngressRoute | Step 4 | Small |
| 6 | Update HA app URL | Step 5 | Trivial |
| 7 | Test from Tailscale | Step 5 | Testing |
| 8 | Grafana OAuth (optional) | Step 4 | Medium |

---

## Known Gotchas

| Issue | Mitigation |
|-------|------------|
| Subnet overlap (coffee shop uses 192.168.4.x) | Rare; if happens, use exit node or migrate to 10.77.x.x |
| Tailscale client not accepting routes | Check Tailscale admin: enable subnet routes for your device |
| OAuth redirect mismatch | Ensure Grafana `root_url` matches registered callback |
| Mobile app strict TLS | cert-manager + Traefik serve full chain (should be fine) |
| Cert renewal | cert-manager auto-renews 30 days before expiry |

---

## Files Created (Actual Implementation)

```
gitops/clusters/homelab/
├── infrastructure/
│   ├── cert-manager/              # HelmRelease only (Step 1)
│   │   ├── namespace.yaml
│   │   ├── helmrepository.yaml    # jetstack
│   │   ├── helmrelease.yaml       # cert-manager v1.16.x
│   │   ├── cloudflare-secret.yaml # SOPS encrypted
│   │   └── kustomization.yaml
│   │
│   ├── cert-manager-config/       # CRD resources (Step 2)
│   │   ├── flux-kustomization.yaml  # <-- KEY: dependsOn for ordering
│   │   ├── kustomization.yaml
│   │   └── resources/
│   │       ├── kustomization.yaml
│   │       ├── clusterissuer.yaml
│   │       ├── wildcard-certificate.yaml
│   │       └── wildcard-home-certificate.yaml
│   │
│   ├── traefik/                   # TODO: Add TLS config
│   └── external-dns/
│       └── ...
├── apps/
│   └── external-services/         # TODO: HA IngressRoute
└── kustomization.yaml             # References both cert-manager dirs
```

### Key Pattern: Flux dependsOn for CRD Ordering

**Problem**: Flux applies all resources simultaneously, but `ClusterIssuer` and `Certificate` CRDs don't exist until cert-manager HelmRelease installs them.

**Solution**: Split into two directories with a Flux Kustomization that has `dependsOn`:

```yaml
# cert-manager-config/flux-kustomization.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: cert-manager-config
  namespace: flux-system
spec:
  path: ./gitops/clusters/homelab/infrastructure/cert-manager-config/resources
  dependsOn:
    - name: flux-system   # Wait for main kustomization (which deploys HelmRelease)
  healthChecks:
    - apiVersion: helm.toolkit.fluxcd.io/v2
      kind: HelmRelease
      name: cert-manager
      namespace: cert-manager
```

**Reference**: [Flux CRD Ordering Discussion](https://github.com/fluxcd/flux2/discussions/2282)

---

## Validation Checklist

| Test | Command/Action | Expected |
|------|----------------|----------|
| cert-manager running | `kubectl get pods -n cert-manager` | 3 pods Running |
| Certificate issued | `kubectl get cert -n cert-manager` | Ready=True |
| Grafana HTTPS (home) | `curl https://grafana.app.home.panderosystems.com` | 200, valid cert |
| Grafana HTTPS (away) | Phone + Tailscale | Same as home |
| HA via Traefik | `curl https://ha.home.panderosystems.com` | HA page |
| HA app (home) | iPhone app | Connects, green lock |
| HA app (away) | iPhone + Tailscale | Same as home |

---

## References

- [LetsEncrypt DNS-01 Challenge](https://letsencrypt.org/docs/challenge-types/)
- [cert-manager Cloudflare](https://cert-manager.io/docs/configuration/acme/dns01/cloudflare/)
- [Tailscale Subnet Routers](https://tailscale.com/kb/1019/subnets)
- [Traefik External Services](https://doc.traefik.io/traefik/routing/services/)
- [Grafana Google OAuth](https://grafana.com/docs/grafana/latest/setup-grafana/configure-access/configure-authentication/google/)

---

---

## THE WAY: Standard Service Exposure Pattern

This architecture establishes **the standard pattern** for exposing any service in the homelab—whether it's a K3s pod, a VM, or an LXC container.

### Core Principles

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              CORE PRINCIPLES                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘

   1. NO INTERNET EXPOSURE - EVER
      ─────────────────────────────
      • No port forwarding on router
      • No Cloudflare Tunnel
      • No public ingress
      • Services are UNREACHABLE from the internet

   2. TWO ACCESS METHODS ONLY
      ─────────────────────────────
      • At home: Direct LAN access (192.168.4.x)
      • Away: Tailscale VPN (same IPs via subnet router)

   3. ONE WILDCARD DNS RECORD
      ─────────────────────────────
      • *.app.home.panderosystems.com → 192.168.4.80
      • Never touch DNS when adding services

   4. ONE WILDCARD CERTIFICATE
      ─────────────────────────────
      • *.app.home.panderosystems.com (LetsEncrypt via DNS-01)
      • Never request new certs when adding services

   5. TRAEFIK IS THE GATEWAY
      ─────────────────────────────
      • ALL services go through Traefik
      • Traefik handles TLS termination
      • Traefik routes based on Host header
```

### Traffic Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              TRAFFIC FLOW                                            │
└─────────────────────────────────────────────────────────────────────────────────────┘

                              INTERNET
                                 │
                                 │  ❌ BLOCKED
                                 │  (no port forwarding, no tunnel, nothing)
                                 │
                    ─────────────┴─────────────


   ┌──────────────────────────────────────────────────────────────────────┐
   │                         ACCESS METHODS                               │
   │                                                                      │
   │   ┌─────────────┐                          ┌─────────────┐          │
   │   │  AT HOME    │                          │    AWAY     │          │
   │   │  (LAN)      │                          │ (Tailscale) │          │
   │   └──────┬──────┘                          └──────┬──────┘          │
   │          │                                        │                  │
   │          │  Direct route                          │  WireGuard       │
   │          │  192.168.4.x                           │  tunnel          │
   │          │                                        │                  │
   │          └────────────────┬───────────────────────┘                  │
   │                           │                                          │
   │                           ▼                                          │
   │              ┌────────────────────────┐                              │
   │              │    CLOUDFLARE DNS      │                              │
   │              │                        │                              │
   │              │ *.app.home.pandero...  │                              │
   │              │      → 192.168.4.80    │                              │
   │              └───────────┬────────────┘                              │
   │                          │                                           │
   │                          ▼                                           │
   │              ┌────────────────────────┐                              │
   │              │       TRAEFIK          │                              │
   │              │    192.168.4.80        │                              │
   │              │                        │                              │
   │              │  • TLS termination     │                              │
   │              │  • Wildcard cert       │                              │
   │              │  • Host-based routing  │                              │
   │              └───────────┬────────────┘                              │
   │                          │                                           │
   │     ┌────────────────────┼────────────────────┐                     │
   │     │                    │                    │                      │
   │     ▼                    ▼                    ▼                      │
   │ ┌────────┐          ┌────────┐          ┌────────┐                  │
   │ │  K3s   │          │  VMs   │          │  LXCs  │                  │
   │ │  Pods  │          │ (HAOS, │          │(Frigate│                  │
   │ │        │          │ Rancher)│         │  etc)  │                  │
   │ └────────┘          └────────┘          └────────┘                  │
   │                                                                      │
   │  Ingress            ExternalName         ExternalName               │
   │  (auto)             + IngressRoute       + IngressRoute             │
   └──────────────────────────────────────────────────────────────────────┘
```

### Adding Services: Decision Tree

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         ADDING A NEW SERVICE                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘

   Want to expose a service at: myservice.app.home.panderosystems.com

                    ┌─────────────────────┐
                    │  Where does the     │
                    │  service run?       │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │   K3s    │    │    VM    │    │   LXC    │
        │   Pod    │    │  (HAOS,  │    │ (Frigate │
        │          │    │  Rancher)│    │   etc)   │
        └────┬─────┘    └────┬─────┘    └────┬─────┘
             │               │               │
             ▼               ▼               ▼
        ┌──────────┐    ┌──────────────────────────┐
        │ Create   │    │ Create:                  │
        │ Ingress  │    │ 1. ExternalName Service  │
        │          │    │ 2. IngressRoute          │
        └────┬─────┘    └────────────┬─────────────┘
             │                       │
             └───────────┬───────────┘
                         │
                         ▼
                    ┌─────────┐
                    │  DONE   │
                    │         │
                    │ No DNS  │
                    │ No cert │
                    │ No port │
                    │ forward │
                    └─────────┘
```

### Pattern A: K3s-Native Service (Automatic)

For services running as K3s pods, just create an Ingress:

```yaml
# gitops/clusters/homelab/apps/my-service/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-service
  namespace: my-service
  annotations:
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
    - hosts:
        - myservice.app.home.panderosystems.com
      secretName: wildcard-app-home-tls  # Shared wildcard cert
  rules:
    - host: myservice.app.home.panderosystems.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-service
                port:
                  number: 8080
```

**That's it.** Traefik picks it up automatically.

### Pattern B: External Service (VM/LXC/Other)

For services NOT in K3s (HAOS, Proxmox, LXCs, etc.), create two resources:

```yaml
# gitops/clusters/homelab/apps/external-services/homeassistant.yaml
---
# 1. Service pointing to external IP
apiVersion: v1
kind: Service
metadata:
  name: homeassistant-external
  namespace: external-services
spec:
  type: ExternalName
  externalName: 192.168.4.240  # HA VM IP
  ports:
    - port: 8123
      targetPort: 8123

---
# 2. IngressRoute for Traefik
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: homeassistant
  namespace: external-services
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`ha.home.panderosystems.com`)
      kind: Rule
      services:
        - name: homeassistant-external
          port: 8123
  tls:
    secretName: wildcard-app-home-tls  # Shared wildcard cert
```

### Quick Reference: Common External Services

| Service | IP | Port | FQDN |
|---------|-----|------|------|
| Home Assistant | 192.168.4.240 | 8123 | ha.home.panderosystems.com |
| Proxmox (pve) | 192.168.4.x | 8006 | pve.home.panderosystems.com |
| OPNsense | 192.168.4.1 | 443 | opnsense.home.panderosystems.com |
| MAAS | 192.168.4.53 | 5240 | maas.home.panderosystems.com |
| Frigate (LXC) | 192.168.4.x | 5000 | frigate.app.home.panderosystems.com |

### What You NEVER Do

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              NEVER DO THIS                                           │
└─────────────────────────────────────────────────────────────────────────────────────┘

   ❌ Port forward on router
   ❌ Expose services to internet
   ❌ Use Cloudflare Tunnel for access
   ❌ Create new DNS records for each service (wildcard handles it)
   ❌ Request new certificates for each service (wildcard handles it)
   ❌ Install certs directly on VMs/LXCs (Traefik terminates TLS)
   ❌ Use different URLs at home vs away
   ❌ Use IP addresses in bookmarks/configs (use FQDNs)
   ❌ Bypass Traefik for HTTPS services
```

### What You ALWAYS Do

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              ALWAYS DO THIS                                          │
└─────────────────────────────────────────────────────────────────────────────────────┘

   ✅ Route through Traefik (TLS termination)
   ✅ Use *.app.home.panderosystems.com naming
   ✅ Use the shared wildcard certificate
   ✅ Access via Tailscale when away
   ✅ Use FQDNs in all configs (HA integrations, etc.)
   ✅ Document new services in external-services/ if non-K3s
```

### Namespace Convention

```
gitops/clusters/homelab/apps/
├── grafana/              # K3s native - has Ingress
├── ollama/               # K3s native - has Ingress
├── frigate/              # K3s native - has Ingress
├── external-services/    # Non-K3s services
│   ├── homeassistant.yaml
│   ├── proxmox.yaml
│   ├── opnsense.yaml
│   └── maas.yaml
└── ...
```

---

## Tags

`architecture, seamless-access, cert-manager, tailscale, letsencrypt, dns-01, traefik, oauth, homelab, the-way, service-exposure, ingress, externalname`
