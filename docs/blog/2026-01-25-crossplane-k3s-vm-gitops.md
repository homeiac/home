# Declaring a VM Into Existence with Crossplane and GitOps

**Date**: January 25, 2026
**Time to 3-node cluster**: ~5 minutes from git push

## The Goal

My K3s cluster was running on 2 nodes - `pumped-piglet` and `still-fawn`. That's enough for etcd to function, but zero fault tolerance. One node goes down, the whole cluster dies.

I had a third Proxmox host (`fun-bedbug`) with a stopped VM from a previous cluster that had been disabled due to thermal issues. Time to bring it back.

## The Old Way vs The New Way

**Old way**: SSH into Proxmox, run `qm create`, configure cloud-init, start VM, SSH into VM, install K3s, debug why it didn't join, repeat.

**New way**: Edit YAML, git push, make coffee.

## The Implementation

### Step 1: Update the Join Token

K3s uses a token for cluster membership. The old VM had a stale token from the previous cluster. I updated the cloud-init snippet with the current token:

```bash
# Get current token from running cluster
./scripts/k3s/exec.sh still-fawn "cat /var/lib/rancher/k3s/server/node-token"

# Update snippet (not tracked in git - contains secrets)
vim scripts/k3s/snippets/k3s-server-fun-bedbug.yaml

# Deploy to Proxmox host
scp scripts/k3s/snippets/k3s-server-fun-bedbug.yaml root@fun-bedbug.maas:/var/lib/vz/snippets/
```

### Step 2: Destroy the Old VM

The old VM had stale K3s state that would cause TLS certificate mismatches. Cleanest solution: destroy it and let Crossplane recreate fresh.

```bash
ssh root@fun-bedbug.maas "qm destroy 114 --purge"
```

### Step 3: Enable in GitOps

Three files to uncomment:

**Crossplane provider** (`gitops/clusters/homelab/infrastructure/crossplane/kustomization.yaml`):
```yaml
resources:
  - namespace.yaml
  - helmrepository.yaml
  - helmrelease.yaml
  - proxmox-ssh-key.sops.yaml
  - provider-proxmox.yaml      # Uncommented
  - proxmox-secret.yaml        # Uncommented
  - provider-config.yaml       # Uncommented
```

**VM instances** (`gitops/clusters/homelab/instances/kustomization.yaml`):
```yaml
resources:
  - ubuntu-noble-cloud-image.yaml  # Uncommented
  - k3s-vm-fun-bedbug.yaml         # Uncommented
```

**VM manifest** (`gitops/clusters/homelab/instances/k3s-vm-fun-bedbug.yaml`):
```yaml
spec:
  forProvider:
    started: true   # Changed from false
    onBoot: true    # Changed from false
```

### Step 4: Git Push and Watch

```bash
git add gitops/
git commit -m "feat(k3s): add fun-bedbug as 3rd control-plane node via Crossplane"
git push

flux reconcile kustomization flux-system --with-source
```

Then I watched Crossplane work:

```bash
$ kubectl get environmentvm k3s-vm-fun-bedbug -w
NAME                SYNCED   READY   EXTERNAL-NAME   AGE
k3s-vm-fun-bedbug   True     False                   10s
k3s-vm-fun-bedbug   True     False                   30s
k3s-vm-fun-bedbug   True     True                    2m
```

On Proxmox, the VM appeared, booted, ran cloud-init, installed K3s, and joined the cluster - all automatically.

## The Result

```
$ kubectl get nodes
NAME                       STATUS   ROLES                       AGE
k3s-vm-fun-bedbug          Ready    control-plane,etcd,master   2m
k3s-vm-pumped-piglet-gpu   Ready    control-plane,etcd,master   38h
k3s-vm-still-fawn          Ready    control-plane,etcd,master   38h
```

Three nodes. Proper etcd quorum. Fault tolerance restored.

## What Crossplane Actually Did

When Flux applied the `EnvironmentVM` resource, Crossplane's Proxmox provider:

1. Created VM 114 on `fun-bedbug` with specified CPU, memory, disk
2. Imported the Ubuntu Noble cloud image into the boot disk
3. Attached the cloud-init snippet for user-data
4. Configured networking with DHCP
5. Started the VM

Cloud-init then:

1. Set the hostname
2. Configured kernel modules for Kubernetes
3. Installed qemu-guest-agent
4. Downloaded and installed K3s with the join token
5. Joined the existing cluster as a control-plane node

All from a YAML file in Git.

## The VM Declaration

Here's what a Crossplane-managed VM looks like:

```yaml
apiVersion: virtualenvironmentvm.crossplane.io/v1alpha1
kind: EnvironmentVM
metadata:
  name: k3s-vm-fun-bedbug
spec:
  forProvider:
    nodeName: fun-bedbug
    vmId: 114
    started: true
    onBoot: true

    cpu:
      - cores: 1
        type: host
    memory:
      - dedicated: 4096

    disk:
      - interface: scsi0
        datastoreId: local
        size: 50
        importFrom: local:import/noble-server-cloudimg-amd64.qcow2

    networkDevice:
      - bridge: vmbr0
        model: virtio

    initialization:
      - datastoreId: local
        userAccount:
          - username: ubuntu
        ipConfig:
          - ipv4:
              - address: dhcp
        userDataFileId: local:snippets/k3s-server-fun-bedbug.yaml

    agent:
      - enabled: true

  providerConfigRef:
    name: default
  deletionPolicy: Orphan
```

That's it. The entire VM definition. Version controlled. Reviewable. Reproducible.

## Lessons Learned (Again)

### 1. Destroy Stale VMs, Don't Repair Them

The old VM had K3s state from a previous cluster. I could have tried to clean it up with `k3s-uninstall.sh`, but destroying and recreating is cleaner and faster. Crossplane makes recreation trivial.

### 2. Cloud-Init Snippets Stay on Proxmox

The snippet contains the cluster join token. It lives on the Proxmox host, not in Git. The VM manifest just references it by path:

```yaml
userDataFileId: local:snippets/k3s-server-fun-bedbug.yaml
```

This keeps secrets out of version control while still having the VM definition in Git.

### 3. EnvironmentDownloadFile Can Fail Safely

Crossplane tried to download the Ubuntu cloud image but failed because it already existed on the host. That's fine - the VM creation proceeded using the existing image. Not every resource needs to succeed for the system to work.

### 4. deletionPolicy: Orphan is Your Friend

If I delete the Kubernetes resource, the VM stays. This prevents accidental destruction and lets me iterate on the manifest without fear.

## The Stack

- **Crossplane**: Kubernetes-native infrastructure provisioning
- **provider-proxmox-bpg**: Crossplane provider for Proxmox VE
- **Flux**: GitOps continuous delivery
- **SOPS**: Secret encryption for credentials in Git
- **K3s**: Lightweight Kubernetes with embedded etcd

## What's Next

With the Crossplane provider working, I can now:

- Declare new VMs in Git and have them appear on any Proxmox host
- Manage the entire homelab infrastructure as code
- Rebuild the cluster from scratch with a git clone and a few commands

The dream of fully declarative infrastructure is one step closer.

---

**Repository**: [homeiac/home](https://github.com/homeiac/home)

**Tags**: crossplane, proxmox, k3s, kubernetes, gitops, flux, infrastructure-as-code, homelab, etcd, cloud-init
