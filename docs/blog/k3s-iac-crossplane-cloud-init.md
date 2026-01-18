# K3s Infrastructure as Code: Crossplane + Cloud-Init for Zero-Touch Node Provisioning

**Date**: 2026-01-17
**Author**: AI-assisted homelab automation
**Tags**: k3s, crossplane, proxmox, cloud-init, iac, gitops, kubernetes

## The Problem

After removing a K3s node from my homelab cluster, I needed to restore 3-node etcd quorum. The obvious solution: spin up a new VM and join it to the cluster. But I wanted **zero manual intervention** - pure Infrastructure as Code.

The goals:
1. Define the VM in Git
2. Push to trigger Flux reconciliation
3. Crossplane creates the VM
4. VM automatically joins the K3s cluster
5. No SSH, no scripts to run, no manual steps

## The Journey (What Didn't Work)

### Attempt 1: Crossplane EnvironmentFile for Dynamic Snippets

My first idea was elegant: use Crossplane's `EnvironmentFile` CRD to create a cloud-init snippet on Proxmox with the K3s join token embedded. Full GitOps - the token would be SOPS-encrypted in the manifest.

```yaml
apiVersion: virtualenvironmentfile.crossplane.io/v1alpha1
kind: EnvironmentFile
metadata:
  name: k3s-cloud-init-fun-bedbug
spec:
  forProvider:
    nodeName: fun-bedbug
    datastoreId: local
    contentType: snippets
    sourceRaw:
      - fileName: k3s-join.yaml
        data: |
          #cloud-config
          runcmd:
            - curl -sfL https://get.k3s.io | K3S_TOKEN='...' sh -s - server
```

**Result**: Failed with SSH permission errors.

The Proxmox API doesn't support uploading snippets directly - it requires SFTP. The Crossplane provider needs SSH credentials configured, which adds complexity (SSH keys in secrets, per-node addresses, etc.).

### Attempt 2: Separate Script After VM Creation

Next idea: cloud-init just prepares the VM, then a script reads the token from a Kubernetes Secret and SSHes in to run the join command.

```bash
# join-server.sh
K3S_TOKEN=$(kubectl get secret k3s-join-token -o jsonpath='{.data.token}' | base64 -d)
ssh ubuntu@$VM_IP "curl -sfL https://get.k3s.io | K3S_TOKEN='$K3S_TOKEN' sh -s - server"
```

**Result**: Works, but requires manual script execution. Not pure IaC.

## The Solution: Hybrid Approach

The winning approach separates concerns:

1. **Snippets are host-level infrastructure** - deployed once per Proxmox host
2. **VMs are workload** - managed by Crossplane GitOps
3. **Cloud-init does everything** - no post-boot intervention needed

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  ONE-TIME PER HOST (like installing packages)                   │
│                                                                 │
│  scp k3s-server-<host>.yaml root@<host>.maas:/var/lib/vz/snippets/
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  GITOPS (repeatable, automated)                                 │
│                                                                 │
│  1. Commit EnvironmentVM manifest to Git                        │
│  2. Flux reconciles → Crossplane creates VM                     │
│  3. VM boots → cloud-init runs                                  │
│  4. K3s installs and joins cluster automatically                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### The Cloud-Init Snippet

The snippet does everything:
- Sets hostname (important for consistent node naming)
- Configures kernel modules and sysctl for Kubernetes
- Installs qemu-guest-agent for Proxmox integration
- Installs K3s with join credentials

```yaml
#cloud-config
hostname: k3s-vm-fun-bedbug
preserve_hostname: true

runcmd:
  # Ensure hostname persists (cloud-init timing issues)
  - hostnamectl set-hostname k3s-vm-fun-bedbug

  # Kubernetes prerequisites
  - swapoff -a
  - modprobe overlay br_netfilter
  - sysctl --system

  # Join K3s cluster
  - |
    curl -sfL https://get.k3s.io | \
      K3S_URL='https://192.168.4.210:6443' \
      K3S_TOKEN='<token>' \
      INSTALL_K3S_VERSION='v1.33.6+k3s1' \
      sh -s - server --disable servicelb
```

### The Crossplane Manifest

The VM manifest references the pre-deployed snippet:

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

    disk:
      - interface: scsi0
        size: 50
        importFrom: local:import/noble-server-cloudimg-amd64.qcow2

    initialization:
      - datastoreId: local
        userDataFileId: local:snippets/k3s-server-fun-bedbug.yaml
```

## Why This Works

### Snippets Are Like Host Packages

Think of deploying snippets like installing packages on a host. You don't manage `/usr/bin/curl` via GitOps - you install it once and it's available forever. Same with snippets.

### Secrets Stay Out of Git

The snippet contains the K3s token, but:
- It's deployed via SCP, not committed to Git
- The Git repo only has an EXAMPLE template
- Real snippets are in `.gitignore`

### Full Automation Where It Matters

The *frequent* operation (creating/destroying VMs) is fully automated via GitOps. The *rare* operation (setting up a new Proxmox host) is a one-liner.

## Lessons Learned

### 1. Cloud-Init Hostname Timing

The `hostname:` directive in cloud-init runs early, but K3s may start before the hostname fully propagates. Solution: add `hostnamectl set-hostname` in `runcmd` right before the K3s install.

### 2. Proxmox API Limitations

Not everything can go through the API. Snippets require SFTP upload. Don't fight it - adapt your architecture.

### 3. Crossplane deletionPolicy: Orphan

During development, use `deletionPolicy: Orphan`. This means deleting the Crossplane CR doesn't delete the VM - useful when iterating. Just remember to manually clean up.

### 4. Per-Host Snippets for Consistent Naming

Generic snippets mean generic hostnames (`ubuntu`). Create per-host snippets with the hostname baked in for consistent K3s node naming.

## Result

```
$ kubectl get nodes
NAME                       STATUS   ROLES                       AGE
k3s-vm-fun-bedbug          Ready    control-plane,etcd,master   43s
k3s-vm-pumped-piglet-gpu   Ready    control-plane,etcd,master   88d
k3s-vm-pve                 Ready    control-plane,etcd,master   248d
```

Three control-plane nodes, etcd quorum restored, all managed via GitOps. New VMs join automatically - just commit and push.

## Files

- **Example snippet**: `scripts/k3s/snippets/k3s-server-EXAMPLE.yaml`
- **VM manifest**: `gitops/clusters/homelab/instances/k3s-vm-fun-bedbug.yaml`
- **Runbook**: `docs/runbooks/k3s-add-control-plane-node.md`

---

*This post was written with AI assistance after solving the problem hands-on. The AI wrote the initial broken code too - it took several iterations to find the right architecture.*
