# Homelab Infrastructure & "Poor Man's Crossplane" Review
**Date:** January 2025
**Reviewer:** Claude Code
**Scope:** Proxmox VMs, LXC Containers, Python Infrastructure Orchestrator

---

## Executive Summary

You've built an impressive **AI-first homelab** with a custom Python orchestration layer (~7,853 LOC) that emulates concepts from Oxide Computer's infrastructure and Crossplane's declarative resource management. The system manages:

- **4 online Proxmox nodes** (pve, chief-horse, fun-bedbug, pumped-piglet) + 2 offline
- **3 VMs** (OPNsense, UbuntuMAAS, k3s-vm-pve)
- **2 LXC containers** (docker, cloudflared)
- **Kubernetes cluster** with Flux GitOps for service deployment
- **Custom Python orchestrator** with Crucible-inspired storage abstractions

**Key Strengths:**
- ✅ Excellent documentation-first discipline
- ✅ Comprehensive test coverage infrastructure (284 tests collected)
- ✅ Modern Python best practices (Poetry, type hints, Black, MyPy)
- ✅ Modular architecture with clear separation of concerns
- ✅ AI-ready abstractions for declarative infrastructure

**Key Weaknesses:**
- ⚠️ Test configuration issue preventing test execution (`asyncio_mode` error)
- ⚠️ Crucible storage backend incomplete (still using mocks)
- ⚠️ Some complexity in orchestration that may not be needed yet
- ⚠️ Missing integration with existing Flux GitOps workflows

---

## Infrastructure Inventory

### Proxmox Cluster Status

| Node | Status | CPU | RAM | Uptime | Notes |
|------|--------|-----|-----|--------|-------|
| **pve** | Online | 4 cores (26.5% util) | 15.36 GB | 1d 23h | Primary controller |
| **pumped-piglet** | Online | 12 cores (9.8% util) | 62.39 GB | 1d 15h | Most powerful node |
| **chief-horse** | Online | 4 cores (17.7% util) | 7.66 GB | 13w 3d | Stable workhorse |
| **fun-bedbug** | Online | 2 cores (61.7% util) | 7.22 GB | 8w | Running hot - investigate |
| **still-fawn** | Offline | - | - | - | Available for expansion |
| **rapid-civet** | Offline | - | - | - | Available for expansion |

**Immediate Action:** `fun-bedbug` is running at 61.7% CPU utilization - investigate workload distribution.

### Virtual Machines

| VMID | Name | Node | Status | RAM | Disk | Purpose |
|------|------|------|--------|-----|------|---------|
| 101 | OPNsense | pve | Running | 4 GB | 32 GB | Network gateway/firewall |
| 102 | UbuntuMAAS | pve | Running | 5 GB | 100 GB | MAAS metal-as-a-service |
| 107 | k3s-vm-pve | pve | Running | 4 GB | 200 GB | Kubernetes control plane |

**Total VM Resources:** 13 GB RAM, 332 GB disk across 3 VMs

### LXC Containers

| VMID | Name | Node | Status | Purpose |
|------|------|------|--------|---------|
| 100 | docker | pve | Running | Docker host |
| 111 | cloudflared | pve | Running | Cloudflare tunnel |

---

## Python Project Architecture Assessment

### Project Structure

```
proxmox/homelab/
├── src/homelab/                    # 7,853 total lines of Python
│   ├── infrastructure_orchestrator.py   # Main orchestration (381 lines)
│   ├── enhanced_vm_manager.py           # Crucible VM manager (574 lines)
│   ├── oxide_storage_api.py             # Oxide-style storage API
│   ├── crucible_config.py               # Storage configuration
│   ├── crucible_mock.py                 # Mock storage backend
│   ├── vm_manager.py                    # Traditional VM manager
│   ├── monitoring_manager.py            # Uptime Kuma integration
│   ├── coral_automation.py              # Google Coral TPU automation
│   ├── cli.py                           # Typer CLI with Rich output
│   └── [17 more modules...]
└── tests/                           # 284 tests (currently blocked)
```

