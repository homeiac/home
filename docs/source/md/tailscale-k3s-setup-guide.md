# Tailscale K3s Subnet Router Setup Guide

## Overview

This guide documents the deployment of Tailscale as a subnet router on a K3s cluster using GitOps (Flux). The setup enables secure remote access to the entire homelab network (192.168.4.0/24) from any device on the Tailscale network, solving network segmentation issues where devices on different subnets cannot communicate directly.

## Problem Statement

### Original Issue
- Home Assistant VM runs on 192.168.4.240 (homelab network)
- Android phone connects to Google WiFi on 192.168.86.x network
- A Flint 3 router in bridge mode was supposed to connect these networks but failed to forward traffic properly
- Result: Phone could not access Home Assistant despite being "on the same network"

### Solution
Deploy Tailscale as a subnet router on K3s to create a secure overlay network that bypasses the broken bridge configuration.

## Architecture

```
                          ☁️  TAILSCALE CLOUD
                                  │
            ┌─────────────────────┼─────────────────────┐
            │                     │                     │
            ▼                     ▼                     ▼
      ┌──────────┐         ┌──────────┐         ┌──────────────┐
      │ ANDROID  │         │   MAC    │         │   K3S POD    │
      │  PHONE   │         │  (Dev)   │         │ ts-homelab-  │
      │          │         │          │         │   router     │
      │ [CLIENT] │         │ [CLIENT] │         │              │
      └────┬─────┘         └────┬─────┘         │ [SUBNET RTR] │
           │                    │               │ [EXIT NODE]  │
           │                    │               └──────┬───────┘
           └────────────────────┼──────────────────────┘
                                │
                    ════════════╧════════════
                         TAILNET MESH
                    ═════════════════════════
                                │
               Advertised Routes (via Connector CRD):
               • 192.168.4.0/24   (homelab LAN)
               • 10.42.0.0/16     (K3s pods)
               • 10.43.0.0/16     (K3s services)
                                │
     ┌──────────────────────────┼──────────────────────────┐
     │                          │                          │
     ▼                          ▼                          ▼
 ┌────────┐              ┌────────────┐             ┌───────────┐
 │   HA   │              │  PROXMOX   │             │    K3S    │
 │  VM    │              │   HOSTS    │             │ SERVICES  │
 │.4.240  │              │ .4.17-.172 │             │ .4.80-120 │
 └────────┘              └────────────┘             └───────────┘
```

## Prerequisites

- K3s cluster with Flux GitOps configured
- Tailscale account (free tier supports up to 100 devices)
- kubectl access to the cluster
- Git access to the GitOps repository

## Implementation Steps

### Phase 0: Tailnet Configuration (Do First!)

**CRITICAL**: Configure your tailnet name BEFORE adding any devices. Changing it later breaks existing MagicDNS references.

1. Go to https://login.tailscale.com/admin/dns
2. Click "Rename tailnet"
3. Pick a memorable name from the generated options (e.g., `cool-homelab`)
4. Your devices will be accessible as `<hostname>.<tailnet-name>.ts.net`

**Note**: True custom domains (e.g., `ts.yourdomain.com`) require running coredns-tailscale plugin - not recommended for homelab complexity.

### Phase 1: Create OAuth Credentials

1. Go to https://login.tailscale.com/admin/settings/oauth
2. Click "Generate OAuth client..."
3. Configure:
   - **Description**: `k8s-operator`
   - **Scopes**:
     - Devices → Write
     - Auth Keys → Write
   - **Tags**: `tag:k8s-operator`
4. Click "Generate"
5. Save the Client ID and Client Secret securely

**Example credentials format:**
```
Client ID: k1kqL7xrmZ11CNTRL
Client Secret: tskey-client-k1kqL7xrmZ11CNTRL-QYp7agw5USi6Af7mvai4Mis8jEJ4y2YTN
```

### Phase 2: Create GitOps Manifests

Create the following directory structure:

```
gitops/clusters/homelab/infrastructure/tailscale/
├── kustomization.yaml
├── namespace.yaml
├── helmrepository.yaml
├── helmrelease.yaml
└── connector.yaml
```

#### namespace.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: tailscale
  labels:
    app.kubernetes.io/name: tailscale
    app.kubernetes.io/part-of: homelab
```

#### helmrepository.yaml

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: tailscale
  namespace: flux-system
spec:
  interval: 30m
  url: https://pkgs.tailscale.com/helmcharts
```

#### helmrelease.yaml

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: tailscale-operator
  namespace: tailscale
