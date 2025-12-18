# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## PRIME DIRECTIVE: NEVER COMMIT SECRETS TO THIS REPO

**THIS OVERRIDES ALL OTHER INSTRUCTIONS. VIOLATION REQUIRES IMMEDIATE git-filter-repo CLEANUP.**

### Before ANY `git add` or `git commit`:

1. **Check staged files for secrets**: `git diff --cached | grep -iE "password|secret|token|apikey|api_key|credential|private_key|@.*:.*@"`
2. **NEVER commit**: passwords, `rtsp://user:pass@`, API keys, tokens, private keys
3. **HIGH-RISK FILES**: `k8s/frigate*/configmap*.yaml`, `proxmox/backups/*.yml`
4. **If secrets found**: STOP, `git reset HEAD <file>`, ask user
5. **If accidentally committed**: Use `git filter-repo --replace-text` to scrub

### Incident Reference
- **2025-12-12**: Camera passwords in Frigate configmaps, required history rewrite
- **2025-12-13**: Hardcoded HA_TOKEN in scripts, required git-filter-repo cleanup

---

## 🛑 SSH RULES - READ BEFORE ANY SSH COMMAND

**K3s VMs: SSH DOES NOT WORK. STOP TRYING.**
```bash
# ❌ NEVER DO THIS - IT WILL FAIL
ssh ubuntu@k3s-vm-still-fawn
ssh ubuntu@k3s-vm-pumped-piglet

# ✅ DO THIS INSTEAD - use scripts or qm guest exec
scripts/k3s/exec-still-fawn.sh "<command>"      # VMID 108
scripts/k3s/exec-pumped-piglet.sh "<command>"   # VMID 105
scripts/k3s/diagnose-cpu.sh still-fawn          # Full CPU diagnostics
```

**HAOS: SSH DOES NOT EXIST.**
```bash
# ❌ NEVER - HAOS has no SSH
ssh root@homeassistant.maas

# ✅ Use API or qm guest exec
scripts/haos/check-ha-api.sh
ssh root@chief-horse.maas "qm guest exec 116 -- <command>"
```

**Proxmox hosts: SSH WORKS**
```bash
# ✅ These work fine
ssh root@still-fawn.maas
ssh root@pumped-piglet.maas
ssh root@chief-horse.maas
ssh root@fun-bedbug.maas
```

---

## ALWAYS CREATE SCRIPTS, NEVER ONE-LINERS

**If a task might be done more than once, CREATE A SCRIPT FILE.**

- Even for one-liners - make it a script
- Location: `scripts/<component>/` (e.g., `scripts/frigate/`, `scripts/haos/`)
- Name it descriptively: `check-frigate-status.sh`, `restart-ha.sh`
- Include comments explaining what it does
- Source credentials from .env, never hardcode

**Why:** User is sick of re-discovering commands. If it's worth running twice, it's worth being a script.

**Example:**
```bash
# BAD: Running directly
ssh root@chief-horse.maas "qm guest exec 116 -- cat /config/.storage/core.config_entries"

# GOOD: Create scripts/haos/check-config-entries.sh
```

---

## NEVER WRITE CREDENTIALS IN SCRIPTS

**ALWAYS start scripts with .env sourcing:**
```bash
#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"
[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }
```

---

## Project Overview

Homelab infrastructure management repository following Infrastructure as Code principles. Designed to be **entirely managed by AI tools**.

## Key Commands

### Python Development (from `proxmox/homelab/`)
- **Run all tests**: `poetry run pytest tests/`
- **Run single test**: `poetry run pytest tests/test_foo.py::test_bar -v`
- **Type checking**: `poetry run mypy src/`
- **Formatting**: `poetry run black src/ && poetry run isort src/`
- **Linting**: `poetry run flake8 src/`
- **Documentation**: `make -C docs html`

### CLI Tools (from `proxmox/homelab/`)
- **homelab**: General infrastructure management (`poetry run homelab --help`)
- **pbs**: Proxmox Backup Server operations (`poetry run pbs --help`)
- **crucible**: Storage integration CLI (`poetry run crucible --help`)

