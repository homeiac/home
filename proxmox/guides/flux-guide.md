# Bootstrapping Flux v2 in Your Homelab

This guide walks you through installing and configuring Flux v2 in your homelab GitOps setup under `clusters/homelab/`.

## 1. Prerequisites

- A Kubernetes cluster with `kubectl` access  
- A Git repository for your manifests (e.g., GitHub `homeiac/home`)  
- Flux CLI installed locally (`brew install fluxcd/tap/flux` on macOS)  

## 2. Bootstrap Flux

```bash
flux bootstrap github \
  --owner=YOUR_GITHUB_USER \
  --repository=home \
  --branch=master \
  --path=gitops/clusters/homelab/flux-system \
  --personal
```

This installs Flux controllers and commits:
- `gotk-components.yaml` & `gotk-sync.yaml` under `flux-system`
- A `GitRepository` and initial `Kustomization`

## 3. Repository Layout

```
gitops/
└── clusters/
    └── homelab/
        ├── flux-system/
        │   ├── gotk-components.yaml
        │   ├── gotk-sync.yaml
        │   └── kustomization.yaml
        └── kustomization.yaml    ← points to ../flux-system
```

`flux-system/kustomization.yaml`:
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
metadata:
  name: homelab
  namespace: flux-system
spec:
  interval: 10m
  path: ../        # Watch everything under homelab/
  prune: true
  sourceRef:
    kind: GitRepository
    name: flux-system
```

## 4. Verify Flux

```bash
flux check --pre
flux get sources git -A
flux get kustomizations -A
```

## 5. Suspend/Resume

```bash
flux suspend kustomization homelab -n flux-system
flux resume kustomization homelab -n flux-system
```

## 6. Workflow

1. **Make changes** under `clusters/homelab/`.  
2. **Commit & push** to `master`.  
3. Flux auto-applies (or run `flux reconcile`).  

## 7. Troubleshooting

- **Build failures** → check `path` and `apiVersion`.  
- **Missing CRDs** → use `dependsOn` in Kustomization:
  ```yaml
  spec:
    dependsOn:
      - name: metallb
        namespace: flux-system
  ```  
- **No sync** → verify `GitRepository` URL, branch, and path.
