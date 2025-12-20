# Crossplane + Proxmox: GitOps for VM Provisioning

**Date:** 2025-12-20
**Tags:** crossplane, proxmox, gitops, flux, kubernetes, infrastructure-as-code, homelab

## The Problem

Managing VMs and LXCs in Proxmox traditionally means:
- Clicking through the UI or running `qm create` commands
- No version control for infrastructure
- Manual tracking of what exists where
- Migration = manual backup/restore/DNS dance

What if VMs could be declared in Git, just like Kubernetes workloads?

## The Solution: Crossplane

Crossplane extends Kubernetes with the ability to provision infrastructure. Combined with Flux GitOps:

```
Git Repository
└── gitops/clusters/homelab/instances/
    ├── rancher-server.yaml     # New VM
    └── frigate-nvr.yaml        # Adopt existing LXC

        ↓ Flux syncs

K3s Cluster + Crossplane

        ↓ Crossplane reconciles

Proxmox VMs/LXCs
```

## Installation

### 1. Crossplane via Flux

```yaml
# gitops/clusters/homelab/infrastructure/crossplane/helmrelease.yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: crossplane
  namespace: crossplane-system
spec:
  chart:
    spec:
      chart: crossplane
      version: "1.18.2"
      sourceRef:
        kind: HelmRepository
        name: crossplane
        namespace: flux-system
```

### 2. Proxmox Provider

```yaml
# provider-proxmox.yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-proxmox-bpg
spec:
  package: xpkg.upbound.io/valkiriaaquaticamendi/provider-proxmox-bpg:v0.11.1
```

### 3. SOPS-Encrypted Credentials

Credentials stored in Git, encrypted with SOPS:

```bash
./scripts/crossplane/create-proxmox-secret-sops.sh
```

Creates a secret with JSON credentials:
```json
{
  "endpoint": "https://pumped-piglet.maas:8006",
  "api_token": "root@pam!provision-manage-vms=...",
  "insecure": "true"
}
```

## Creating New VMs

Declare a VM in YAML - Proxmox auto-assigns VMID:

```yaml
apiVersion: virtualenvironmentvm.crossplane.io/v1alpha1
kind: EnvironmentVM
metadata:
  name: my-new-vm
spec:
  forProvider:
    nodeName: pumped-piglet    # Which Proxmox host
    name: my-new-vm
    description: "Created via Crossplane"

    cpu:
      - cores: 4
        type: host

    memory:
      - dedicated: 8192

    disk:
      - interface: scsi0
        datastoreId: local-2TB-zfs
        size: 100

    networkDevice:
      - bridge: vmbr0
        model: virtio

    started: true

  providerConfigRef:
    name: default
```

Commit, push, Flux syncs, Crossplane creates the VM.

## Adopting Existing VMs

The key pattern - use `external-name` annotation:

```yaml
apiVersion: virtualenvironmentvm.crossplane.io/v1alpha1
kind: EnvironmentVM
metadata:
  name: rancher-server
  annotations:
    # This tells Crossplane to adopt existing VM, not create new
    crossplane.io/external-name: "200"
spec:
  forProvider:
    nodeName: pumped-piglet
    vmId: 200
    # ... rest of config

  # Don't delete Proxmox VM if CR is removed from Git
  deletionPolicy: Orphan
```

Crossplane observes the existing VM and syncs state.

## Importing Existing LXCs

Helper script generates YAML from existing containers:

```bash
./scripts/crossplane/import-lxc.sh 113 > frigate-nvr.yaml
```

Generates:
```yaml
apiVersion: virtualenvironmentcontainer.crossplane.io/v1alpha1
kind: EnvironmentContainer
metadata:
  name: frigate-nvr
  annotations:
    crossplane.io/external-name: "113"
spec:
  forProvider:
    nodeName: fun-bedbug
    # ... config extracted from existing LXC
  deletionPolicy: Orphan
```

## Host Selection

Pick your Proxmox node with `nodeName`:

| Host | Use Case |
|------|----------|
| `pumped-piglet` | General workloads, K3s VMs |
| `still-fawn` | GPU workloads (RTX 3070) |
| `fun-bedbug` | Coral TPU, Frigate |
| `chief-horse` | Home Assistant OS |

## Key Patterns

### New VM (Crossplane creates)
```yaml
spec:
  forProvider:
    nodeName: still-fawn
    # vmId: omit - Proxmox auto-assigns
```

### Adopt Existing (Crossplane observes)
```yaml
metadata:
  annotations:
    crossplane.io/external-name: "113"
spec:
  deletionPolicy: Orphan
```

### Delete VM when CR deleted
```yaml
spec:
  deletionPolicy: Delete  # default
```

### Keep VM when CR deleted
```yaml
spec:
  deletionPolicy: Orphan
```

## File Structure

```
gitops/clusters/homelab/
├── infrastructure/crossplane/
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── helmrepository.yaml
│   ├── helmrelease.yaml
│   ├── provider-proxmox.yaml
│   ├── proxmox-secret.yaml    # SOPS encrypted
│   └── provider-config.yaml
│
└── instances/
    ├── kustomization.yaml
    ├── rancher-server.yaml
    └── README.md

scripts/crossplane/
├── create-proxmox-secret-sops.sh
├── import-lxc.sh
└── install-provider.sh
```

## What's Next

- **Migration via Git**: Change `nodeName`, Crossplane recreates on new host
- **Compositions**: Abstract device requirements (GPU, TPU) into claims
- **Full GitOps**: Enable `instances/` in main kustomization for automatic sync

## Lessons Learned

1. **Provider CRDs need Crossplane first** - can't include Provider in same kustomization as Helm install
2. **Credentials format matters** - `insecure` must be string `"true"` not boolean
3. **external-name is the adoption key** - without it, Crossplane tries to create new
4. **deletionPolicy: Orphan for production** - safety net for adopted resources

## References

- [provider-proxmox-bpg](https://marketplace.upbound.io/providers/valkiriaaquaticamendi/provider-proxmox-bpg)
- [Crossplane Managed Resources](https://docs.crossplane.io/latest/managed-resources/)
- [Flux SOPS Integration](https://fluxcd.io/flux/guides/mozilla-sops/)