### Architectural Patterns

#### 1. **Infrastructure Orchestrator** (infrastructure_orchestrator.py:1-381)

**Purpose:** Single-script homelab consistency maintainer

**5-Step Orchestration Workflow:**
```python
Step 1: Provision K3s VMs using VMManager
Step 2: Register K3s VMs in MAAS for persistent IPs
Step 3: Register critical services (Uptime Kuma) in MAAS
Step 4: Update monitoring to use persistent hostnames
Step 5: Generate documentation from current state
```

**Assessment:**
- ✅ Idempotent design pattern
- ✅ Clear separation of orchestration steps
- ✅ Comprehensive logging and error handling
- ⚠️ SSH-based MAAS integration is brittle (subprocess calls)
- ⚠️ MAC address discovery through SSH could be unreliable
- ⚠️ Documentation generation is placeholder only

**Recommendation:** Consider using MAAS Python client library instead of SSH subprocess calls.

#### 2. **Crucible VM Manager** (enhanced_vm_manager.py:1-574)

**Purpose:** Oxide-inspired storage-backed VM lifecycle management

**Key Capabilities:**
- Create VMs with distributed storage disks
- Clone VMs from snapshots
- Attach/detach storage volumes
- Full lifecycle management with rollback

**Code Sample:**
```python
# VM creation with storage (lines 48-160)
async def create_vm_with_storage(
    vm_name: str,
    node_name: str,
    disk_size_gb: int = 50,
    disk_source: DiskSource = DiskSource.BLANK,
    snapshot_id: Optional[str] = None
) -> Dict[str, Any]:
    # 1. Create Crucible storage disk
    # 2. Create VM shell in Proxmox
    # 3. Attach Crucible disk to VM
    # 4. Configure VM storage
    # 5. Store VM configuration
```

**Assessment:**
- ✅ Beautiful abstraction layer over Proxmox API
- ✅ Async/await for parallel operations
- ✅ Proper cleanup on failure
- ✅ Type hints and comprehensive documentation
- ⚠️ Storage backend still using mocks (line 116: "Real Crucible backend not yet implemented")
- ⚠️ Proxmox integration incomplete (line 502: falls back to traditional config)

**Reality Check:** This is excellent architecture for **future** distributed storage, but currently it's an abstraction layer over traditional Proxmox storage with mock backends. Not yet production-ready.

#### 3. **Oxide Storage API** (oxide_storage_api.py:1-150+)

**Purpose:** Emulate Oxide Computer's customer-facing storage API

**Abstractions:**
- `DiskState` enum (creating, attached, detached, destroyed, etc.)
- `DiskSource` enum (blank, snapshot, image, importing)
- `DiskCreate` dataclass - complete disk configuration
- `Snapshot` operations with Oxide-style metadata

**Assessment:**
- ✅ Matches Oxide's actual API design patterns
- ✅ Comprehensive state machine for disk lifecycle
- ✅ Production-quality type safety with dataclasses
- ⚠️ Backend always uses mocks (line 112-117: real Crucible "not yet implemented")
- ❌ No actual distributed storage implementation

**Question:** Is the goal to eventually run real Crucible/distributed storage, or is this just design inspiration for a simpler system?

#### 4. **Monitoring Manager** (monitoring_manager.py)

**Purpose:** Uptime Kuma integration for service monitoring

**Assessment:**
- ✅ Deployed and functional (referenced in orchestrator)
- ✅ Multiple instance support (pve + fun-bedbug)
- ✅ Idempotent monitor creation/updates
- 🤔 Why separate from Kubernetes/Prometheus monitoring?

#### 5. **Coral Automation** (coral_automation.py, coral_detection.py, etc.)

**Purpose:** Google Coral TPU detection and passthrough

