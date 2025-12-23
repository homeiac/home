# Using Cloudflare DNS to Bypass Homelab DNS Hell

**Date**: 2025-12-22
**Tags**: dns, cloudflare, external-dns, kubernetes, maas, homelab

## The Problem

Fake TLDs like `.homelab` or `.local` seem convenient for internal services, but they're a nightmare when you have multiple DNS servers that don't play nice together.

My setup:
- **OPNsense** (192.168.4.1) - Unbound DNS with `.homelab` overrides
- **MAAS** (192.168.4.53) - Bind9 for `.maas` zone
- **K8s CoreDNS** - Forwards to MAAS
- **Devices on different subnets** - Some use OPNsense, some use MAAS

The failure mode: K8s pods couldn't resolve `.homelab` names because:

1. CoreDNS forwards to MAAS
2. MAAS Bind9 sees `.homelab` as a "real" TLD
3. Bind9 queries root servers for `.homelab` authoritative NS
4. Root servers return NXDOMAIN (no such TLD)
5. Bind9 caches the NXDOMAIN and never tries forwarders

The "fix" was adding a forward zone in MAAS, but MAAS regenerates its config on restart. Fragile.

## The Solution: Use a Real Domain

Instead of fighting DNS servers, I used a domain I already own (`panderosystems.com`) and let Cloudflare handle it.

### Step 1: Deploy external-dns

external-dns syncs DNS records from Kubernetes to cloud providers. GitOps setup:

```yaml
# gitops/clusters/homelab/infrastructure/external-dns/helmrelease.yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: external-dns
  namespace: external-dns
spec:
  chart:
    spec:
      chart: external-dns
      version: "1.15.x"
      sourceRef:
        kind: HelmRepository
        name: external-dns
        namespace: flux-system
  values:
    provider:
      name: cloudflare
    env:
      - name: CF_API_TOKEN
        valueFrom:
          secretKeyRef:
            name: cloudflare-api-token
            key: api-token
    sources:
      - ingress
      - crd
    domainFilters:
      - panderosystems.com
    txtOwnerId: homelab-k3s
    policy: sync
```

### Step 2: Create Cloudflare API Token

1. Go to https://dash.cloudflare.com/profile/api-tokens
2. Create token with **Zone:DNS:Edit** permission
3. Scope to your domain
4. Store as SOPS-encrypted secret:

```yaml
# cloudflare-secret.yaml (encrypted with SOPS)
apiVersion: v1
kind: Secret
metadata:
  name: cloudflare-api-token
  namespace: external-dns
stringData:
  api-token: ENC[AES256_GCM,data:...,type:str]
```

### Step 3: Define DNS Records with CRDs

The DNSEndpoint CRD lets you define DNS records declaratively:

```yaml
# dnsendpoints.yaml
apiVersion: externaldns.k8s.io/v1alpha1
kind: DNSEndpoint
metadata:
  name: homelab-services
  namespace: external-dns
spec:
  endpoints:
    # Wildcard for Traefik ingress
    - dnsName: "*.app.home.panderosystems.com"
      recordType: A
      targets:
        - 192.168.4.80
      recordTTL: 300
    # Direct device access
    - dnsName: reolink-vdb.home.panderosystems.com
      recordType: A
      targets:
        - 192.168.1.10
      recordTTL: 300
    - dnsName: opnsense.home.panderosystems.com
      recordType: A
      targets:
        - 192.168.4.1
      recordTTL: 300
```

### Step 4: Verify

```bash
# Query Cloudflare directly
dig +short reolink-vdb.home.panderosystems.com @1.1.1.1
# 192.168.1.10

# From K8s pod
kubectl exec -n frigate deployment/frigate -- getent hosts reolink-vdb.home.panderosystems.com
# 192.168.1.10    reolink-vdb.home.panderosystems.com
```

## Why This Works

1. **Real TLD**: `.com` is a real TLD, so DNS servers behave normally
2. **Authoritative**: Cloudflare is the authoritative NS for your domain
3. **Universal**: Works from any device that can reach the internet
4. **No local config**: No need to configure OPNsense, MAAS, or CoreDNS
5. **GitOps friendly**: DNS records are version controlled

## Gotchas

### CRD Not Included in Chart

The external-dns helm chart doesn't install the DNSEndpoint CRD. You need to add it manually with the `api-approved.kubernetes.io` annotation:

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: dnsendpoints.externaldns.k8s.io
  annotations:
    api-approved.kubernetes.io: "https://github.com/kubernetes-sigs/external-dns/pull/2007"
```

### OPNsense DNS over TLS

If OPNsense uses DNS over TLS, make sure the forwarders are **enabled** (checkbox checked). I had them configured but not enabled - queries went nowhere.

### Local DNS Cache

After adding records, flush caches:
- Mac: `sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder`
- OPNsense: Services → Unbound DNS → restart service

### Private IPs in Public DNS

Yes, this puts private IPs (192.168.x.x) in public DNS. This is fine:
- The IPs are only routable from your network
- No security risk - attackers can't reach them anyway
- Split-horizon DNS is overrated for homelabs

## Cost

Free. Cloudflare's free tier includes:
- Unlimited DNS queries
- API access
- No rate limits for reasonable usage

## Summary

| Approach | Pros | Cons |
|----------|------|------|
| `.homelab` with Unbound | Simple setup | Doesn't work from K8s, fragile |
| MAAS forward zones | Centralized | MAAS regenerates config on restart |
| **Cloudflare + external-dns** | Works everywhere, GitOps | Requires domain, public DNS |

Stop fighting your DNS servers. Use a real domain and let Cloudflare handle it.

## Files

- `gitops/clusters/homelab/infrastructure/external-dns/` - Full external-dns setup
- `docs/architecture/reolink-doorbell-network.md` - Device-specific DNS documentation
