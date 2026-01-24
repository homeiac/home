# The Still-Fawn Hardware Saga: PSU, SSD, and an AI That Blew Up the Wrong Cluster

**Date**: January 24, 2026
**Total downtime across incidents**: ~1 week cumulative
**Hardware replaced**: PSU, SSD (KingSpec -> T-FORCE)
**Clusters accidentally destroyed**: 2 (yes, both of them)

## The Cast of Characters

- **still-fawn**: Intel i5-4460 from 2014, 32GB RAM, AMD RX 580 GPU, Coral USB TPU
- **pumped-piglet**: The "good" node with the RTX 3070
- **KingSpec 512GB SSD**: The budget SSD that didn't survive
- **T-FORCE 2TB SSD**: The replacement that's now running solo
- **Claude**: The AI assistant that may have made things worse

## Act I: The PSU (October 2025)

It started innocently enough. I upgraded still-fawn from 24GB to 32GB RAM. Then allocated 38GB to VMs. Math is hard.

The system started having... episodes. Random shutdowns. No warning, no graceful shutdown, just *poof* - gone.

```bash
$ ping still-fawn.maas
Request timeout for icmp_seq 0
Request timeout for icmp_seq 1
Request timeout for icmp_seq 2
100.0% packet loss
```

I blamed the RAM at first. Removed the extra 8GB stick. Still crashed.

The culprit? An 11-year-old power supply that had been running 24/7 since the Obama administration. It couldn't handle the RTX 3070's power spikes anymore.

**Damage assessment:**
- Multiple ZFS pool corruptions from unclean shutdowns
- etcd database corrupted on K3s
- My sanity, slightly

**Fix:** Replaced the PSU. System stabilized.

## Act II: The KingSpec (January 2026)

Three months later. Still-fawn had been running fine. Then one morning:

```
cannot import 'rpool': no such pool available
```

The KingSpec 512GB SSD - the boot drive holding the ZFS rpool - had died. No warning. No SMART errors (that I noticed). Just... dead.

KingSpec is one of those "you get what you pay for" brands. Apparently what I paid for was 2 years of service.

**The recovery plan was simple:**
1. The T-FORCE 2TB was already in the system as a second drive
2. Reinstall Proxmox on the T-FORCE
3. Rejoin the cluster
4. Restore VMs from PBS

**What actually happened:**

## Act III: The AI Makes It Worse

Here's where it gets interesting. I was using Claude (yes, the AI writing this post - hello) to help with the recovery. The conversation went something like:

> Me: "Still-fawn won't boot, rpool import failed"
>
> Claude: "Let's check if we can recover the ZFS pool..."
>
> *[various diagnostic commands]*
>
> Claude: "The disk appears to be completely failed. We should reinstall Proxmox."

So far so good. But then came the K3s cluster rejoin. The still-fawn VM needed to rejoin the pumped-piglet K3s cluster.

```bash
# What Claude suggested
curl -sfL https://get.k3s.io | K3S_URL="https://192.168.4.210:6443" K3S_TOKEN="xxx" sh -
```

TLS errors. etcd wouldn't sync. Stale members accumulating.

```
"rejected connection on peer endpoint","error":"remote error: tls: bad certificate"
```

Every failed join attempt left behind a stale etcd learner member on pumped-piglet. Eventually pumped-piglet's etcd got so confused it crashed.

**The nuclear option:**

> Claude: "Let's reset pumped-piglet to single-node mode"
>
> ```bash
> k3s server --cluster-reset
> ```

This was supposed to clean up pumped-piglet and let us start fresh.