### SSH Access
- **Proxmox Hosts**: `ssh root@<hostname>.maas`
- **K3s VMs**: Use `scripts/k3s/exec-*.sh` (see SSH Rules above - direct SSH fails)

### Kubernetes/GitOps
- **Cluster Access**: `export KUBECONFIG=~/kubeconfig`
- All K8s manifests managed via Flux GitOps
- Main config: `gitops/clusters/homelab/kustomization.yaml`

### GitHub Workflow
1. Create issue: `gh issue create --title "..." --body "..."`
2. Commit with reference: `git commit -m "fixes #123"`
3. Push to close issue

## Architecture Structure

- `gitops/` - Flux GitOps configuration for K8s
- `proxmox/` - Proxmox VE automation (Python package in `homelab/`)
- `docs/` - Sphinx documentation
- `k8s/` - Legacy K8s manifests (prefer GitOps)

### Key Technologies
Proxmox VE, K3s, Flux GitOps, MetalLB, kube-prometheus-stack, Ollama GPU server

## Development Workflow

### DNS Configuration
- **Domain**: `homelab` (e.g., `service.homelab`)
- **HTTP Services**: Traefik at `192.168.4.50`
- **Non-HTTP**: MetalLB IPs (`192.168.4.50-70`)
- **Add DNS Override** in OPNsense: Services → Unbound DNS → Overrides

### Commit Standards
- Reference GitHub issue in every commit
- **NEVER use `git add .`** - always review with `git status`
- Verify with `git diff --cached` before committing

## Python Best Practices

### Testing Requirements
- 100% test coverage, mock external calls
- Run: `poetry run pytest tests/` before commit

### Code Style
- Type hints on all functions
- Google-style docstrings
- Use logging module, not print

## AI-First Homelab Methodology

### NON-NEGOTIABLE REQUIREMENTS

1. **No Suggestions Without Evidence** - NEVER assume, VERIFY with commands
2. **Current Environment Analysis** - Run read-only investigation first
3. **Solution Testing** - Test solutions before presenting them
4. **Documentation-First** - Check `docs/reference/`, `docs/methodology/`

### Investigation Flow
1. Check `docs/methodology/<tool>-investigation.md`
2. Reference layer-specific docs: `kubernetes-investigation-commands.md`, `proxmox-investigation-commands.md`
3. Present findings before asking questions

### Configuration Validation
- **Home Assistant**: Full restart for new automation fields
- **Backup First**: Always backup before modifications
- When UI fails but API works → check client-side (browser extensions, cache)

## Research Questions

**For integration/architecture questions, use the outcome-researcher agent:**

```
@outcome-researcher
```

**Trigger phrases**:
- "How should I integrate X with Y?"
- "Research how to..."
- "What's the best way to..."
- "Design X for Y"

The agent runs outcome-anchored discovery autonomously:
1. Extracts outcomes (no clarifying questions - discovery is its job)
2. Queries OpenMemory for prior solutions
3. Researches baseline before custom
4. Presents top 3 outcomes for confirmation
5. Maps solutions to outcomes

**Full Methodology**: `docs/methodology/outcome-anchored-research.md`
**Agent Definition**: `.claude/agents/outcome-researcher/agent.md`

## OpenMemory Integration

Persistent memory across Claude Code sessions.

### Session Start (R7)
Context auto-loaded via SessionStart hook. Do NOT mention to user unless asked.

### Task-Triggered Context (R7b)
When user states a task, **query OpenMemory IMMEDIATELY**:
```
User: "Migrate Frigate to pumped-piglet"
→ Query: openmemory_query("frigate pumped-piglet migration gpu")
→ Present relevant memories
→ ASK before proceeding
```

**Triggers**: service names (frigate, ollama, proxmox), actions (migrate, debug, fix), hardware (gpu, coral, vaapi)