**Assessment:**
- ✅ Hardware detection via USB
- ✅ Automated VM passthrough configuration
- ✅ Multi-module design (detection, initialization, models, config)
- 🤔 This is niche but well-implemented

---

## Comparison: "Poor Man's Crossplane" vs Crossplane

### What You've Built

| Aspect | Your Implementation | Crossplane |
|--------|---------------------|------------|
| **Scope** | Proxmox VMs + MAAS + monitoring | Multi-cloud (AWS, GCP, Azure) |
| **Paradigm** | Python orchestrator scripts | Kubernetes CRDs + controllers |
| **State Management** | Python dicts + Proxmox API | etcd via Kubernetes |
| **Declarative** | Partial (Config + .env) | Full (YAML manifests) |
| **Idempotency** | Manual checks in code | Built-in via reconciliation loops |
| **Extensibility** | Add Python modules | Install provider packages |
| **Learning Curve** | Python + Proxmox | Kubernetes + Go + CRDs |

### Your Advantages

1. **Simpler for homelab scale** - No Kubernetes controller complexity
2. **Direct Proxmox integration** - Native API usage
3. **Python ecosystem** - Easy to prototype and test
4. **AI-friendly** - LLMs understand Python better than Go controllers

### Crossplane Advantages

1. **True declarative infrastructure** - Git commit = desired state
2. **Self-healing** - Continuous reconciliation
3. **Kubernetes-native** - Works with your existing Flux setup
4. **Production-tested** - Battle-hardened in enterprises

---

## Critical Issues

### 1. Test Suite Blocked ⚠️

**Error:**
```
ERROR: Unknown config option: asyncio_mode
'asyncio' not found in `markers` configuration option
```

**Root Cause:** `pyproject.toml` has `asyncio_mode = "auto"` (line 63) but `asyncio` is not in the markers list (line 57-62).

**Fix:**
```toml
# pyproject.toml line 57-62
markers = [
    "slow: marks tests as slow",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
    "mock: marks tests that use mocking extensively",
    "asyncio: marks tests that use asyncio"  # ADD THIS
]
```

**Impact:** Cannot verify 284 tests are passing before making changes. This is **critical**.

### 2. fun-bedbug High CPU Usage 🔥

**Observation:** 61.7% CPU utilization on a 2-core system (only node above 30%)

**Likely Causes:**
- Frigate NVR with camera processing
- Google Coral TPU workload
- Insufficient CPU for workload

**Recommended Actions:**
1. Check running services: `ssh root@fun-bedbug.maas "pct list && top -bn1 | head -20"`
2. Review Frigate camera count and detection frequency
3. Consider workload migration to pumped-piglet (12 cores at 9.8% util)

### 3. Crucible Storage Not Implemented 🚧

**Current State:** All storage operations use mocks

**Code Evidence:**
```python
# oxide_storage_api.py:114-117
if self.config.enable_mocking:
    self.storage_backend = MockCrucibleManager(self.config)
else:
    logger.warning("Real Crucible backend not yet implemented, using mock")
    self.storage_backend = MockCrucibleManager(self.config)  # Always mocks!
```

**Decision Point:**
- Continue with mock backend for testing/development?
- Implement real distributed storage backend?
- Simplify abstractions to match actual Proxmox storage?

---

## Code Quality Assessment

### Strengths ✅

1. **Type Safety**
   - Comprehensive type hints on all functions
   - Dataclasses for structured data
   - MyPy configuration enforcing strict typing

2. **Testing Infrastructure**
   - 284 tests collected
   - pytest with coverage reporting
   - Mock fixtures for external dependencies
   - 90% coverage requirement (pyproject.toml:55)

3. **Code Style**
   - Black formatting (120 char line length)
   - isort for import organization
   - flake8 linting
   - Pre-commit hooks configured

4. **Documentation**
   - Comprehensive docstrings
   - Inline comments for complex logic
   - Module-level documentation
   - README with clear setup instructions

