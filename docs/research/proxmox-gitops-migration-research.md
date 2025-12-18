# Research: Proxmox Manager → GitOps Migration Options

## Executive Summary

This is a **research document**, not an implementation plan. It analyzes what parts of `proxmox/homelab/src/homelab/` can realistically move to GitOps-style Flux management, and which approach (Crossplane, CAPI, TF Controller, Ansible) fits each use case.

**TL;DR**: The current Python manager handles 3 distinct categories:
1. **Declarative infrastructure** (VMs, containers, network) → Good GitOps candidates
2. **Host-level operations** (ZFS, GPU passthrough) → Keep as Python/Ansible
3. **Operational/imperative** (start/stop, health checks) → Keep as Python CLI

---

## Current Proxmox Manager Inventory

### Files and Their Responsibilities

| File | Operations | GitOps Fit |
|------|------------|-----------|
| `vm_manager.py` | VM create/delete/health check, cloud-init, disk resize | ⚠️ Partial |
| `k3s_manager.py` | K3s install, node join, cluster bootstrap | ✅ CAPI |
| `storage_manager.py` | ZFS pool create/import, dataset, PVE registration | ❌ Host-level |
| `gpu_passthrough_manager.py` | VFIO setup, IOMMU, kernel modules | ❌ Host-level |
| `pbs_storage_manager.py` | PBS storage entry registration | ✅ Yes |
| `unified_infrastructure_manager.py` | YAML reconciliation (already GitOps-like) | ✅ Replace |

---

## Option 1: Crossplane + provider-proxmox-bpg