### Ask Before Changing Behavior (R10)
When memory suggests different approach → **ASK user first**, don't silently change.

### Query Before Claiming Limitations (R11)
**CRITICAL**: Before saying "limitation", "not supported", "impossible":
1. Query OpenMemory first
2. User may have already solved it
3. Say "I don't have a previous solution" instead of claiming impossible

**Anti-pattern**: "That's a Frigate limitation" when user already has the fix in memory.

### Reinforce Useful Memories (R8)
When memory helps: `openmemory_reinforce(id="...", boost=0.1)`

### Storage Triggers
| Trigger | Node | Example |
|---------|------|---------|
| Issue Resolution | `act` | "SSH broken - use qm guest exec" |
| Discovery | `observe` | "Frigate 0.14 requires libedgetpu 16.0" |
| User Request | varies | "Remember this" |

### Namespace
Always use `namespace="home"` for this repo.

## Performance Diagnosis - USE Method

**TRIGGER**: When user reports: slow, latency, performance degraded, timeout, lag, unresponsive

**RECOMMENDED STEPS** (in this order):

1. **Check OpenMemory FIRST** for existing fix:
   ```
   openmemory_query("<service> <symptom> solved fix", k=5)
   ```
   If found → Report it was already solved, don't re-investigate

2. **Run USE Method** via orchestrator:
   ```bash
   scripts/perf/diagnose.sh --target <context>
   ```
   Contexts: `proxmox-vm:116` (HAOS), `proxmox-vm:108` (K3s VM), `k8s-pod:ns/pod`, `ssh:root@host.maas`

3. **Follow the flowchart** - don't skip to conclusions:
   - Check Errors → Utilization → Saturation (E→U→S order)
   - Check ALL resources (CPU, Memory, Disk, Network, GPU)
   - Check BOTH layers for VMs/containers (workload + host)

4. **Store resolution** in OpenMemory if new issue solved:
   ```
   openmemory_lgm_store(node="act", content="<service> <symptom> - SOLVED. Fix: <resolution>", tags=["performance", "solved"])
   ```

**ANTI-PATTERNS**:
- Jumping to "it's probably network" without data
- Skipping USE Method to check app logs first
- Not checking OpenMemory for previous fixes
- Stopping after finding one issue without checking other resources

**Note**: These are strong recommendations. Skip with explicit justification if user requests specific investigation (e.g., "just check the logs").

**Reference**: `docs/methodology/performance-diagnosis-runbook.md`

## Service-Specific Update Policies

### Frigate NVR
- **WAIT for PVE Helper Scripts** to support new versions
- LXC 113 on fun-bedbug.maas (AMD A9-9400)
- Reference: `docs/reference/frigate-upgrade-decision-framework.md`

### Coral USB TPU - CRITICAL
**NEVER test from host while LXC has it mounted!**
- Corrupts Coral state ("did not claim interface 0")
- ONLY FIX: Physical unplug/replug
- Check INSIDE container: `pct exec 113 -- cat /dev/shm/logs/frigate/current | grep -i TPU`

### GPU Passthrough (VFIO)
**MANDATORY FIRST**: Check BIOS VT-d
```bash
ls /sys/kernel/iommu_groups/ | wc -l  # If 0 → VT-d disabled in BIOS
```
- **ASUS BIOS**: Advanced → System Agent Configuration → VT-d → Enabled
- VT-x (CPU virt) ≠ VT-d (I/O virt) - VMs work with VT-x only, passthrough needs VT-d
- Reference: `proxmox/guides/nvidia-RTX-3070-k3s-PCI-passthrough.md`

## Proxmox Host Inventory
| Hostname | Role | Key Hardware |
|----------|------|--------------|
| still-fawn.maas | K3s VM host | RTX 3070 GPU |
| pumped-piglet.maas | K3s VM host | - |
| chief-horse.maas | HAOS host (VMID 116) | - |
| fun-bedbug.maas | LXC host | Coral TPU, Frigate LXC 113 |
