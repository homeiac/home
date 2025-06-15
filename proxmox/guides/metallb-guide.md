# Deploying MetalLB via Flux in Your Homelab

This guide covers deploying MetalLB (LoadBalancer implementation) using Flux v2.

## 1. Prerequisites

- Flux v2 already bootstrapped and watching `clusters/homelab/`.  
- `metallb-system` namespace will be created by the HelmRelease.

## 2. Add MetalLB HelmRepository & HelmRelease

Create `gitops/clusters/homelab/infrastructure/metallb/helmrepository.yaml`:

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: metallb
  namespace: flux-system
spec:
  interval: 30m
  url: https://metallb.github.io/metallb
```

Create `gitops/clusters/homelab/infrastructure/metallb/helmrelease.yaml`:

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: metallb
  namespace: metallb-system
spec:
  interval: 5m
  chart:
    spec:
      chart: metallb
      version: 0.15.x
      sourceRef:
        kind: HelmRepository
        name: metallb
        namespace: flux-system
  install:
    createNamespace: true
```

And a `kustomization.yaml` in the same folder:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - helmrepository.yaml
  - helmrelease.yaml
```

## 3. Configure IPAddressPool & L2Advertisement

Create `gitops/clusters/homelab/infrastructure-config/metallb/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - address-pool.yaml
  - l2-advertisement.yaml
```

`address-pool.yaml`:

```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: homelab-pool
  namespace: metallb-system
spec:
  addresses:
    - 192.168.4.50-192.168.4.70
```

`l2-advertisement.yaml`:

```yaml
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: homelab-l2
  namespace: metallb-system
```

## 4. Add Flux Kustomization

Under `clusters/homelab/flux-system/kustomization.yaml` ensure:

```yaml
resources:
  - ../infrastructure/metallb
  - ../infrastructure-config/metallb
```

Flux will install the chart first, then apply the config.

## 5. Verify Installation

```bash
kubectl -n metallb-system get pod
kubectl -n metallb-system get ipaddresspools,l2advertisements
```

## 6. Smoke Test

```bash
# Create a test LoadBalancer service
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: metallb-test
spec:
  selector:
    app: some-nonexistent
  ports:
    - port: 80
      targetPort: 9376
  type: LoadBalancer
EOF

# Wait for EXTERNAL-IP
kubectl get svc metallb-test --watch
```

You should see an IP from your pool (e.g., `192.168.4.51`).  

---

Deploying MetalLB via Flux ensures full GitOps control—changes to your pool or chart automatically reconcile on commit.
