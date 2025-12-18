# Homelab as Oxide: Unified Control Plane Vision

## Goal

Build an **Oxide Computer-like UX** for your homelab:
- Single API for compute, storage, network
- Hardware abstraction (don't care which host, just give me resources)
- Full IaC - including GPU passthrough, VFIO, cloud-init
- Self-service provisioning with cloud-like experience

---

## Current State Assessment

### What You Already Have (Oxide-Aligned)

| Oxide Concept | Your Implementation | Status |
|---------------|---------------------|--------|
| **Crucible (Storage)** | `oxide_storage_api.py` + MA90 sled + PBS | ✅ POC complete |
| **Disk lifecycle** | DiskCreate, attach/detach, snapshots | ✅ Working |
| **Sled (Compute)** | Proxmox hosts (still-fawn, pumped-piglet, etc.) | ✅ Working |
| **Control Plane** | Python CLI + Flux GitOps | ⚠️ Fragmented |
| **Instance API** | `enhanced_vm_manager.py` | ⚠️ Partial |
| **Networking** | Manual Proxmox config | ❌ Not abstracted |
| **Hardware passthrough** | `gpu_passthrough_manager.py` | ❌ Manual/imperative |

### What's Missing for Oxide-like UX

1. **Unified API** - Currently 10+ separate Python modules, no single endpoint
2. **Instance abstraction** - Can't say "give me VM with GPU" without knowing host
3. **Network as code** - VPC/subnet concepts don't exist
4. **Cloud-init integration** - Works but not tied to instance API
5. **Device passthrough as resource** - GPU/Coral are host-specific, not pool resources

---

## Oxide Architecture → Homelab Mapping

### Oxide's Stack
```
User Request (API/CLI/Portal)
    ↓
Control Plane (Nexus)
    ↓
├── Instance Service → Sled Agent → Propolis (VM)
├── Storage Service → Crucible → Disks/Snapshots
├── Network Service → OPTE → VPCs/Subnets
└── Identity Service → Silos/Projects/Users
```

### Your Target Stack
```
User Request (unified CLI / K8s CRDs / REST API)
    ↓
Homelab Control Plane (to build)
    ↓
├── Instance Service → Proxmox API → VMs/LXCs
├── Storage Service → Crucible/PBS → Disks/Backups (✅ exists)
├── Network Service → OPNsense/Proxmox → VLANs/Bridges
├── Device Service → MAAS + cloud-init → GPU/Coral/USB
└── K8s Workloads → Flux → Deployments
```

---

## The Gap: MAAS + Cloud-Init + Device Passthrough

You identified this as the key missing piece. Let's break it down:

### Current MAAS Flow
```
MAAS deploys Ubuntu → Manual cloud-init → Manual VFIO/GPU setup
```

### Desired Flow (Oxide-like)
```
API: "Create instance with GPU"
    → MAAS/Proxmox picks host with GPU
    → Cloud-init configures VFIO/modules automatically
    → Instance boots with GPU attached
```

### What's Required

1. **Device Inventory** - Know which hosts have which devices (GPU, Coral, etc.)
2. **Cloud-init Templates** - Per-device-class templates for kernel modules, VFIO
3. **Scheduler** - Match "instance needs GPU" to "host has GPU"
4. **Post-deploy Hooks** - Verify device passthrough worked

---

## Implementation Approach

### Option A: Extend Python + Crossplane (Incremental)

Build on existing Python modules, add Crossplane for declarative IaC:

```
┌─────────────────────────────────────────────────┐
│                  Flux GitOps                     │
├─────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌─────────────────────────┐ │
│  │  Crossplane  │  │  Homelab Controller     │ │
│  │  (VM/LXC/PBS)│  │  (Python → K8s Job)     │ │
│  └──────┬───────┘  └──────────┬──────────────┘ │
│         │                     │                 │
│    Proxmox API           SSH to hosts          │
│         │                     │                 │
│  ┌──────▼──────┐       ┌──────▼──────┐        │
│  │ VMs, LXC,   │       │ GPU setup,  │        │
│  │ Storage     │       │ cloud-init  │        │
│  └─────────────┘       └─────────────┘        │
└─────────────────────────────────────────────────┘
```

**Pros**: Builds on existing work, incremental
**Cons**: Still fragmented (Crossplane + Python + MAAS)

### Option B: Build Homelab Nexus (Unified API)

Create a single REST API that wraps everything:

```python
# Unified Homelab API (new)
POST /api/v1/instances
{
  "name": "gpu-worker-1",
  "cpu": 4,
  "memory_gb": 16,
  "devices": ["gpu"],           # Abstract - scheduler picks host
  "disk_size_gb": 100,          # → Crucible backend
  "network": "k3s-cluster",     # → Proxmox bridge
  "cloud_init": "k3s-node"      # → Template with VFIO setup
}

# Response
{
  "id": "inst-123",
  "name": "gpu-worker-1",
  "host": "still-fawn",         # Scheduler chose this
  "ip": "192.168.4.215",
  "gpu": "RTX 3070",            # What it got
  "state": "running"
}
```

**Pros**: True Oxide-like UX, single source of truth
**Cons**: Significant new development, overlaps with existing tools

### Option C: KRO + Crossplane (K8s-Native)

Use KRO to define custom `Instance` CRD that composes Crossplane resources:

```yaml
apiVersion: homelab.io/v1alpha1
kind: Instance
metadata:
  name: gpu-worker-1
spec:
  cpu: 4
  memory: 16Gi
  devices:
    - type: gpu
  storage:
    size: 100Gi
    class: crucible
  network: k3s-cluster
  cloudInit: k3s-gpu-node
```

KRO translates to:
1. Crossplane `EnvironmentVM` on host with GPU
2. Crucible disk via `oxide_storage_api`
3. Cloud-init ConfigMap with VFIO setup

**Pros**: Pure K8s, Flux-native, uses existing Crossplane decision
**Cons**: KRO adds complexity, MAAS still separate

---

## Recommended Path: Phased Approach

### Phase 1: Device Inventory & Scheduler (Foundation)

**Goal**: Know what resources exist where, enable "give me VM with GPU"

#### 1.1 Create Hybrid Device Discovery

**Auto-discovery script** (`scripts/discovery/scan-hosts.sh`):
```bash
# Queries each Proxmox host for:
# - lspci | grep -i nvidia/amd (GPUs)
# - lsusb | grep -i coral (TPUs)
# - /dev/dri/* (render devices)
# Outputs JSON for merging with manual config
```

**Manual inventory** (`config/device-inventory.yaml`):
```yaml
hosts:
  still-fawn:
    gpu:
      type: nvidia-rtx-3070
      pcie_slot: "01:00.0"
      vfio_ids: ["10de:2484", "10de:228b"]
    available: true  # Can override auto-discovery
  pumped-piglet:
    gpu: null
    usb_devices: []
  fun-bedbug:
    coral_tpu:
      type: usb
      path: /dev/bus/usb/002/003
      vendor_id: "1a6e:089a"
  chief-horse:
    role: haos-host  # No VM placement
```

**Python module** (`proxmox/homelab/src/homelab/device_inventory.py`):
```python
class DeviceInventory:
    def __init__(self, config_path: str, enable_discovery: bool = True):
        self.manual_config = load_yaml(config_path)
        if enable_discovery:
            self.discovered = self._discover_devices()
        self.merged = self._merge_configs()

    def find_host_with(self, requirements: List[str]) -> Optional[str]:
        """Find host that satisfies device requirements."""
        # e.g., requirements=["gpu"] → returns "still-fawn"

    def get_device_config(self, host: str, device: str) -> Dict:
        """Get device-specific config for cloud-init generation."""
```

#### 1.2 Scheduler Integration

**Modify** `vm_manager.py`:
```python
def create_vm(
    self,
    name: str,
    devices: List[str] = None,  # NEW: ["gpu", "coral_tpu"]
    node: str = None,  # Optional override
    ...
):
    if devices and not node:
        node = self.inventory.find_host_with(devices)
        if not node:
            raise NoHostAvailable(f"No host has: {devices}")
    # Continue with VM creation on selected node
```

### Phase 2: Cloud-Init Templates for Devices

**Goal**: "Instance with GPU" auto-configures VFIO, kernel modules

#### 2.1 Template Library Structure

```
proxmox/cloud-init-templates/
├── base.yaml              # SSH keys, users, packages
├── devices/
│   ├── gpu-nvidia.yaml    # VFIO-PCI, nvidia-container-toolkit
│   ├── gpu-amd.yaml       # AMDGPU, VAAPI
│   └── coral-tpu.yaml     # udev rules, libedgetpu
├── roles/
│   ├── k3s-node.yaml      # K3s agent install, kubeconfig
│   ├── k3s-server.yaml    # K3s server + etcd
│   └── docker-host.yaml   # Docker CE, compose
└── composer.py            # Merges templates based on requirements
```

#### 2.2 Example: GPU Template

**`proxmox/cloud-init-templates/devices/gpu-nvidia.yaml`**:
```yaml
#cloud-config
write_files:
  - path: /etc/modprobe.d/vfio.conf
    content: |
      options vfio-pci ids={{ vfio_ids | join(',') }}
      softdep nouveau pre: vfio-pci
  - path: /etc/modules-load.d/vfio.conf
    content: |
      vfio
      vfio_iommu_type1
      vfio_pci

runcmd:
  - update-initramfs -u
  # Install NVIDIA container toolkit for K8s GPU pods
  - curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  - apt-get update && apt-get install -y nvidia-container-toolkit
```

#### 2.3 Template Composer

**`proxmox/homelab/src/homelab/cloud_init_composer.py`**:
```python
class CloudInitComposer:
    def compose(self,
                base: str = "base",
                devices: List[str] = None,
                roles: List[str] = None,
                variables: Dict = None) -> str:
        """
        Compose cloud-init from multiple templates.

        Example:
            compose(devices=["gpu-nvidia"], roles=["k3s-node"],
                    variables={"vfio_ids": ["10de:2484"]})
        """
        templates = [self.load(base)]
        for device in (devices or []):
            templates.append(self.load(f"devices/{device}"))
        for role in (roles or []):
            templates.append(self.load(f"roles/{role}"))

        merged = self._deep_merge(templates)
        return self._render(merged, variables)
```

### Phase 3: Unified Instance API (K8s CRD + REST + CLI)

**Goal**: Single interface for all instance operations - K8s native with CLI and REST

#### 3.1 Custom Resource Definition

**`gitops/clusters/homelab/crds/instance-crd.yaml`**:
```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: instances.homelab.io
spec:
  group: homelab.io
  versions:
    - name: v1alpha1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                cpu:
                  type: integer
                memory:
                  type: string  # "16Gi"
                devices:
                  type: array
                  items:
                    type: string  # ["gpu", "coral_tpu"]
                storage:
                  type: object
                  properties:
                    size:
                      type: string  # "100Gi"
                    class:
                      type: string  # "crucible" | "local-zfs"
                roles:
                  type: array
                  items:
                    type: string  # ["k3s-node"]
                node:
                  type: string  # Optional: force specific host
            status:
              type: object
              properties:
                phase:
                  type: string  # Creating, Running, Failed
                host:
                  type: string  # Assigned Proxmox host
                ip:
                  type: string
                devices:
                  type: object  # What was actually attached
  scope: Namespaced
  names:
    plural: instances
    singular: instance
    kind: Instance
```

#### 3.2 Homelab Controller (Kopf-based)

**`proxmox/homelab/src/homelab/controller.py`**:
```python
import kopf
from homelab.device_inventory import DeviceInventory
from homelab.cloud_init_composer import CloudInitComposer
from homelab.vm_manager import VMManager

@kopf.on.create('homelab.io', 'v1alpha1', 'instances')
async def create_instance(spec, name, namespace, **kwargs):
    inventory = DeviceInventory()
    composer = CloudInitComposer()
    vm_manager = VMManager()

    # 1. Find host with required devices
    devices = spec.get('devices', [])
    host = spec.get('node') or inventory.find_host_with(devices)

    # 2. Compose cloud-init
    device_configs = [inventory.get_device_config(host, d) for d in devices]
    cloud_init = composer.compose(
        devices=devices,
        roles=spec.get('roles', []),
        variables={'vfio_ids': device_configs[0].get('vfio_ids', [])}
    )

    # 3. Create VM via Proxmox API
    vm = await vm_manager.create_vm(
        name=name,
        node=host,
        cpu=spec['cpu'],
        memory=spec['memory'],
        cloud_init=cloud_init,
        devices=devices
    )

    return {'host': host, 'vmid': vm['vmid'], 'phase': 'Running'}
```

#### 3.3 CLI Interface

**`homelab_cli.py` additions**:
```python
@app.command("instance")
def instance_cmd():
    """Manage instances (VMs with device abstraction)."""
    pass

@instance_cmd.command("create")
def instance_create(
    name: str,
    cpu: int = 2,
    memory: str = "4Gi",
    device: List[str] = [],
    role: List[str] = [],
    node: str = None
):
    """Create instance - applies CRD or calls controller directly."""
    # Option 1: Create K8s CRD
    # Option 2: Direct Python call (for testing)

@instance_cmd.command("list")
def instance_list():
    """List all instances (queries K8s + Proxmox)."""

@instance_cmd.command("status")
def instance_status(name: str):
    """Get instance status (REST query to controller)."""
```

#### 3.4 REST API for Queries

**`proxmox/homelab/src/homelab/api.py`** (FastAPI):
```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/api/v1/instances")
async def list_instances():
    """Query all instances across hosts."""

@app.get("/api/v1/instances/{name}")
async def get_instance(name: str):
    """Get instance details + real-time status from Proxmox."""

@app.get("/api/v1/devices")
async def list_devices():
    """List available devices across all hosts."""

@app.get("/api/v1/hosts/{host}/capacity")
async def host_capacity(host: str):
    """Get host resource availability."""
```

### Phase 4: Network Abstraction

**Goal**: VPC-like isolation without manual bridge config

1. **Network catalog** (similar to device inventory):
   ```yaml
   networks:
     k3s-cluster:
       bridge: vmbr0
       vlan: null
       subnet: 192.168.4.0/24
       gateway: 192.168.4.1
     iot-isolated:
       bridge: vmbr1
       vlan: 100
       subnet: 192.168.100.0/24
   ```

2. **Instance API uses network names**, not bridge IDs

### Phase 5: Full IaC via Crossplane

**Goal**: All state in Git, Flux reconciles

1. **Device inventory as K8s ConfigMap** (Flux-managed)
2. **Instances as Crossplane CRDs**
3. **Cloud-init templates as K8s ConfigMaps**
4. **Python CLI for imperative ops only** (debug, one-time setup)

---

## Files to Create/Modify

### Phase 1 Files

| File | Purpose |
|------|---------|
| `config/device-inventory.yaml` | Manual device catalog (hosts, GPUs, TPUs) |
| `scripts/discovery/scan-hosts.sh` | Auto-discovery script |
| `proxmox/homelab/src/homelab/device_inventory.py` | Hybrid inventory loader + query |

### Phase 2 Files

| File | Purpose |
|------|---------|
| `proxmox/cloud-init-templates/base.yaml` | Common cloud-init (SSH, users) |
| `proxmox/cloud-init-templates/devices/gpu-nvidia.yaml` | VFIO + nvidia-container-toolkit |
| `proxmox/cloud-init-templates/devices/gpu-amd.yaml` | AMDGPU + VAAPI |
| `proxmox/cloud-init-templates/devices/coral-tpu.yaml` | udev rules + libedgetpu |
| `proxmox/cloud-init-templates/roles/k3s-node.yaml` | K3s agent bootstrap |
| `proxmox/homelab/src/homelab/cloud_init_composer.py` | Template merger |

### Phase 3 Files

| File | Purpose |
|------|---------|
| `gitops/clusters/homelab/crds/instance-crd.yaml` | Instance CRD definition |
| `proxmox/homelab/src/homelab/controller.py` | Kopf-based K8s controller |
| `proxmox/homelab/src/homelab/api.py` | FastAPI REST endpoints |

### Modify Existing

| File | Changes |
|------|---------|
| `proxmox/homelab/src/homelab/vm_manager.py` | Add `devices` param, scheduler integration |
| `proxmox/homelab/src/homelab/homelab_cli.py` | Add `instance` subcommand group |
| `proxmox/homelab/pyproject.toml` | Add kopf, fastapi dependencies |

### GitOps Structure

```
gitops/clusters/homelab/
├── crds/
│   └── instance-crd.yaml
├── infrastructure/
│   └── homelab-controller/
│       ├── deployment.yaml      # Controller pod
│       └── rbac.yaml            # ServiceAccount + ClusterRole
└── instances/
    ├── k3s-gpu-worker.yaml      # Example Instance CR
    └── frigate-lxc.yaml         # Example LXC Instance
```

---

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **API Style** | K8s CRDs + REST for queries + CLI | Best of all worlds: GitOps via CRDs, dynamic queries via REST, user-friendly CLI |
| **Device Discovery** | Hybrid | Auto-discover devices, allow manual overrides in YAML |
| **MAAS Integration** | Proxmox-only for now | Focus on VM provisioning, MAAS for bare metal later |
| **Network Priority** | Later phase | Get compute + devices working first |

---

## Refined Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interfaces                          │
├─────────────────────────────────────────────────────────────────┤
│  homelab CLI        kubectl/CRDs         REST API (read-only)   │
│  (imperative)       (declarative)        (queries/status)       │
└────────┬─────────────────┬────────────────────┬─────────────────┘
         │                 │                    │
         ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Homelab Control Plane                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  Crossplane │  │  Homelab    │  │  Device Discovery       │ │
│  │  Provider   │  │  Controller │  │  (hybrid auto+manual)   │ │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘ │
│         │                │                     │                 │
│         ▼                ▼                     ▼                 │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────────┐   │
│  │ Proxmox API │  │ Cloud-Init  │  │ Device Inventory      │   │
│  │ (VMs/LXC)   │  │ Templates   │  │ (GPU/Coral/USB)       │   │
│  └─────────────┘  └─────────────┘  └───────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Success Criteria

**Oxide-like UX achieved when:**
- [ ] Can request "VM with GPU" without specifying host
- [ ] Cloud-init automatically configures device passthrough
- [ ] All instance state visible in one place (API/CLI)
- [ ] Network assigned by name, not bridge ID
- [ ] GPU/Coral/USB devices are pool resources, not host-specific
- [ ] IaC: Git commit → infrastructure changes

---

## Quick Start: Phase 1 Implementation

**Immediate next steps to begin:**

1. **Create device inventory file**:
   ```bash
   # config/device-inventory.yaml
   # Document current hardware across all Proxmox hosts
   ```

2. **Create discovery script**:
   ```bash
   # scripts/discovery/scan-hosts.sh
   # SSH to each host, run lspci/lsusb, output JSON
   ```

3. **Implement DeviceInventory class**:
   ```bash
   # proxmox/homelab/src/homelab/device_inventory.py
   # ~100 lines: load YAML, merge with discovery, query methods
   ```

4. **Test scheduler integration**:
   ```bash
   # Modify vm_manager.py to accept devices=[] param
   # Test: VMManager().create_vm(name="test", devices=["gpu"])
   ```

**Estimated effort**: Phase 1 = 1-2 days

---

## Sources

- [Oxide Documentation](https://docs.oxide.computer)
- [Oxide API Reference](https://docs.oxide.computer/api)
- Existing codebase: `proxmox/homelab/src/homelab/`
- Your Crucible POC: `oxide_storage_api.py`, `crucible_config.py`
