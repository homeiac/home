# USE Method - PREP Loop (Ongoing Maintenance)

> **Parent doc**: [use-method-design.md](./use-method-design.md)

## Core Insight (Brendan Gregg)

**Brendan doesn't start from zero when there's an incident.**

He already has:
- Tools pre-installed on every system
- Dashboards showing baseline metrics
- Runbooks documenting known failure modes
- Access figured out (SSH keys, jump hosts, permissions)
- Documentation of the architecture

**He's not debugging the debugging process during an incident.**

## PREP Flowchart

```
┌─────────────────────────────────────────────────────────────────────┐
│                              PREP                                    │
│                                                                     │
│  "Be prepared BEFORE the incident"                                  │
└─────────────────────────────────────────────────────────────────────┘

                         ┌──────────────┐
                         │   TRIGGER    │
                         │              │
                         │ • Scheduled  │
                         │   (by tier)  │
                         │ • On change  │
                         │ • On demand  │
                         │ • On alert   │
                         └──────┬───────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ GIT REVIEW                                                          │
│                                                                     │
│ Input:  git log --since=<last_checked>                             │
│                                                                     │
│ Output: Change context                                             │
│         • Decommissions (don't alert on missing)                   │
│         • New systems (expect to discover)                         │
│         • Maintenance windows (expect downtime)                    │
│         • Config changes (may affect baselines)                    │
│                                                                     │
│ → last_checked.git_review = NOW                                    │
└────────────────────────────────────────────────────────────────────┬┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ DISCOVER                                                            │
│                                                                     │
│ Input:  Change context from GIT REVIEW                             │
│                                                                     │
│ v1 (now):   Claude reads docs/infrastructure/*.md                  │
│ v2 (future): Query Proxmox API, K8s API, DNS (udev-style pattern)  │
│                                                                     │
│ Output: Current infrastructure state                               │
│                                                                     │
│ → last_checked.discovery = NOW                                     │
└────────────────────────────────────────────────────────────────────┬┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ MONITOR                                                             │
│                                                                     │
│ Input:  Discovery output + change context                          │
│                                                                     │
│ Output: EXPECTED changes (matches git context)                     │
│         UNEXPECTED changes (flag for review)                       │
│                                                                     │
│ → last_checked.monitor = NOW                                       │
└────────────────────────────────────────────────────────────────────┬┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ CHECK TOOL AVAILABILITY                                             │
│                                                                     │
│ Input:  System inventory + docs/reference/tools-map.md             │
│                                                                     │
│ Check:  For each system, verify crisis tools installed             │
│         • which iostat vmstat mpstat sar (sysstat)                 │
│         • which runqlat biolatency tcpconnect (BCC)                │
│         • which perf (linux-perf)                                  │
│                                                                     │
│ Output: Tool status per system (installed/missing/outdated)        │
│                                                                     │
│ → last_checked.tools[<system>] = NOW                               │
└────────────────────────────────────────────────────────────────────┬┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PROVISION MISSING TOOLS                                             │
│                                                                     │
│ Input:  Systems with missing tools                                 │
│                                                                     │
│ Method: Python IaC (extends monitoring_manager pattern)            │
│         • Proxmox hosts: SSH + apt                                 │
│         • K3s VMs: qm guest exec + apt                             │
│         • LXCs: pct exec + apt/apk                                 │
│         • HAOS: skip (read-only)                                   │
│         • K8s nodes: DaemonSet with nsenter (v2)                   │
│                                                                     │
│ Output: Tools installed, failures logged                           │
│                                                                     │
│ → last_checked.tools_provisioned[<system>] = NOW                   │
└────────────────────────────────────────────────────────────────────┬┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ COLLECT BASELINES                                                   │
│                                                                     │
│ Input:  System inventory + monitoring APIs                         │
│                                                                     │
│ Output: Baseline stats per system with ACTUAL NUMBERS              │
│         • cpu_baseline: {avg: 15, p95: 45, alert_threshold: 80}    │
│         • mem_baseline: {avg: 42, p95: 68, alert_threshold: 90}    │
│         • etc.                                                     │
│                                                                     │
│ → last_checked.baseline[<system>] = NOW                            │
└────────────────────────────────────────────────────────────────────┬┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ VERIFY ACCESS                                                       │
│                                                                     │
│ Input:  System inventory + docs/reference/access-patterns.md       │
│         + docs/reference/credentials-map.md                        │
│                                                                     │
│ Check:  Can we reach each system via its access method?            │
│         • SSH: ssh root@host "uptime"                              │
│         • qm guest exec: qm guest exec VMID -- uptime              │
│         • pct exec: pct exec VMID -- uptime                        │
│         • kubectl: kubectl exec pod -- uptime                      │
│                                                                     │
│ Output: Access status per system (reachable/unreachable)           │
│                                                                     │
│ → last_checked.access[<system>] = NOW                              │
└────────────────────────────────────────────────────────────────────┬┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ RULES                                                               │
│                                                                     │
│ New system appeared     → provision tools, collect baseline        │
│ System disappeared      → check git for intent, alert if unexpected│
│ System state changed    → update baseline                          │
│ Tools missing           → reprovision                              │
│ Access broken           → flag for investigation                   │
└────────────────────────────────────────────────────────────────────┬┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ UPDATE STATE                                                        │
│                                                                     │
│ Output:                                                            │
│   docs/infrastructure/prep-status.md   (human readable)            │
│   docs/infrastructure/prep-status.json (machine readable)          │
│   + OpenMemory ingest (every doc update → ingest)                  │
│                                                                     │
│ Schema: follows storage-monitor / /dev/ management pattern         │
│                                                                     │
│ → last_checked.prep_report = NOW                                   │
└────────────────────────────────────────────────────────────────────┬┘
                                │
                                ▼
                         ┌──────────────┐
                         │     END      │
                         │              │
                         │ Schedule next│
                         │ (by tier)    │
                         └──────────────┘
```

