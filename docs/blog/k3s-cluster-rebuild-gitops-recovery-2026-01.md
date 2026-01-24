# How I Blew Up My K3s Cluster and Didn't Panic (Thanks to GitOps)

**Date**: January 24, 2026
**Time to full recovery**: ~2 hours
**Panic level**: Surprisingly low

## The Disaster

It started with a simple disk failure on `still-fawn`, one of my Proxmox nodes. The 512GB SSD that held the ZFS root pool decided it had enough. The node wouldn't boot - just dropped into initramfs with "cannot import rpool".

No big deal, I thought. I have PBS backups. I'll just restore VM 108 (my K3s control plane node on still-fawn).

**Plot twist**: The PBS restore was painfully slow (2 MB/s due to chunk-based deduplication + ZFS random I/O). After 23 minutes at 5% progress, I made a decision: create a fresh VM instead.

That's when things got interesting.

## The Cascade

My K3s cluster was a 2-node HA setup with embedded etcd:
- `pumped-piglet` (VM 105) - 32GB RAM, RTX 3070
- `still-fawn` (VM 108) - 32GB RAM, AMD GPU, Coral TPU

With still-fawn down, etcd lost quorum. The cluster was effectively dead.

**What I tried (and failed at):**

1. Reset pumped-piglet to single-node with `k3s server --cluster-reset` ✓
2. Create fresh VM 108 via Crossplane ✓
3. Join still-fawn to the cluster... ✗

The join kept failing with TLS certificate errors:
```
"rejected connection on peer endpoint","error":"remote error: tls: bad certificate"
```

Every attempt would:
1. Add a learner member to pumped-piglet's etcd
2. Fail TLS handshake
3. Leave stale learner in etcd
4. Crash pumped-piglet's etcd (stuck trying to reach unreachable member)

I was going in circles. Reset pumped-piglet, try to join, fail, reset again. Classic insanity.

## The Root Cause

After much frustration (and some colorful language), I finally diagnosed it:

**Mixed CA certificates**. still-fawn had OLD CA files from previous failed attempts mixed with NEW client certs:

```
/var/lib/rancher/k3s/server/tls/etcd/peer-ca.crt     06:30 (OLD!)
/var/lib/rancher/k3s/server/tls/etcd/client.crt      06:59 (new)
```

K3s downloads CA certs from the existing cluster during join. But if OLD CA files exist on disk, they're used instead, causing TLS mismatch.

**Why did the old files persist?** Because I was using `rm -rf /var/lib/rancher/k3s` instead of the proper uninstall script. The systemd service would restart and recreate partial state before the join completed.

## The Fix

One command: `/usr/local/bin/k3s-uninstall.sh`

This script removes EVERYTHING:
- All `/var/lib/rancher/k3s/*`
- All `/etc/rancher/k3s/*`
- systemd service files
- symlinks (`kubectl`, `crictl`, `ctr`)
- CNI state
- iptables rules

After a proper uninstall and fresh join:

```
$ kubectl get nodes
NAME                       STATUS   ROLES                       AGE
k3s-vm-pumped-piglet-gpu   Ready    control-plane,etcd,master   40m
k3s-vm-still-fawn          Ready    control-plane,etcd,master   55s
```

## Why I Didn't Panic: GitOps

Here's the thing - my entire cluster state is in Git. When the K3s cluster came back online, I just needed to:

1. Install Flux
2. Create two secrets (SOPS age key + GitHub deploy key)
3. Apply the GitOps sync config

```bash
# Install Flux
flux install

# Create SOPS decryption secret
kubectl create secret generic sops-age \
  --namespace=flux-system \
  --from-file=age.agekey=~/.config/sops/age/keys.txt

# Create GitHub deploy key secret
kubectl create secret generic flux-system \
  --namespace=flux-system \
  --from-file=identity=~/.ssh/flux-homeiac-home \
  --from-file=identity.pub=~/.ssh/flux-homeiac-home.pub \
  --from-literal=known_hosts="$(ssh-keyscan github.com 2>/dev/null)"

# Apply sync config
kubectl apply -f gitops/clusters/homelab/flux-system/gotk-sync.yaml
```

Within minutes, Flux was reconciling:

```
$ flux get kustomizations
NAME                READY   MESSAGE
cert-manager-config True    Applied revision: master@sha1:98aa8fff
flux-system         True    Applied revision: master@sha1:98aa8fff
metallb-config      True    Applied revision: master@sha1:98aa8fff
traefik-config      True    Applied revision: master@sha1:98aa8fff
```

HelmReleases started deploying automatically:
- cert-manager ✓
- MetalLB ✓
- kube-prometheus-stack ✓
- Crossplane ✓
- external-dns ✓
- Traefik ✓

All my apps, all my configs, all my secrets (SOPS-encrypted in Git) - everything came back.

## What GitOps Saved Me From

Without GitOps, I would have needed to:

1. Remember which Helm charts were installed and their versions
2. Recreate all the Helm values files
3. Remember the order of installation (CRDs before resources)
4. Manually create all secrets
5. Reconfigure all ingresses
6. Hope I didn't forget anything

Instead, I just pointed Flux at my Git repo and went to make coffee.

## Lessons Learned

### 1. Use the Uninstall Script
Never `rm -rf /var/lib/rancher/k3s`. Always use `/usr/local/bin/k3s-uninstall.sh`. It exists for a reason.

### 2. Dependency Ordering Matters
Flux's server-side dry-run will fail if CRDs don't exist yet. Solution: separate Flux Kustomizations with `dependsOn`:

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: metallb-config
spec:
  dependsOn:
    - name: flux-system  # Wait for MetalLB HelmRelease
  path: ./infrastructure-config/metallb-config/resources
```

### 3. Keep Your Age Key Safe
The SOPS age private key (`~/.config/sops/age/keys.txt`) is the master key to all your encrypted secrets. Back it up. Seriously.

### 4. Document the Recovery Process
I now have a complete runbook at `docs/runbooks/still-fawn-recovery-2026-01.md` with every command needed to rebuild from scratch.

### 5. GitOps is Not Just Hype
When your cluster dies at 2 AM, you don't want to be piecing together configs from memory. Git is your source of truth. Flux makes it real.

## The Numbers

| Metric | Value |
|--------|-------|
| Time from disk failure to cluster rebuild | ~90 minutes |
| Time from Flux install to apps running | ~5 minutes |
| Manual kubectl commands after Flux | 0 |
| Secrets recreated manually | 2 (age key + deploy key) |
| Configs recreated manually | 0 |
| Sleep lost | Some, but not as much as expected |

## Final Thoughts

Disasters happen. Disks fail. Clusters die. The question isn't *if* but *when*.

GitOps doesn't prevent disasters - it makes recovery boring. And boring is exactly what you want at 2 AM.

My cluster is now running again with all services restored. The only evidence of the disaster is this blog post and a slightly updated runbook.

If you're still doing `kubectl apply -f` by hand, consider this your sign to embrace GitOps. Future-you will thank present-you.

---

**Stack**: K3s, Flux, SOPS, Proxmox, PBS
**Repo**: [homeiac/home](https://github.com/homeiac/home)

**Tags**: k3s, kubernetes, gitops, flux, disaster-recovery, etcd, homelab, infrastructure-as-code, sops