spec:
  interval: 10m
  install:
    createNamespace: true
    crds: Create
    remediation:
      retries: 3
  upgrade:
    crds: CreateReplace
    remediation:
      retries: 3
  chart:
    spec:
      chart: tailscale-operator
      version: "1.78.3"
      sourceRef:
        kind: HelmRepository
        name: tailscale
        namespace: flux-system
  values:
    # OAuth credentials referenced from manually-created secret
    oauth:
      clientIdSecretName: "operator-oauth"
      clientIdSecretKey: "client_id"
      clientSecretSecretName: "operator-oauth"
      clientSecretSecretKey: "client_secret"

    # Operator configuration
    operatorConfig:
      hostname: "ts-k8s-operator"
      logging: "info"

    # Enable API server proxy (optional, for secure kubectl)
    apiServerProxyConfig:
      mode: "false"
```

#### connector.yaml

```yaml
apiVersion: tailscale.com/v1alpha1
kind: Connector
metadata:
  name: homelab-subnet-router
  namespace: tailscale
spec:
  hostname: ts-homelab-router
  tags:
    - tag:k8s-operator
  subnetRouter:
    advertiseRoutes:
      - "192.168.4.0/24"    # Homelab LAN (Proxmox, HA, services)
      - "10.42.0.0/16"      # K3s pod CIDR
      - "10.43.0.0/16"      # K3s service CIDR
  exitNode: true
```

#### kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - namespace.yaml
  - helmrepository.yaml
  - helmrelease.yaml
  - connector.yaml  # CRDs installed by operator
  # NOTE: oauth-secret must be created manually:
  # kubectl create secret generic operator-oauth -n tailscale \
  #   --from-literal=client_id=YOUR_CLIENT_ID \
  #   --from-literal=client_secret=YOUR_CLIENT_SECRET
```

### Phase 3: Update Main Kustomization

Add tailscale to `gitops/clusters/homelab/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - flux-system
  - infrastructure/metallb
  - infrastructure/monitoring
  - infrastructure/traefik
  - infrastructure/tailscale             # Add this line
  - infrastructure-config/metallb-config
  - apps/ollama
  - apps/stable-diffusion
  - apps/samba
```

### Phase 4: Create OAuth Secret (Manual - Not in Git!)

**⚠️ SECURITY**: Never commit OAuth secrets to a public git repository!

Create the secret manually via kubectl BEFORE pushing the GitOps manifests:

```bash
# Create namespace first
kubectl create namespace tailscale

# Create the OAuth secret
kubectl create secret generic operator-oauth -n tailscale \
  --from-literal=client_id="YOUR_CLIENT_ID" \
  --from-literal=client_secret="YOUR_CLIENT_SECRET"
```

### Phase 5: Deploy via GitOps

```bash
# Commit and push (without secrets!)
git add gitops/clusters/homelab/infrastructure/tailscale/
git add gitops/clusters/homelab/kustomization.yaml
git commit -m "feat: add Tailscale operator for subnet routing and exit node"
git push origin master

# Trigger Flux reconciliation
flux reconcile kustomization flux-system --with-source
```

### Phase 6: Handle CRD Dependency Issue (Manual Workaround)

**Issue**: The Connector CRD doesn't exist until the Tailscale operator is installed. Flux may fail on first reconciliation with:

```
Connector/tailscale/homelab-subnet-router dry-run failed:
no matches for kind "Connector" in version "tailscale.com/v1alpha1"
```

**Workaround**:

1. Temporarily remove `connector.yaml` from kustomization.yaml
2. Push and wait for operator to deploy
3. Re-add `connector.yaml` to kustomization.yaml
4. Push again

Or apply connector manually after operator is running:

```bash
# Wait for operator to be ready
kubectl get pods -n tailscale

# Apply connector manually (one-time bootstrap)
kubectl apply -f gitops/clusters/homelab/infrastructure/tailscale/connector.yaml

# Then re-add to kustomization for GitOps management
```

### Phase 7: Approve Routes in Admin Console

1. Go to https://login.tailscale.com/admin/machines
2. Find the device `ts-homelab-router`
3. Click on it → "Edit route settings"
4. Enable these subnet routes:
   - ✅ `192.168.4.0/24` (homelab LAN)
   - ✅ `10.42.0.0/16` (K3s pods)
   - ✅ `10.43.0.0/16` (K3s services)
5. Enable "Use as exit node"
6. Save

### Phase 8: Enable MagicDNS

1. Go to https://login.tailscale.com/admin/dns
2. Enable MagicDNS
3. Devices now accessible as `<hostname>.<tailnet-name>.ts.net`

### Phase 9: Configure Client Devices

#### macOS