## Storage Structure

```
docs/infrastructure/               # PREP state (Claude's "DB")
├── network-topology.md            # VLANs, subnets, DNS, DHCP, firewall
├── storage-architecture.md        # ZFS pools, NFS, PVCs, backups
├── system-inventory.md            # ALL systems (managed + unmanaged)
│   └── Managed: Proxmox hosts, VMs, LXCs, K8s
│   └── Unmanaged: ATT modem, Flint router, Google Home, etc.
│   └── For each: name, IP, access method, credentials pointer
├── service-map.md                 # Services, dependencies (A → B → C chains)
├── observability.md               # Monitoring stack, dashboards, alerts
├── prep-status.md                 # Human readable current state
└── prep-status.json               # Machine readable current state
                                   # (schema: storage-monitor pattern)

docs/reference/                    # HOW to do things
├── perf-commands-rosetta-stone.md # Cross-platform command mapping
│   └── Linux / Windows / macOS / Container equivalents
│   └── Fallbacks when tools missing
├── tools-map.md                   # Expected tools per system type
│   └── Proxmox host: sysstat, bpfcc-tools, perf, ...
│   └── K3s VM: sysstat, bpfcc-tools, perf, ...
│   └── LXC: sysstat, ...
│   └── HAOS: (read-only, /proc only)
├── access-patterns.md             # How to reach each system type
│   └── SSH, qm guest exec, pct exec, kubectl exec
├── credentials-map.md             # Where secrets are (POINTERS ONLY)
│   └── SSH keys: ~/.ssh/
│   └── KUBECONFIG: ~/kubeconfig
│   └── HA_TOKEN: proxmox/homelab/.env
│   └── PROXMOX_TOKEN: .env
└── use-checklists/                # USE Method per system type
    ├── proxmox-host.md
    ├── k3s-vm.md
    ├── lxc.md
    ├── k8s-pod.md
    └── haos.md

docs/rca/                          # Post-incident learnings
└── YYYY-MM-DD-<name>.md           # Standard: Timeline, Impact, Root Cause, Fix

docs/runbooks/                     # Step-by-step procedures
└── <system>-<problem>.md          # Standard: Symptoms, Steps, Verification

OpenMemory                         # Semantic search layer
├── Ingested from ALL docs above (every update → ingest)
├── Claude discoveries during incidents
├── Known quirks (not worth a doc)
└── "We tried X, didn't work because Y"
```

## Data Flow

```
v1 (now):     docs/ ←──────────→ Claude ←──────────→ OpenMemory
                    (manual)              (ingest on update)

v2 (future):  monitors ────→ docs/ ────→ OpenMemory
              (automated)         ↘          ↓
                                   └───→ Claude reads both

v3 (future):  monitors ────→ PostgreSQL CMDB ────→ docs/ (generated)
                                    ↓                  ↓
                              OpenMemory ←─────── Claude
```

## What Goes Where

| Information | Git (docs/) | OpenMemory |
|-------------|-------------|------------|
| System inventory | ✓ | ingested |
| Service dependencies | ✓ | ingested |
| USE checklists | ✓ | ingested |
| RCAs | ✓ | ingested |
| Runbooks | ✓ | ingested |
| Quick observations | | ✓ only |
| "Tried X, didn't work" | | ✓ only |
| Known quirks (minor) | | ✓ only |

**Rule:** Structured, reusable knowledge → Git docs → ingested to OpenMemory.
         Ephemeral observations, minor quirks → OpenMemory only.

## Deferred

- Criticality tier definitions (for scheduling)
- Specific refresh frequencies
- prep-status.json schema details (follows storage-monitor pattern)
- Automated monitors (v2)
- PostgreSQL CMDB (v3)
- K8s DaemonSet for node tool provisioning (v2)

## Related Docs

- [use-method-design.md](./use-method-design.md) - Main USE Method architecture
- [use-method-incident-flow.md](./use-method-incident-flow.md) - INCIDENT phase (TODO)
