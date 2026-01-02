# Action Log: Seamless Homelab Access Implementation

**Date Started**: 2026-01-01
**Date Completed**: Part 1 complete (2026-01-01)
**Status**: In Progress - cert-manager deployed, certs issued

---

## Pre-Flight Checklist

| Check | Command | Expected | Actual | Status |
|-------|---------|----------|--------|--------|
| external-dns running | `kubectl get pods -n external-dns` | 1/1 Running | 1/1 Running | PASS |
| Tailscale subnet router | `kubectl get connector -n tailscale` | homelab-subnet-router Ready | Ready | PASS |
| Cloudflare API token | `kubectl get secret -n external-dns cloudflare-api-token` | exists | exists (SOPS encrypted) | PASS |
| Traefik running | `kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik` | Running | Running | PASS |

---

## Step 1: Deploy cert-manager

**Start Time**: 2026-01-01 ~15:00 PST
**End Time**: 2026-01-01 ~15:35 PST

### Commands Run

```bash
# Created GitOps files
gitops/clusters/homelab/infrastructure/cert-manager/
  - namespace.yaml
  - helmrepository.yaml (jetstack)
  - helmrelease.yaml (cert-manager v1.16.x)
  - cloudflare-secret.yaml (SOPS encrypted, copied from external-dns)
  - kustomization.yaml

# Committed and pushed
git add gitops/clusters/homelab/infrastructure/cert-manager/
git commit -m "feat(cert-manager): add cert-manager with Cloudflare DNS-01"
git push

# Triggered Flux reconciliation
flux reconcile source git flux-system
flux reconcile kustomization flux-system
```

### Issues Encountered

1. **Missing kustomization.yaml include**: First commit didn't include cert-manager in main kustomization.yaml
   - Fixed: Added `- infrastructure/cert-manager` to gitops/clusters/homelab/kustomization.yaml

2. **CRD ordering issue**: ClusterIssuer/Certificate failed because CRDs don't exist until HelmRelease installs them
   - Error: `no matches for kind "Certificate" in version "cert-manager.io/v1"`
   - Fixed: Split into two directories with Flux Kustomization dependsOn pattern

### Verification

| Check | Command | Expected | Actual |
|-------|---------|----------|--------|
| cert-manager pods | `kubectl get pods -n cert-manager` | 3 pods Running | cert-manager, cainjector, webhook all 1/1 Running |
| CRDs installed | `kubectl get crd certificates.cert-manager.io` | exists | PASS |
| HelmRelease ready | `flux get helmreleases -n cert-manager` | Ready=True | Ready, v1.16.5 |

---

## Step 2: Fix CRD Ordering with dependsOn Pattern

**Start Time**: 2026-01-01 ~15:35 PST
**End Time**: 2026-01-01 ~15:45 PST

### Solution

Per [Flux docs](https://github.com/fluxcd/flux2/discussions/2282), dependencies must be same type.
Created separate Flux Kustomization with dependsOn:

```
infrastructure/cert-manager/          # HelmRelease only
infrastructure/cert-manager-config/
  ├── flux-kustomization.yaml         # Flux Kustomization with dependsOn + healthCheck
  ├── kustomization.yaml              # Points to flux-kustomization.yaml
  └── resources/
      ├── kustomization.yaml          # The actual CRD resources
      ├── clusterissuer.yaml
      ├── wildcard-certificate.yaml
      └── wildcard-home-certificate.yaml
```

Key config in flux-kustomization.yaml:
```yaml
spec:
  dependsOn:
    - name: flux-system
  healthChecks:
    - apiVersion: helm.toolkit.fluxcd.io/v2
      kind: HelmRelease
      name: cert-manager
      namespace: cert-manager
```

---

## Step 3: Create Wildcard Certificates

**Start Time**: 2026-01-01 ~15:45 PST
**End Time**: 2026-01-01 ~15:50 PST

### Commands Run

```bash
# Triggered reconciliation
flux reconcile kustomization cert-manager-config

# Watched certificate progress
kubectl get certificates -n cert-manager -w
kubectl get challenges -n cert-manager
```

### Verification

| Check | Command | Expected | Actual |
|-------|---------|----------|--------|
| ClusterIssuer Ready | `kubectl get clusterissuer letsencrypt-prod` | Ready=True | Ready=True |
| wildcard-app-home | `kubectl get cert wildcard-app-home -n cert-manager` | Ready=True | Ready=True (5m) |
| wildcard-home | `kubectl get cert wildcard-home -n cert-manager` | Ready=True | Ready=True (5m) |
| TLS secret exists | `kubectl get secret wildcard-app-home-tls -n cert-manager` | exists | PASS |

### DNS-01 Challenge Flow Observed

1. cert-manager created CertificateRequest
2. ACME order created with LetsEncrypt
3. Challenges created (2 per cert: wildcard + apex)
4. Cloudflare API used to create TXT records (Presented=true)
5. LetsEncrypt validated TXT records
6. Certificates issued and stored as secrets

---

## Summary - Part 1 Complete

### What's Working
- cert-manager v1.16.5 deployed via Flux HelmRelease
- ClusterIssuer `letsencrypt-prod` with Cloudflare DNS-01 solver
- Wildcard certificate `*.app.home.panderosystems.com` - ISSUED
- Wildcard certificate `*.home.panderosystems.com` - ISSUED
- SOPS encryption working for secrets

### What's Next (Part 2)
- [ ] Configure Traefik to use wildcard certs
- [ ] Route HA through Traefik (ExternalName Service)
- [ ] Test from Tailscale
- [ ] Configure Grafana Google OAuth

---

## Lessons Learned

1. **Always check git diff before push**: Forgot to add kustomization.yaml change to first commit
2. **CRD ordering requires dependsOn pattern**: Can't deploy CRD instances in same kustomization as the CRD source
3. **DNS-01 takes ~2-3 minutes**: DNS propagation delay is normal
4. **SOPS key location**: Authoritative key is in K8s secret `flux-system/sops-age`, not filesystem backups

---

## Tags

`seamless-access, cert-manager, tailscale, letsencrypt, action-log, dns-01, cloudflare, flux, dependsOn`
