# USE Method Performance Diagnosis - Architecture & Design

## Flowchart (Brendan Gregg's USE Method)

```mermaid
flowchart TD
    START([Start]) --> IDENTIFY[Identify Resources]
    IDENTIFY --> CHOOSE[Choose a Resource]

    CHOOSE --> ERRORS{Errors Present?}
    ERRORS -->|Y| INVESTIGATE[Investigate Discovery]
    ERRORS -->|N| UTIL{High Utilization?}

    UTIL -->|Y| INVESTIGATE
    UTIL -->|N| SAT{Saturation?}

    SAT -->|Y| INVESTIGATE
    SAT -->|N| ALL_CHECKED{All Resources<br/>Fully Checked?}

    INVESTIGATE --> IDENTIFIED{Identified<br/>the Problem?}
    IDENTIFIED -->|N| ALL_CHECKED
    IDENTIFIED -->|Y| END_NODE([End])

    ALL_CHECKED -->|N| CHOOSE
    ALL_CHECKED -->|Y| END_NODE
```

## Key Principles

### 1. Check Order: E → U → S

**Always check in this order for each resource:**

1. **Errors FIRST** - Quickest signal, often points directly to root cause
2. **Utilization** - Is the resource busy? (>70% warrants investigation)
3. **Saturation** - Is work queueing? (any non-zero value is concerning)

### 2. Iterate Through ALL Resources

Do NOT stop at the first anomaly. Complete the checklist for ALL resources:
- CPU
- Memory
- Disk I/O
- Network
- GPU (if present)
- Software resources (file descriptors, mutexes, etc.)

### 3. Layered Analysis

For virtualized/containerized environments, check BOTH layers:

```mermaid
flowchart TB
    subgraph WORKLOAD["Workload Layer"]
        W_CPU[CPU cgroup limits]
        W_MEM[Memory cgroup limits]
        W_METRICS[Container metrics]
    end

    subgraph HOST["Host Layer"]
        H_CPU[Physical CPU]
        H_MEM[Physical Memory]
        H_DISK[Storage devices]
        H_NET[Network interfaces]
    end

    WORKLOAD --> COMPARE{Compare}
    HOST --> COMPARE

    COMPARE -->|Workload saturated,<br/>Host idle| LIMITS[Check limits/quotas]
    COMPARE -->|Both saturated| SHORTAGE[Actual resource shortage]
    COMPARE -->|Both idle| OTHER[Check application-level]
```

## Resource Checklist

### Physical Resources

| Resource | Utilization | Saturation | Errors |
|----------|-------------|------------|--------|
| **CPU** | % busy time | run queue length | MCE, hardware errors |
| **Memory** | % used, available | swap in/out, page scanning | OOM kills, alloc failures |
| **Disk I/O** | % util (iostat) | queue depth, await time | I/O errors, SMART |
| **Network** | throughput vs capacity | drops, retransmits | interface errors |
| **GPU** | compute %, VRAM % | SM occupancy | XID errors, ECC |

### Software Resources

| Resource | Utilization | Saturation | Errors |
|----------|-------------|------------|--------|
| **File Descriptors** | current vs ulimit | N/A | EMFILE errors |
| **Threads** | active vs max | thread pool queue | fork failures |
| **Connections** | active vs max | connection queue | refused/timeout |

## Execution Contexts

```mermaid
flowchart LR
    subgraph CONTEXTS["Supported Contexts"]
        LOCAL[localhost]
        SSH[ssh:hostname]
        K8S[k8s-pod:ns/pod]
        VM[proxmox-vm:VMID]
        LXC[lxc:VMID]
    end

    subgraph ROUTING["Command Routing"]
        DIRECT[Direct execution]
        SSH_CMD[SSH command]
        KUBECTL[kubectl exec]
        QM[qm guest exec]
        PCT[pct exec]
    end

    LOCAL --> DIRECT
    SSH --> SSH_CMD
    K8S --> KUBECTL
    VM --> QM
    LXC --> PCT
```

## Anti-Patterns

### What NOT To Do

```mermaid
flowchart TD
    BAD1[Start with service-specific tools] -->|WRONG| X1[Confirmation bias]
    BAD2[Assume bottleneck without data] -->|WRONG| X2[Wasted time]
    BAD3[Check one resource only] -->|WRONG| X3[Missed root cause]
    BAD4[Skip error checks] -->|WRONG| X4[Obvious signal missed]
    BAD5[Only check workload layer] -->|WRONG| X5[Missed host issues]
```

### Correct Flow

```mermaid
flowchart TD
    A[Symptom Reported] --> B[Run USE Checklist]
    B --> C{Errors Found?}
    C -->|Yes| D[Investigate errors first]
    C -->|No| E{High Utilization?}
    E -->|Yes| F[Identify saturated resource]
    E -->|No| G{Saturation?}
    G -->|Yes| H[Check queue depths]
    G -->|No| I[Check application-level]

    D --> J[Root Cause]
    F --> J
    H --> J
    I --> J
```

## File Structure

```
scripts/perf/
├── use-checklist.sh        # Main USE method sweep (follows flowchart)
├── quick-triage.sh         # 60-second subset
├── install-crisis-tools.sh # Pre-install diagnostic packages
├── cpu-deep-dive.sh        # Detailed CPU analysis
├── memory-deep-dive.sh     # Detailed memory analysis
├── disk-deep-dive.sh       # Detailed disk I/O analysis
├── network-deep-dive.sh    # Detailed network analysis
├── gpu-deep-dive.sh        # Detailed GPU analysis
├── flame-graph.sh          # Generate CPU/off-CPU flame graphs
├── compare-reports.sh      # Compare JSON reports
├── reports/                # Timestamped JSON outputs
└── flames/                 # Generated flame graph SVGs
```

## References

- [The USE Method](https://www.brendangregg.com/usemethod.html) - Brendan Gregg
- [USE Method Linux Checklist](https://www.brendangregg.com/USEmethod/use-linux.html)
- [Linux Crisis Tools](https://www.brendangregg.com/blog/2024-03-24/linux-crisis-tools.html)
- [60-Second Linux Performance Analysis](https://netflixtechblog.com/linux-performance-analysis-in-60-000-milliseconds-accc10403c55)
