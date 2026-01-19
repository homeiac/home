# Claude Code + USE Method Integration

How Claude Code should invoke the USE Method performance diagnosis framework.

## When to Invoke

Claude should use the USE Method when user reports:
- slow, latency, performance degraded
- timeout, lag, unresponsive
- service degradation
- "something is wrong with X"

## Invocation Pattern

### Step 0: Memory Check (ALWAYS FIRST)

Before ANY diagnostic commands, check OpenMemory for existing fixes:

```
openmemory_query("<service> <symptom> solved fix resolution", k=5)
```

**If relevant result found:**
- Report the existing fix to user
- Ask if they want to verify it's still in place
- Do NOT start new investigation

**If no results:**
- Proceed to Step 1

### Step 1: Run USE Method Orchestrator

```bash
scripts/perf/diagnose.sh --target <context> [--url <service-url>]
```

**Target Contexts:**

| Context | Example | When to Use |
|---------|---------|-------------|
| `proxmox-vm:VMID` | `proxmox-vm:116` | HAOS (VM 116), K3s VMs |
| `k8s-pod:ns/pod` | `k8s-pod:frigate/frigate-coral-xxx` | Kubernetes pods |
| `ssh:user@host` | `ssh:root@still-fawn.maas` | Direct host access |
| `local` | `local` | Local machine |

**VMID Reference:**
- 116 = HAOS on chief-horse
- 108 = K3s VM on still-fawn
- 105 = K3s VM on pumped-piglet

### Step 2: Interpret Results

The script checks resources in E→U→S order:
- **E**rrors first (quickest signal)
- **U**tilization (>70% warrants investigation)
- **S**aturation (queuing, any non-zero is concerning)

**For each resource (CPU, Memory, Disk, Network, GPU):**

| Symbol | Meaning | Action |
|--------|---------|--------|
| ✓ | OK | No action needed |
| ⚠ | Warning | Investigate further |
| ✗ | Error | Critical - investigate immediately |

**Decision Tree:**
```
Issues Found?
├── Yes → Run deep-dive script for that resource
│         - memory-deep-dive.sh
│         - cpu-deep-dive.sh (planned)
│         - disk-deep-dive.sh (planned)
│
└── No → Check application logs
         scripts/perf/app-logs.sh --target <context>
         │
         └── External latency suspected?
             └── Yes → scripts/perf/network-timing.sh <url>
```

### Step 3: Layered Analysis

For VMs and containers, the script checks BOTH layers:

```
┌─────────────────────────┐
│ WORKLOAD LAYER          │  ← Check resource limits, cgroup throttling
│ (VM or Container)       │
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│ HOST LAYER              │  ← Check physical resources
│ (Proxmox or K8s Node)   │
└─────────────────────────┘
```

**Interpretation:**
- Workload saturated, Host OK → Check limits/quotas
- Both saturated → Actual resource shortage
- Both OK → Check application-level

### Step 4: Store Resolution

When issue is solved, store in OpenMemory for future reference:

```
openmemory_lgm_store(
  node="act",
  content="<service> <symptom> - SOLVED. Fix: <resolution>",
  tags=["<service>", "performance", "solved"],
  namespace="home"
)
```

**Example:**
```
openmemory_lgm_store(
  node="act",
  content="Voice PE TTS latency - SOLVED. Fix: Disable WiFi power save in ESPHome config.",
  tags=["voice-pe", "latency", "esp32", "solved"],
  namespace="home"
)
```

## Anti-Patterns to Avoid

| Bad Pattern | Why It's Wrong | Correct Approach |
|-------------|----------------|------------------|
| "Let me check the network" | Assumes bottleneck without evidence | Run USE Method to find actual bottleneck |
| Checking logs first | Skips resource-level diagnosis | Check resources first, then logs |
| Stopping at first finding | May miss related issues | Check ALL resources before concluding |
| Not checking OpenMemory | May re-investigate solved issue | Always check memory first |
| "That's a limitation" | May be wrong | Query OpenMemory before claiming impossible |

## Script Portfolio

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `diagnose.sh` | Main orchestrator | First script to run |
| `use-checklist.sh` | Full USE sweep | Detailed analysis |
| `quick-triage.sh` | 60-second subset | Quick check |
| `memory-deep-dive.sh` | Memory analysis | When memory issues found |
| `network-timing.sh` | HTTP timing | When external latency suspected |
| `app-logs.sh` | Application logs | When USE shows no resource issues |

## Example Scenarios

### Scenario 1: Voice PE Slow (Already Solved)

```
User: "Voice PE TTS is slow"

Claude:
1. Query: openmemory_query("voice pe slow latency solved", k=5)
2. Found: "Voice PE WiFi latency - ALREADY SOLVED. Fix: Disable WiFi power save"
3. Report: "This was previously solved by disabling WiFi power save in ESPHome."
```

### Scenario 2: Frigate Slow (New Issue)

```
User: "Frigate detections are delayed"

Claude:
1. Query: openmemory_query("frigate slow detection solved", k=5) → No results
2. Run: scripts/perf/diagnose.sh --target k8s-pod:frigate/frigate-xxx
3. Results show CPU at 95%
4. Report: "High CPU utilization (95%) on Frigate pod"
5. Deep dive: Show top CPU consumers
6. After fix: Store resolution in OpenMemory
```

### Scenario 3: HAOS Unresponsive

```
User: "Home Assistant is unresponsive"

Claude:
1. Query: openmemory_query("home assistant unresponsive solved", k=5) → No results
2. Run: scripts/perf/diagnose.sh --target proxmox-vm:116
3. Results show memory at 92%
4. Also check host layer (chief-horse) → Host is fine
5. Report: "HAOS VM memory at 92%, host resources OK"
6. Deep dive: scripts/perf/memory-deep-dive.sh --target proxmox-vm:116
```

## References

- [USE Method](https://www.brendangregg.com/usemethod.html) - Brendan Gregg
- [Linux Performance Analysis in 60s](https://netflixtechblog.com/linux-performance-analysis-in-60-000-milliseconds-accc10403c55)
- Architecture: `docs/architecture/use-method-design.md`
- Runbook: `docs/methodology/performance-diagnosis-runbook.md`
