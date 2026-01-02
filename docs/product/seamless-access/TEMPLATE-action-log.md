# Action Log: Seamless Homelab Access Implementation

**Date Started**: YYYY-MM-DD
**Date Completed**:
**Status**: In Progress / Completed / Blocked

---

## Pre-Flight Checklist

| Check | Command | Expected | Actual | Status |
|-------|---------|----------|--------|--------|
| external-dns running | `kubectl get pods -n external-dns` | 1/1 Running | | |
| Tailscale subnet router | `kubectl get connector -n tailscale` | homelab-subnet-router Ready | | |
| Cloudflare API token | `kubectl get secret -n external-dns cloudflare-api-token` | exists | | |
| DNS resolves | `dig grafana.app.home.panderosystems.com` | 192.168.4.80 | | |
| Traefik running | `kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik` | Running | | |

---

## Step 1: Deploy cert-manager

**Start Time**:
**End Time**:

### Commands Run

```bash
# Check if namespace exists
kubectl get ns cert-manager

# Apply via Flux (after committing manifests)
git add gitops/clusters/homelab/infrastructure/cert-manager/
git commit -m "feat: add cert-manager with Cloudflare DNS-01"
git push

# Watch reconciliation
flux reconcile kustomization flux-system --with-source
kubectl get pods -n cert-manager -w
```

### Verification

| Check | Command | Expected | Actual |
|-------|---------|----------|--------|
| cert-manager pods | `kubectl get pods -n cert-manager` | 3 pods Running | |
| CRDs installed | `kubectl get crd certificates.cert-manager.io` | exists | |
| ClusterIssuer ready | `kubectl get clusterissuer letsencrypt-prod` | Ready=True | |

### Notes / Issues

-

---

## Step 2: Create Wildcard Certificate

**Start Time**:
**End Time**:

### Commands Run

```bash
# Check certificate status
kubectl get certificate -n cert-manager
kubectl describe certificate wildcard-app-home -n cert-manager

# Check challenges
kubectl get challenges -A
```

### Verification

| Check | Command | Expected | Actual |
|-------|---------|----------|--------|
| Certificate Ready | `kubectl get cert wildcard-app-home -n cert-manager` | Ready=True | |
| Secret created | `kubectl get secret wildcard-app-home-tls -n cert-manager` | exists | |
| TXT record appeared | `dig _acme-challenge.app.home.panderosystems.com TXT` | acme challenge | |

### Notes / Issues

-

---

## Step 3: Configure Traefik TLS

**Start Time**:
**End Time**:

### Commands Run

```bash
# Update Traefik to use the wildcard cert
kubectl apply -f gitops/clusters/homelab/infrastructure/traefik/...

# Restart Traefik to pick up changes
kubectl rollout restart deployment traefik -n kube-system
```

### Verification

| Check | Command | Expected | Actual |
|-------|---------|----------|--------|
| Traefik has cert | `curl -v https://grafana.app.home.panderosystems.com 2>&1 \| grep subject` | CN=*.app.home... | |
| No browser warning | Open in browser | Green lock | |

### Notes / Issues

-

---

## Step 4: Route HA Through Traefik

**Start Time**:
**End Time**:

### Commands Run

```bash
# Create IngressRoute for HA
kubectl apply -f ...

# Test
curl -v https://ha.home.panderosystems.com
```

### Verification

| Check | Command | Expected | Actual |
|-------|---------|----------|--------|
| HA accessible via Traefik | `curl -s https://ha.home.panderosystems.com` | HA page | |
| HA app works | Test on phone | Connects | |

### Notes / Issues

-

---

## Step 5: Test Tailscale Access

**Start Time**:
**End Time**:

### Test Procedure

1. Disconnect from home WiFi
2. Connect to phone hotspot (different network)
3. Enable Tailscale
4. Test access

### Verification

| Check | URL | Expected | Actual |
|-------|-----|----------|--------|
| Grafana | `https://grafana.app.home.panderosystems.com` | Loads with valid cert | |
| Frigate | `https://frigate.app.home.panderosystems.com` | Loads with valid cert | |
| HA | `https://ha.home.panderosystems.com` | Loads with valid cert | |
| HA App | iPhone HA app | Connects | |

### Notes / Issues

-

---

## Step 6: Configure Google OAuth (Optional)

**Start Time**:
**End Time**:

### Commands Run

```bash
# Update Grafana config
kubectl apply -f ...
```

### Verification

| Check | Expected | Actual |
|-------|----------|--------|
| Google login button | Appears on Grafana login | |
| OAuth flow works | Can login with Google | |
| Callback works via Tailscale | Works from remote | |

### Notes / Issues

-

---

## Rollback Plan

If things break:

```bash
# Revert to previous state
git revert HEAD
git push
flux reconcile kustomization flux-system --with-source

# Or manually delete resources
kubectl delete certificate wildcard-app-home -n cert-manager
kubectl delete clusterissuer letsencrypt-prod
```

---

## Post-Implementation Checklist

| Check | Status |
|-------|--------|
| All services accessible at home | |
| All services accessible via Tailscale | |
| No browser cert warnings | |
| HA app works (home + away) | |
| Certs auto-renew (check in 60 days) | |
| OpenMemory updated with solution | |

---

## Lessons Learned

-

---

## Tags

`seamless-access, cert-manager, tailscale, letsencrypt, action-log`