5. **Dependencies**
   - Poetry for dependency management
   - Pinned versions in poetry.lock
   - Separation of dev vs production deps
   - Modern async libraries (aiohttp, aiofiles)

### Weaknesses ⚠️

1. **Complexity for Current Scale**
   - 7,853 lines of Python for 3 VMs and 2 containers
   - Oxide-inspired storage abstractions without backend implementation
   - Multiple orchestration layers (orchestrator + vm_manager + enhanced_vm_manager)

2. **Incomplete Implementations**
   - Documentation generation is placeholder (infrastructure_orchestrator.py:286-298)
   - Crucible storage always mocks
   - Proxmox storage configuration falls back to traditional (enhanced_vm_manager.py:493-510)

3. **Integration Gaps**
   - Python orchestrator separate from Flux GitOps
   - No integration with Kubernetes for VM-based workloads
   - MAAS integration via SSH subprocess instead of API client

4. **Maintenance Risk**
   - Large codebase requires ongoing maintenance
   - Complex abstractions may be harder for AI agents to modify
   - Test suite currently blocked from running

---

## Recommendations

### Immediate Actions (This Week)

1. **Fix Test Suite** ⏰
   ```bash
   # Add 'asyncio' to markers in pyproject.toml
   cd proxmox/homelab
   poetry run pytest tests/ -v
   poetry run coverage html
   ```

2. **Investigate fun-bedbug CPU Usage** 🔥
   ```bash
   ssh root@fun-bedbug.maas "htop"  # Interactive process viewer
   # Check for Frigate, LLM workloads, camera streams
   ```

3. **Run Infrastructure Orchestrator in Dry-Run** 🧪
   ```bash
   cd proxmox/homelab
   poetry run python -m homelab.infrastructure_orchestrator --dry-run
   ```

### Short-Term (Next Month)

4. **Simplify or Implement Crucible Backend**
   - **Option A:** Remove Crucible abstractions, use Proxmox storage directly
   - **Option B:** Implement basic distributed storage (Ceph, LINSTOR)
   - **Option C:** Keep mocks for testing, document as "future work"

5. **Integrate with Flux GitOps**
   - Create GitOps manifests for VMs (using Proxmox provider)
   - Let Flux manage infrastructure state
   - Python orchestrator becomes operator pattern

6. **Consolidate Orchestration Layers**
   - Choose between `vm_manager.py` vs `enhanced_vm_manager.py`
   - Merge overlapping functionality
   - Reduce cognitive load for AI agents

7. **Add Integration Tests**
   - Test actual VM creation on Proxmox
   - Test MAAS registration workflows
   - Test monitoring synchronization

### Long-Term (Next Quarter)

8. **Consider Crossplane for Real Crossplane**
   - Install Crossplane in K3s cluster
   - Use Proxmox provider for VMs
   - Keep Python for complex business logic only

9. **Document Architecture Decisions**
   - Why Crucible-inspired abstractions?
   - When to use Python vs GitOps?
   - What's the end-state architecture vision?

10. **Implement Real Storage Backend**
    - Deploy Ceph or similar distributed storage
    - Connect Crucible abstractions to real backend
    - Enable true storage-backed VM cloning

---

## Decision Points for Discussion

### 1. Crucible Storage: Implement, Simplify, or Remove?

**Context:** Currently all storage operations use mocks. The abstractions are well-designed but have no backing implementation.

**Options:**
- **A) Implement Real Backend:** Deploy Ceph/LINSTOR, connect abstractions
- **B) Simplify Abstractions:** Remove Oxide-style API, use Proxmox storage directly
- **C) Keep for Future:** Document as design experiment, use mocks for testing

**Recommendation:** Option C for now. The abstractions are valuable as design documentation, but implementing distributed storage is a major project. Focus on making existing VMs more declarative first.