### Maturity Assessment
- **Version**: v0.11.1 (Dec 2025)
- **Upstream**: Based on [bpg/terraform-provider-proxmox](https://github.com/bpg/terraform-provider-proxmox) (1.7k stars, 129 contributors)
- **Stars**: 11 (early adoption)
- **Risk**: Single maintainer, early stage

### Supported Resources (31 CRDs)
- `EnvironmentVM` - Virtual machines
- `EnvironmentContainer` - LXC containers
- `EnvironmentNetworkLinuxBridge` / `EnvironmentNetworkLinuxVlan` - Networking
- `EnvironmentFile` / `EnvironmentDownloadFile` - Storage files
- Firewall rules, aliases, IP sets, security groups
- User accounts, groups, roles, ACL
- HA groups and resources
- APT repositories, DNS, time settings

### Known Limitations
- 4 resources blocked by Upjet schema issues (cluster options, hardware mappings)
- Certificate and datastore resources don't implement `Get` properly
- Token creation fails with retrieval errors

### What Could Move to Crossplane

```yaml
# Example: VM definition as Crossplane resource
apiVersion: virtualenvironmentvm.crossplane.io/v1alpha1
kind: EnvironmentVM
metadata:
  name: k3s-vm-still-fawn
spec:
  forProvider:
    nodeName: still-fawn
    name: k3s-vm-still-fawn
    vmId: 108
    memory:
      dedicated: 16384
    cpu:
      cores: 4
    disk:
      - interface: scsi0
        size: 100
        storage: local-zfs
    network:
      - bridge: vmbr0
        model: virtio
    agent:
      enabled: true
```

**Pro**: Native K8s resources, Flux reconciliation, drift detection
**Con**: Early provider maturity, limited ZFS/host operations

### Sources
- [provider-proxmox-bpg GitHub](https://github.com/valkiriaaquatica/provider-proxmox-bpg)
- [Upbound Marketplace](https://marketplace.upbound.io/providers/valkiriaaquaticamendi/provider-proxmox-bpg/v0.11.1)

---

## Option 2: Cluster API (CAPI) for K3s Lifecycle

### Available Providers
1. **IONOS CAPMOX** - [ionos-cloud/cluster-api-provider-proxmox](https://github.com/ionos-cloud/cluster-api-provider-proxmox)
2. **k8s-proxmox CAPPX** - [k8s-proxmox/cluster-api-provider-proxmox](https://github.com/k8s-proxmox/cluster-api-provider-proxmox)
3. **Launchbox** - [launchboxio/cluster-api-provider-proxmox](https://github.com/launchboxio/cluster-api-provider-proxmox)

### What This Replaces
- `K3sManager` - cluster bootstrap, node joining
- `VMManager` (for K3s VMs specifically)
- Manual `kubeadm` / `k3s install` scripts

### Architecture
```
Flux → Cluster CR → CAPI Controller → Proxmox API → VMs → K3s bootstrap
```

### Trade-offs
**Pro**:
- Standard K8s way to manage cluster lifecycle
- Integrates with Talos, kubeadm, RKE2
- Node scaling via MachineDeployments

**Con**:
- Requires template VMs
- Overkill for single-cluster homelab
- Adds CAPI controller complexity

### Sources
- [CAPI Proxmox Tutorial](https://itnext.io/build-your-own-managed-kubernetes-service-on-proxmox-with-capi-8d9786644818)
- [CAPI + Talos + Proxmox](https://a-cup-of.coffee/blog/talos-capi-proxmox/)

---

## Option 3: Tofu/Terraform Controller

### Background
Weaveworks shutdown (Feb 2024) → Project moved to [flux-iac/tofu-controller](https://github.com/flux-iac/tofu-controller)

### Architecture
```
Git (*.tf files) → GitRepository → Terraform CR → Tofu Controller → Proxmox API
```

### Key Features
- GitOps for Terraform/OpenTofu
- Drift detection
- State enforcement
- Multi-tenancy via runner pods

### What Could Move
- Everything bpg/terraform-provider-proxmox supports (VMs, containers, network, firewall, users)
- State stored in K8s secrets or backend

### Trade-offs
**Pro**:
- Uses mature Terraform provider (1.7k stars)
- Battle-tested GitOps pattern
- State management solved

**Con**:
- Adds Terraform layer (complexity)
- HCL + YAML hybrid
- State drift between TF state and actual

### Example
```yaml
apiVersion: infra.contrib.fluxcd.io/v1alpha2
kind: Terraform
metadata:
  name: proxmox-vms
spec:
  path: ./terraform/proxmox
  sourceRef:
    kind: GitRepository
    name: home
  approvePlan: auto
  interval: 30m
```

### Sources
- [Tofu Controller](https://github.com/flux-iac/tofu-controller)
- [Weave GitOps TF Docs](https://docs.gitops.weaveworks.org/docs/terraform/terraform-intro/)

---

## Option 4: Ansible + GitOps (You Said No, But For Completeness)

### Collection
- [community.proxmox](https://github.com/ansible-collections/community.proxmox) - Official
- [maxhoesel-ansible/ansible-collection-proxmox](https://github.com/maxhoesel-ansible/ansible-collection-proxmox)

### What It Does Well
- Host-level operations (ZFS, kernel modules, VFIO)
- One-time setup tasks
- Idempotent playbooks

### GitOps Pattern
AWX/AAP or Kubernetes Job runs Ansible playbooks from Git.

**You said no, so skipping.**

---

## Option 5: KRO (Kube Resource Orchestrator)

### What It Is
[KRO](https://kro.run/) is a **composition/orchestration layer** for K8s resources - including CRDs from operators like Crossplane, Kubemox, or proxmox-operator.

### Clarification: KRO + Proxmox Operators = YES

**Important nuance:** KRO itself doesn't talk to Proxmox, but:

1. **Proxmox Operators exist** that make VMs into K8s CRDs:
   - [**Kubemox**](https://github.com/alperencelik/kubemox) - 69 stars, v0.5.2, active
   - [**proxmox-operator**](https://github.com/CRASH-Tech/proxmox-operator) - 81 stars, v1.0.0, `Qemu` CRD
   - **Crossplane provider-proxmox-bpg** - `EnvironmentVM` CRD

2. **KRO can orchestrate these CRDs** with K8s workloads:
   ```yaml
   # KRO ResourceGraphDefinition example
   apiVersion: kro.run/v1alpha1
   kind: ResourceGraphDefinition
   metadata:
     name: k3s-node-with-workload
   spec:
     schema:
       apiVersion: homelab.io/v1alpha1
       kind: K3sNode
       spec:
         nodeName: string
         cpuCores: integer
         memoryGB: integer
     resources:
       # Step 1: Create Proxmox VM (via Kubemox/Crossplane CRD)
       - id: proxmox-vm
         template:
           apiVersion: proxmox.xfix.org/v1alpha1  # or Crossplane API
           kind: Qemu
           metadata:
             name: ${schema.spec.nodeName}
           spec:
             node: still-fawn
             cores: ${schema.spec.cpuCores}
             memory: ${schema.spec.memoryGB * 1024}

       # Step 2: Wait for VM ready, then deploy workload
       - id: workload-deployment
         dependsOn: [proxmox-vm]
         readyWhen:
           - ${proxmox-vm.status.phase == "Running"}
         template:
           apiVersion: apps/v1
           kind: Deployment
           # ...
   ```

### The Stack Would Be:
```
KRO (composition layer - DAG ordering, custom APIs)
  ↓ orchestrates
Kubemox / Crossplane / proxmox-operator (CRDs → Proxmox API)
  ↓ manages
Proxmox VMs
```

### Proxmox Operator Comparison

| Operator | Stars | Version | Resources | Status |
|----------|-------|---------|-----------|--------|
| **Kubemox** | 69 | v0.5.2 | VMs (LXC planned) | Alpha, active |
| **proxmox-operator** | 81 | v1.0.0 | VMs only (`Qemu`) | Alpha, stale (2023) |
| **Crossplane provider** | 11 | v0.11.1 | VMs, LXC, network, firewall | Alpha, active |

### When KRO Makes Sense
- You want a **single custom API** (e.g., `K3sNode`) that creates VM + joins cluster + deploys workload
- You're already using Crossplane/Kubemox and want to compose with K8s resources
- You want DAG-based dependency ordering without writing a controller

### When KRO Doesn't Help
- You just want VMs as K8s resources (use Crossplane/Kubemox directly)
- You need imperative operations (start/stop)
- Host-level operations (ZFS, GPU passthrough)

---

## Migration Tier Analysis

### Tier 1: Good GitOps Fit (Crossplane or TF Controller)

| Resource | Current Code | GitOps Target |
|----------|--------------|---------------|
| VM definitions | `VMManager.create_vm()` | `EnvironmentVM` CR |
| LXC containers | - | `EnvironmentContainer` CR |
| Network bridges | - | `EnvironmentNetworkLinuxBridge` CR |
| Firewall rules | - | Firewall CRs |
| PBS storage entry | `PBSStorageManager` | `proxmox_virtual_environment_storage` |
| Users/ACL | - | User/Role CRs |

### Tier 2: CAPI-Specific

| Resource | Current Code | GitOps Target |
|----------|--------------|---------------|
| K3s cluster VMs | `VMManager` + `K3sManager` | CAPI `Cluster` + `Machine` |
| Node scaling | Manual | `MachineDeployment` |

### Tier 3: Keep as Python/Ansible (Host-Level)

| Resource | Why Not GitOps |
|----------|----------------|
| ZFS pool create/import | Runs SSH commands on host, not API |
| GPU passthrough | Kernel modules, BIOS config |
| IOMMU groups | Host hardware detection |
| Coral TPU setup | USB device passthrough |

### Tier 4: Keep as Python CLI (Imperative)

| Resource | Why Not GitOps |
|----------|----------------|
| VM start/stop | Imperative by nature |
| Health checks | Query, not declaration |
| Resource calculation | Pure compute |
| Diagnostics | Read-only |

---

## Recommendation Matrix

| Approach | Maturity | Complexity | Fits Your Stack | Verdict |
|----------|----------|------------|-----------------|---------|
| **Crossplane** | Early (6mo) | Medium | ✅ Native K8s, Flux | ⚠️ Wait for 1.0 |
| **CAPI** | Medium | High | ✅ K8s-native | ✅ For K3s lifecycle |
| **TF Controller** | Production | Medium-High | ⚠️ Adds TF layer | ✅ Mature option |
| **Ansible** | Production | Low | ❌ Not K8s-native | ❌ You said no |

---

## Recommended Approach (Based on Your Answers)

**Summary**:
- Skip CAPI (2-VM K3s setup is stable)
- Try Crossplane now (willing to be early adopter)
- TF Controller as fallback (pure GitOps is acceptable)
- Keep Python for host-level ops
- **KRO**: Optional composition layer on top of Crossplane

### Architecture Options

**Option A: Crossplane Only (Simpler)**
```
Flux → Crossplane EnvironmentVM CRs → Proxmox API → VMs
```

**Option B: Crossplane + KRO (More Powerful)**
```
Flux → KRO ResourceGraphDefinition → Crossplane CRs + K8s workloads → Proxmox + K8s
```

**When to add KRO**: If you want to define custom APIs like `K3sNode` that bundle VM creation + workload deployment with dependency ordering. Not needed if you just want VMs as K8s resources.

---

### Phase 1: Crossplane for Proxmox Resources

**Install Crossplane + provider-proxmox-bpg**:
```bash
# In gitops/clusters/homelab/infrastructure/crossplane/
helm install crossplane crossplane-stable/crossplane -n crossplane-system --create-namespace

# Provider
kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-proxmox-bpg
spec:
  package: xpkg.upbound.io/valkiriaaquaticamendi/provider-proxmox-bpg:v0.11.1
EOF
```

**Migrate These Resources**:

| Python Code | Crossplane CRD | Priority |
|-------------|----------------|----------|
| `VMManager.create_vm()` | `EnvironmentVM` | P1 |
| `PBSStorageManager` | Storage CRs | P2 |
| Network bridges | `EnvironmentNetworkLinuxBridge` | P3 |
| Firewall rules | Firewall CRs | P3 |

**Example VM Definition** (`gitops/clusters/homelab/infrastructure/proxmox-vms/`):
```yaml
apiVersion: virtualenvironmentvm.crossplane.io/v1alpha1
kind: EnvironmentVM
metadata:
  name: k3s-vm-still-fawn
spec:
  forProvider:
    nodeName: still-fawn
    name: k3s-vm-still-fawn
    vmId: 108
    started: true
    agent:
      enabled: true
    cpu:
      cores: 4
      type: host
    memory:
      dedicated: 16384
    disk:
      - interface: scsi0
        size: 100
        storage: local-zfs
        iothread: true
        ssd: true
    network:
      - bridge: vmbr0
        model: virtio
    initialization:
      type: cloud-init
      datastoreId: local-zfs
  providerConfigRef:
    name: proxmox-provider
```

---

### Phase 2: TF Controller as Fallback

**If Crossplane hits blockers** (missing resources, bugs), switch to TF Controller:

```yaml
# gitops/clusters/homelab/infrastructure/tofu-controller/terraform.yaml
apiVersion: infra.contrib.fluxcd.io/v1alpha2
kind: Terraform
metadata:
  name: proxmox-vms
  namespace: flux-system
spec:
  path: ./terraform/proxmox
  sourceRef:
    kind: GitRepository
    name: home
  approvePlan: auto
  interval: 30m
  destroyResourcesOnDeletion: false
  storeReadablePlan: human
  vars:
    - name: proxmox_api_url
      valueFrom:
        secretKeyRef:
          name: proxmox-credentials
          key: api_url
```

**Terraform files** would live in `terraform/proxmox/`:
```hcl
# terraform/proxmox/main.tf
terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.89.0"
    }
  }
}

resource "proxmox_virtual_environment_vm" "k3s_still_fawn" {
  node_name = "still-fawn"
  vm_id     = 108
  name      = "k3s-vm-still-fawn"
  # ... same config as Crossplane
}
```

---

### Phase 3: Keep as Python CLI (Host-Level)

**These stay in `proxmox/homelab/src/homelab/`**:

| Module | Reason |
|--------|--------|
| `storage_manager.py` | ZFS commands run via SSH on host |
| `gpu_passthrough_manager.py` | Kernel modules, IOMMU groups |
| `coral_automation.py` | USB device passthrough |
| `health_checker.py` | Diagnostic, not declarative |
| `resource_manager.py` | Pure computation |

**Optional**: Create a "bootstrap" category in your Python CLI that these ops fall under, clearly separating them from GitOps-managed resources.

---

### Migration Roadmap

```
Week 1: Install Crossplane + provider-proxmox-bpg
Week 2: Define first VM (test VM, not production) as Crossplane CR
Week 3: Validate drift detection, reconciliation
Week 4: If stable, migrate PBS storage entry
Week 5: If unstable, pivot to TF Controller

Ongoing: Keep Python CLI for ZFS/GPU/host operations
```

---

### Files to Create (GitOps)

```
gitops/clusters/homelab/
├── infrastructure/
│   ├── crossplane/
│   │   ├── namespace.yaml
│   │   ├── helmrelease.yaml      # Crossplane Helm
│   │   ├── provider.yaml         # provider-proxmox-bpg
│   │   └── providerconfig.yaml   # Proxmox API credentials
│   └── proxmox-vms/
│       ├── kustomization.yaml
│       ├── k3s-vm-still-fawn.yaml
│       └── k3s-vm-pumped-piglet.yaml
```

---

### What Gets Retired from Python

Once GitOps manages VMs:
- `VMManager.create_vm()` - replaced by Crossplane
- `VMManager.delete_vm()` - replaced by Crossplane
- `PBSStorageManager.register_storage()` - replaced by Crossplane
- `unified_infrastructure_manager.py` - fully replaced by Flux reconciliation

**Keep**:
- `VMManager.start/stop_vm()` - imperative ops, keep as CLI
- `VMManager.check_health()` - diagnostic
- All host-level managers

---

---

## Real Usage Analysis (from Git History)

**729 total commits since Jan 2025, ~205 infrastructure-related**

### Category Breakdown (Actual Use Cases)

| Use Case | Commits | Examples | GitOps? |
|----------|---------|----------|---------|
| **Device Migration (Coral/GPU)** | ~10 | `migrate Coral TPU from pumped-piglet to still-fawn` | ❌ Host USB/PCI |
| **K8s Workload Migration** | ~10 | `migrate Samba to k3s-vm-pumped-piglet-gpu` | ✅ Already GitOps |
| **GPU/Device Passthrough** | ~15 | `/sys mount for AMD GPU`, `VAAPI hwaccel` | ❌ Host + Pod |
| **Backup/PBS Config** | ~12 | `PBS migration`, `exclude 18TB from backups` | ⚠️ Partial |
| **VM Creation (one-time)** | ~8 | `idempotent VM creation`, `UEFI + Q35` | ✅ Crossplane |
| **LXC Config** | ~5 | `Frigate LXC 113 backup configs` | ✅ Crossplane |
| **Coral TPU USB Mapping** | ~8 | `udev rules`, `coral-tpu-init service` | ❌ Host-level |

### Key Insight: Most "Proxmox Work" is NOT VM/LXC CRUD

**Top 3 actual operations:**
1. **Device passthrough reconfiguration** - Moving Coral/GPU between hosts (host-level, NOT GitOps)
2. **K8s workload placement** - nodeSelector changes (ALREADY GitOps via Flux)
3. **Backup configuration** - PBS storage, exclusions (partial GitOps candidate)

**VM/LXC creation is RARE** - ~13 commits total out of 729 (1.8%)

### Key Observations

**1. Most "Proxmox work" is actually K8s workload config**
- GPU mounts, device passthrough to pods
- Node selectors, tolerations
- PVC recreation for node migration
- **These are ALREADY GitOps** (Flux manages them)

**2. Actual Proxmox API operations are rare**
- VM creation: ~5 commits (one-time setup)
- LXC creation: ~2 commits (Frigate LXC 113)
- Storage registration: ~3 commits (PBS)

**3. Host-level operations dominate the "non-GitOps" work**
- USB device passthrough (`/dev/bus/usb`)
- GPU passthrough (`/dev/dri`, `/sys`)
- Kernel modules (VFIO, nouveau blacklist)
- udev rules for Coral TPU

### What This Means for GitOps Migration

**HIGH VALUE** (frequent, declarative):
- K8s workload placement (node selectors) - **Already GitOps**
- PVC/storage claims - **Already GitOps**
- Ingress/services - **Already GitOps**

**MEDIUM VALUE** (rare, but declarative):
- VM definitions - **Would benefit from Crossplane**:
  - k3s-vm-still-fawn (192.168.4.212) - K3s control-plane, 35d old
  - k3s-vm-pumped-piglet-gpu (192.168.4.210) - K3s control-plane, 57d old
  - k3s-vm-pve (192.168.4.238) - K3s control-plane, 217d old (oldest node)
  - HAOS VM (VMID 116 on chief-horse)
- LXC definitions - **Would benefit from Crossplane**:
  - LXC 113: Frigate on fun-bedbug (Coral TPU)
- PBS storage entries - **Would benefit from Crossplane**

**LOW VALUE** (host-level, imperative):
- GPU passthrough config - **Keep as scripts**
- USB/Coral TPU mapping - **Keep as scripts**
- ZFS pool operations - **Keep as scripts** (must run ON host)

### Storage Management Deep Dive

**Current Python Implementation Struggles:**

| Issue | Details |
|-------|---------|
| SSH localhost calls | `storage_manager.py` tried to SSH to itself when running on host |
| DNS unreliable | PBS hostname resolution failed, forced static IP workaround |
| Where to run? | ZFS commands need host access, can't run remotely |

**What CAN move to GitOps:**
- **PBS storage entries** (`pbs_storage_manager.py`) - API-based, works remotely
- **Proxmox storage registration** - API-based

**What CANNOT move to GitOps:**
- **ZFS pool create/import** - runs `zpool` commands on host
- **ZFS dataset creation** - runs `zfs` commands on host
- **Pool properties** - host-level

### Revised Recommendation

Given the actual usage patterns:

1. **Don't over-engineer** - Most infra work is already GitOps via Flux for K8s
2. **Crossplane for the "big 6"**:
   - 3 K3s VMs:
     - k3s-vm-still-fawn (192.168.4.212)
     - k3s-vm-pumped-piglet-gpu (192.168.4.210)
     - k3s-vm-pve (192.168.4.238)
   - 1 HAOS VM (VMID 116 on chief-horse)
   - 1 LXC container (Frigate 113 on fun-bedbug)
   - PBS storage entries
3. **Skip KRO** - Not enough composition complexity to justify another layer
4. **Containerize Python CLI** - For host-level operations (GPU, USB, ZFS), run via K8s Jobs

### Why Crossplane Over TF Controller (Final Decision)

**TF Controller** has a more mature underlying provider, but:

| Factor | TF Controller | Crossplane |
|--------|---------------|------------|
| **Languages** | HCL + YAML | Just YAML |
| **State management** | Must manage TF state | None |
| **Feels like K8s** | No | Yes |
| **Looping/deps** | HCL syntax | K8s-native |
| **Debugging** | `terraform plan` | `kubectl describe` |
| **Learning curve** | Learn HCL | Already know K8s |

**Risk mitigation for Crossplane's immaturity:**
- Provider is **auto-generated** from bpg/terraform-provider-proxmox via Upjet
- Upstream TF fixes flow automatically (Renovate bot triggers rebuilds)
- Not betting on wrapper maintainer's custom code
- Worst case: fork and run Upjet generator yourself
- Migration path to TF Controller exists (same underlying provider)

**Bottom line**: The maintenance risk is acceptable because Crossplane is a thin, auto-generated wrapper. You get better UX without betting on custom code.

### Crossplane Core Features (CNCF Graduated - Oct 2025)

**Critical insight**: The features you care about most are **Crossplane core**, not provider-specific:

| Feature | Where It Lives | Maintenance |
|---------|----------------|-------------|
| `readinessChecks` | Crossplane Composition Engine | ✅ CNCF graduated, 3000+ contributors |
| Dependency ordering | Crossplane Composition Engine | ✅ CNCF graduated |
| "Wait for ready" | Crossplane Runtime | ✅ CNCF graduated |
| Reconciliation loop | Crossplane Runtime | ✅ CNCF graduated |
| Status conditions | Crossplane Runtime | ✅ CNCF graduated |

**readinessChecks types (all core Crossplane):**
```yaml
readinessChecks:
  - type: MatchString
    fieldPath: status.atProvider.state
    matchString: "running"
  - type: MatchCondition
    matchCondition:
      type: Ready
      status: "True"
```

**The Proxmox provider only needs to:**
1. Create/update/delete resources via API (inherited from TF provider)
2. Report status back (inherited from TF provider)

**Crossplane core handles:**
- Waiting for resources to be ready
- Ordering resource creation
- Retrying failures
- Drift detection
- Reconciliation

This is why TF's "wait for ready" pain goes away - Crossplane's battle-tested core (used by NASA, Nike, IBM) handles it, not the Proxmox provider.

**Sources:**
- [Crossplane CNCF Graduation Announcement](https://www.cncf.io/announcements/2025/11/06/cloud-native-computing-foundation-announces-graduation-of-crossplane/)
- [Crossplane Composition Dependencies](https://github.com/crossplane/crossplane/issues/2072)

---

## Python Functionality Analysis: What Can Be Flux-Controlled?

### Current Python Modules (32 files)

| Module | Purpose | Execution Context | Flux Integration Path |
|--------|---------|-------------------|----------------------|
| **API-Based (Remote)** | | | |
| `proxmox_api.py` | Proxmox API wrapper | Remote | ✅ Crossplane replaces |
| `vm_manager.py` | VM CRUD | Remote | ✅ Crossplane replaces |
| `pbs_storage_manager.py` | PBS storage entries | Remote | ✅ Crossplane replaces |
| `uptime_kuma_client.py` | Monitoring API | Remote | ✅ K8s CronJob |
| `health_checker.py` | VM status checks | Remote | ✅ K8s CronJob |
| **Host-Level (SSH/Local)** | | | |
| `storage_manager.py` | ZFS pool/dataset | ON host | 🔄 K8s Job + SSH |
| `gpu_passthrough_manager.py` | VFIO/IOMMU setup | ON host | 🔄 K8s Job + SSH |
| `coral_*.py` (5 files) | Coral TPU management | ON host | 🔄 K8s Job + SSH |
| `k3s_manager.py` | K3s install/join | ON host (VM) | 🔄 K8s Job + SSH |
| `k3s_ssh_manager.py` | SSH key management | ON host | 🔄 K8s Job + SSH |
| `iso_manager.py` | ISO upload to nodes | ON host | 🔄 K8s Job + SSH |
| **Orchestration** | | | |
| `unified_infrastructure_manager.py` | YAML reconciliation | Mixed | ⚠️ Flux replaces |
| `infrastructure_orchestrator.py` | Multi-step workflows | Mixed | ⚠️ Flux replaces |
| `pumped_piglet_migration.py` | One-time migration | Mixed | 🗑️ Deprecate |
| **CLI/Config** | | | |
| `cli.py`, `pbs_cli.py`, `homelab_cli.py` | User interfaces | Local | Keep as-is |
| `config.py`, `*_config.py` | Configuration | N/A | Keep as-is |

### Flux Integration Patterns

**Pattern 1: Crossplane for API Operations**
```
Flux Kustomization → Crossplane CRD → Proxmox API
```
Replaces: `vm_manager.py`, `pbs_storage_manager.py`, parts of `storage_manager.py`

**Pattern 2: K8s Job + SSH for Host Operations**
```yaml
# Flux triggers K8s Job that SSHs to Proxmox host
apiVersion: batch/v1
kind: Job
metadata:
  name: zfs-pool-setup
spec:
  template:
    spec:
      containers:
      - name: ansible-runner
        image: ansible/ansible-runner
        command: ["ansible-playbook", "-i", "hosts", "zfs-setup.yml"]
        volumeMounts:
        - name: ssh-key
          mountPath: /root/.ssh
      volumes:
      - name: ssh-key
        secret:
          secretName: proxmox-ssh-key
```
For: `storage_manager.py` (ZFS), `gpu_passthrough_manager.py`, `coral_*.py`

**Pattern 3: K8s CronJob for Monitoring/Health**
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: proxmox-health-check
spec:
  schedule: "*/5 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: health-checker
            image: ghcr.io/homeiac/homelab-cli:latest
            command: ["homelab", "health", "--json"]
```
For: `health_checker.py`, `uptime_kuma_client.py`

### Containerizing the Python CLI

To make host operations Flux-controlled:

1. **Build container image** with homelab CLI:
```dockerfile
FROM python:3.11-slim
RUN pip install poetry
COPY proxmox/homelab /app
WORKDIR /app
RUN poetry install
ENTRYPOINT ["poetry", "run", "homelab"]
```

2. **Push to registry** (ghcr.io/homeiac/homelab-cli)

3. **Flux triggers Jobs** that run CLI commands:
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: coral-tpu-init
  annotations:
    fluxcd.io/automated: "true"
spec:
  template:
    spec:
      containers:
      - name: homelab
        image: ghcr.io/homeiac/homelab-cli:latest
        command: ["homelab", "coral", "init", "--host", "fun-bedbug.maas"]
        env:
        - name: PROXMOX_PASSWORD
          valueFrom:
            secretKeyRef:
              name: proxmox-credentials
              key: password
```

### What This Achieves

| Before | After |
|--------|-------|
| Run Python scripts manually | Flux reconciles desired state |
| No drift detection | Continuous reconciliation |
| SSH from laptop | SSH from K8s Job (more reliable) |
| Scattered credentials | K8s Secrets (SOPS encrypted) |
| No audit trail | Git commits = audit log |

### Recommended Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Flux GitOps                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Crossplane  │  │  K8s Jobs   │  │   K8s CronJobs     │ │
│  │             │  │  (one-time) │  │   (monitoring)      │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                     │            │
│    Proxmox API      SSH to hosts         Proxmox API       │
│         │                │                     │            │
│  ┌──────▼──────┐  ┌──────▼──────┐      ┌──────▼──────┐    │
│  │ VMs, LXC,   │  │ ZFS, GPU,   │      │ Health,     │    │
│  │ PBS Storage │  │ Coral TPU   │      │ Uptime Kuma │    │
│  └─────────────┘  └─────────────┘      └─────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Sources

- [Crossplane provider-proxmox-bpg](https://github.com/valkiriaaquatica/provider-proxmox-bpg)
- [bpg/terraform-provider-proxmox](https://github.com/bpg/terraform-provider-proxmox)
- [Kubemox](https://github.com/alperencelik/kubemox)
- [proxmox-operator](https://github.com/CRASH-Tech/proxmox-operator)
- [IONOS CAPMOX](https://github.com/ionos-cloud/cluster-api-provider-proxmox)
- [Tofu Controller](https://github.com/flux-iac/tofu-controller)
- [KRO](https://kro.run/)
- [Proxmox-GitOps (Ansible example)](https://github.com/stevius10/Proxmox-GitOps)