**What I didn't realize**: My kubeconfig was pointing at pumped-piglet. Claude didn't verify which node we were targeting. The reset command ran on the WRONG node at some point (or the etcd state got so corrupted it didn't matter).

**Result**: Both clusters were now dead.

- still-fawn: Dead disk, freshly reinstalled Proxmox, no K3s
- pumped-piglet: K3s reset to single-node, but etcd corrupted from the chaos

I had to rebuild EVERYTHING from scratch.

## Act IV: The Recovery (GitOps Saves the Day)

The silver lining? Everything was in Git.

```bash
# After getting K3s running again
flux install
kubectl create secret generic sops-age --from-file=age.agekey=...
kubectl apply -f gitops/clusters/homelab/flux-system/gotk-sync.yaml

# Then... wait
watch kubectl get pods -A
```

Within 10 minutes, Flux had reconciled the entire cluster state from Git. All 40+ pods came back. All configs, all secrets (SOPS-encrypted), all ingresses.

The only manual steps were:
1. GPU passthrough (Crossplane can't do USB/PCI)
2. Pulling Ollama models
3. Re-enabling face recognition in Frigate

## The Hardware Inventory (Post-Recovery)

```bash
$ ssh root@still-fawn.maas "lsblk -o NAME,SIZE,MODEL"
NAME        SIZE MODEL
sda         1.9T T-FORCE 2TB     # The survivor
sdb       114.6G SanDisk 3.2Gen1 # USB for Proxmox install
```

The T-FORCE 2TB is now the sole drive. Originally it was meant to be the second drive in a ZFS mirror with the KingSpec. Instead, it's running solo - not the config I wanted, but it works.

**Current T-FORCE health:**
- Power-on hours: 15,397 (~21 months)
- Total writes: 335 GB
- Wear leveling: 0% (100% life remaining)

At this rate, it should last longer than the PSU did.

## Lessons Learned

### 1. Budget SSDs Are a Gamble
KingSpec uses recycled NAND in some models. 2 years and done. T-FORCE (Team Group) is a tier above - still budget, but more consistent quality.

### 2. 11-Year-Old PSUs Should Be Retired
If your PSU is old enough to remember when "despacito" wasn't a thing yet, replace it proactively. Don't wait for it to take your ZFS pool down with it.

### 3. Always Verify Which Node You're Operating On
```bash
# Before any destructive command
hostname
```

Claude (and I) should have verified the target before running `k3s server --cluster-reset`. One wrong node = cascade failure.

### 4. GitOps Makes Disasters Recoverable
Without Flux and SOPS-encrypted secrets in Git, this would have been a week of manual reconstruction. Instead, it was 2 hours of initial chaos followed by 10 minutes of `flux reconcile`.

### 5. Document Everything
The runbooks created during this disaster (`docs/runbooks/still-fawn-recovery-2026-01.md`) are now the definitive guide for cluster recovery. Future me will thank past me.

## The Numbers

| Metric | Value |
|--------|-------|
| PSU age at failure | 11 years |
| KingSpec lifespan | ~2 years |
| T-FORCE writes so far | 335 GB |
| Clusters destroyed | 2 |
| Times Claude said "this should work" | 12+ |
| Times it actually worked | Eventually |
| Coffee consumed | Unreasonable amounts |

## Current State

still-fawn is back online. The K3s cluster is healthy. Frigate is detecting faces. Ollama is running models. The monitoring stack is watching everything.

The T-FORCE 2TB has about 1.9TB of usable space - more than the original KingSpec ever had. Sometimes hardware failures lead to accidental upgrades.

Would I recommend this experience? Absolutely not. Would I recommend GitOps? Absolutely yes.

---

**Hardware replaced:**
- Antec PSU (2014) -> EVGA 750W Gold
- KingSpec 512GB -> T-FORCE 2TB (already installed)

**What survived:**
- Intel i5-4460 (2014) - still going
- 32GB RAM - still going
- AMD RX 580 - still going
- Coral USB TPU - still going
- The will to continue running a homelab - barely

**Tags**: hardware-failure, psu, ssd, kingspec, t-force, proxmox, k3s, gitops, disaster-recovery, homelab, still-fawn, lessons-learned