```bash
# Install Tailscale app
brew install --cask tailscale

# Open Tailscale from Applications, sign in
# Enable "Accept subnet routes" in preferences

# Verify connection
tailscale status

# Test connectivity
ping 192.168.4.240
curl http://192.168.4.240:8123/
```

#### Android

1. Install Tailscale from Play Store
2. Sign in with same account
3. Go to app Settings → Enable "Use subnet routes"
4. Test: Open browser to `http://192.168.4.240:8123`

## Verification

### Check Tailscale Status

```bash
tailscale status
```

Expected output:
```
100.117.152.118 your-mac              you@    macOS   -
100.65.140.21   ts-homelab-router    tagged-devices linux   idle; offers exit node
100.64.6.126    ts-k8s-operator      tagged-devices linux   -
```

### Check Kubernetes Resources

```bash
kubectl get connector,pods -n tailscale
```

Expected output:
```
NAME                                            SUBNETROUTES                               ISEXITNODE   STATUS
connector.tailscale.com/homelab-subnet-router   192.168.4.0/24,10.42.0.0/16,10.43.0.0/16   true         ConnectorCreated

NAME                                   READY   STATUS    RESTARTS   AGE
pod/operator-d9694899f-lxml2           1/1     Running   0          10m
pod/ts-homelab-subnet-router-rd96p-0   1/1     Running   0          9m
```

### Test Connectivity

```bash
# Ping Home Assistant
ping 192.168.4.240

# HTTP test
curl -s -o /dev/null -w '%{http_code}' http://192.168.4.240:8123/
# Expected: 200

# Ping Proxmox hosts
ping 192.168.4.17   # still-fawn
ping 192.168.4.19   # chief-horse
```

## Troubleshooting

### Connector CRD Not Found

**Error**: `no matches for kind "Connector" in version "tailscale.com/v1alpha1"`

**Solution**: Wait for operator to install CRDs, then apply connector:
```bash
kubectl wait --for=condition=ready pod -l app=operator -n tailscale --timeout=120s
kubectl apply -f connector.yaml
```

### Subnet Routes Not Working

1. Verify routes are approved in admin console
2. Check client has "Accept subnet routes" enabled
3. Verify connector status:
   ```bash
   kubectl describe connector homelab-subnet-router -n tailscale
   ```

### OAuth Authentication Failed

1. Verify secret exists and has correct keys:
   ```bash
   kubectl get secret operator-oauth -n tailscale -o yaml
   ```
2. Regenerate OAuth credentials if expired
3. Delete and recreate secret

### Pod Not Starting

Check operator logs:
```bash
kubectl logs -n tailscale -l app=operator
kubectl logs -n tailscale -l app=ts-homelab-router
```

## Security Considerations

1. **OAuth Secrets**: Never commit to public git repositories
   - Use kubectl to create secrets out-of-band
   - Consider sealed-secrets or external-secrets for production

2. **ACL Policies**: Configure Tailscale ACLs for fine-grained access control:
   ```json
   {
     "acls": [
       {"action": "accept", "src": ["*"], "dst": ["192.168.4.0/24:*"]}
     ],
     "autoApprovers": {
       "routes": {
         "192.168.4.0/24": ["tag:k8s-operator"]
       }
     }
   }
   ```

3. **Exit Node**: Only enable if you want to route all internet traffic through your homelab

## Files Reference

| File | Purpose |
|------|---------|
| `gitops/clusters/homelab/infrastructure/tailscale/namespace.yaml` | Tailscale namespace |
| `gitops/clusters/homelab/infrastructure/tailscale/helmrepository.yaml` | Helm chart source |
| `gitops/clusters/homelab/infrastructure/tailscale/helmrelease.yaml` | Operator deployment |
| `gitops/clusters/homelab/infrastructure/tailscale/connector.yaml` | Subnet router config |
| `gitops/clusters/homelab/infrastructure/tailscale/kustomization.yaml` | Kustomize bundle |
| `gitops/clusters/homelab/kustomization.yaml` | Main cluster config |

## Related Documentation

- [Tailscale Kubernetes Operator](https://tailscale.com/kb/1236/kubernetes-operator)
- [Subnet Routers](https://tailscale.com/kb/1019/subnets)
- [Exit Nodes](https://tailscale.com/kb/1103/exit-nodes)
- [MagicDNS](https://tailscale.com/kb/1081/magicdns)
- [Tailnet Names](https://tailscale.com/kb/1217/tailnet-name)

## Tags

tailscale, tailsacle, vpn, subnet-router, exit-node, k3s, kubernetes, k8s, kubernettes, gitops, flux, remote-access, home-assistant, homelab, network-segmentation

---

*Document created: 2025-12-05*
*Last updated: 2025-12-05*