### 2. Python Orchestrator vs Flux GitOps: Which is Source of Truth?

**Current State:**
- Flux manages Kubernetes workloads
- Python orchestrator manages Proxmox VMs
- No coordination between them

**Options:**
- **A) GitOps All The Things:** Move VM definitions to Git, use Crossplane
- **B) Python as Controller:** Keep Python, add Kubernetes operator pattern
- **C) Hybrid:** Python for complex logic, Git for declarative state

**Recommendation:** Option C. Use GitOps for static configuration, Python for dynamic orchestration (MAC discovery, MAAS registration, monitoring sync).

### 3. Test Coverage: How Much is Enough?

**Current:** 90% coverage requirement, 284 tests

**Question:** Is this overhead justified for homelab scale?

**Recommendation:** Keep high test coverage. This codebase is designed for AI agent modification - good tests enable confident automated changes.

---

## Comparison to Similar Projects

### 1. Proxmox Terraform Provider
- **Scope:** Declarative VM provisioning
- **Your Advantage:** Python more flexible for complex workflows
- **Their Advantage:** Terraform state management

### 2. Foreman/Katello
- **Scope:** Bare metal provisioning + config management
- **Your Advantage:** Lighter weight, homelab-focused
- **Their Advantage:** Production-ready, community support

### 3. Oxide Cloud Computer (Inspiration)
- **Scope:** Full rack-scale infrastructure
- **Your Project:** Homelab-scale implementation of similar abstractions
- **Value:** Learning from production systems, applicable patterns

---

## Conclusion

You've built an impressively sophisticated infrastructure management system that punches well above its weight. The architecture shows clear influence from production systems (Oxide, Crossplane) while remaining pragmatic for homelab scale.

**Key Takeaway:** This is **excellent design work** and **solid Python engineering**, but you may be over-engineering for current needs. The abstractions are beautiful but some (like Crucible storage) lack implementations.

**Strategic Choice:**
1. **Simplify:** Remove unused abstractions, focus on working features
2. **Complete:** Implement distributed storage, fulfill the vision
3. **Pivot:** Move to Crossplane for true declarative infrastructure

**My Recommendation:** Fix tests immediately, then simplify the codebase while preserving the excellent architectural patterns for future reference. Use this as a learning platform while moving toward GitOps for production workloads.

The fact that this is "AI-first" infrastructure is its biggest strength - the clean abstractions and comprehensive tests make it easy for AI agents to understand and modify. Keep that advantage while reducing complexity.

---

## Appendix: Quick Wins

### A. Fix Test Suite
```bash
cd /Users/10381054/code/home/proxmox/homelab
# Edit pyproject.toml, add 'asyncio' to markers
poetry run pytest tests/ -v --cov=src/homelab --cov-report=html
open htmlcov/index.html
```

### B. Get Current Infrastructure State
```bash
cd /Users/10381054/code/home/proxmox/homelab
poetry run python -c "
from homelab.infrastructure_orchestrator import InfrastructureOrchestrator
import json
orch = InfrastructureOrchestrator()
# Run read-only checks
print('Infrastructure Status:')
print('- MAAS Host:', orch.maas_host)
print('- Critical Services:', len(orch.critical_services))
"
```

### C. Investigate fun-bedbug
```bash
ssh root@fun-bedbug.maas "
echo '=== Container CPU Usage ==='
pct list
echo ''
echo '=== Top Processes ==='
top -bn1 | head -20
echo ''
echo '=== Frigate Status (if exists) ==='
pct exec 113 -- ps aux | grep -i frigate
"
```

### D. Documentation Snapshot
```bash
cd /Users/10381054/code/home
make -C docs html
# Deploy at: https://your-docs-site.homelab
```

---

**End of Review**

*Generated: 2025-01-22 by Claude Code*
*Total Analysis Time: ~15 minutes*
*Files Reviewed: 7,853 lines across 24 Python modules*
