# SRE Performance Diagnosis Runbook

A repeatable, **script-based** methodology for diagnosing performance issues.
Works every time, regardless of where the problem is.

## Core Principle

**USE Method first, then Application Logs, then Standard Tracing Tools.**

Don't assume the bottleneck - let the data tell you where to look.

**ALWAYS USE SCRIPTS - NO ONE-OFF COMMANDS.**

---

## Critical Lesson: Reproduce, Measure, Research, Check If Solved

When USE Method is clean but symptom persists:

### Step 2c: Reproduce and Isolate

**Reduce to smallest measurable scope.**

```bash
# Latency issue? Ping the actual endpoint
ping <device-ip>

# Service slow? Time the specific call
scripts/perf/network-timing.sh <url>

# Intermittent? Measure repeatedly
scripts/perf/network-timing.sh --repeat 10 <url>
```

### Step 2d: Measure the Actual Symptom

Get **numbers**, not assumptions. Compare against baseline:
- Normal: <10ms local, <50ms remote
- Slow: >100ms needs investigation
- Broken: >500ms or high jitter

### Step 2e: Research the Symptom

```bash
# Search for known issues
# "ESP32 400ms latency" → WiFi power save
# "K8s pod slow startup" → image pull policy
# "TLS handshake 2s" → certificate chain
```

### Step 2f: Check If Already Solved

```bash
# Query OpenMemory for previous fixes
/recall "<symptom keywords>"

# Check git history
git log --all --oneline --grep="<symptom>"

# Check if config fix already applied
```

**Expected outcome**: Either find root cause OR report "Problem already solved. No action needed."

---

## Quick Start: Automated Diagnosis

```bash
# Run the orchestrator - it follows the flowchart automatically
scripts/perf/diagnose.sh --target proxmox-vm:116

# With service URL for network timing (Step 3)
scripts/perf/diagnose.sh --target proxmox-vm:116 --url http://homeassistant.maas:8123/api/
```

---

## The Flowchart

```
       "It's slow"
            |
            v
    +----------------+
    | USE Method     |
    | (all resources)|
    +----------------+
            |
            v
      .----------.
     / resource   \-----> yes -----> deep dive -----> fix
     \ issue?     /                  that resource
      '----------'
            |
            no
            |
            v
    +----------------+
    | check app logs |
    +----------------+
            |
            v
      .----------.
     / external   \-----> yes -----> measure endpoint
     \ latency?   /                  directly (ping, curl -w)
      '----------'                          |
            |                               v
            no                        .----------.
            |                        / already    \---> yes ---> done.
            v                        \ solved?    /              no action needed
    +----------------+                '----------'
    | add tracing    |                      |
    | (bpftrace,     |                      no
    | tcpdump)       |                      |
    +----------------+                      v
            |                         research symptom
            v                         (Google, GitHub)
         find it                            |
                                            v
                                         fix it
```

### Decision Tree (Text)

```
1. USE Method (CPU, Memory, Disk, Network)
   └─> resource issue? ─────> yes ─> deep dive ─> fix
                        └─> no
                             │
2. Application Logs          │
   └─> timing/errors logged? ┘
                        └─> external latency?
                             │
3. Reproduce & Measure       │
   └─> ping/curl the actual endpoint
   └─> already solved? ─────> yes ─> done (no action needed)
                        └─> no ─> research ─> fix
```

---

## Step 1: USE Method

**For EVERY resource, check Errors, Utilization, Saturation.**

### Quick Commands

```bash
# Run full USE checklist
scripts/perf/use-checklist.sh --context <target>

# For Proxmox VMs
scripts/perf/run-on-proxmox-vm.sh <vmid>

# 60-second triage
scripts/perf/quick-triage.sh --context <target>
```

### What to Check

| Resource | Errors (E) | Utilization (U) | Saturation (S) |
|----------|------------|-----------------|----------------|
| **CPU** | `dmesg \| grep -i mce` | `vmstat` (us+sy) | `vmstat` (r > nproc) |
| **Memory** | `dmesg \| grep -i oom` | `free -m` | `vmstat` (si/so > 0) |
| **Disk** | `dmesg \| grep -i "i/o error"` | `iostat -x` (%util) | `iostat -x` (avgqu-sz) |
| **Network** | `ip -s link` (errors) | `sar -n DEV` | `ip -s link` (dropped) |
| **GPU** | `dmesg \| grep -i xid` | `nvidia-smi` | `nvidia-smi` (memory) |

### Decision Point

- **Resource problem found?** -> Go to Step 2a (Deep Dive)
- **All resources OK?** -> Go to Step 2b (Application Layer)

---

## Step 2a: Resource Deep Dive

When USE shows a specific resource problem:

### CPU Issues

```bash
# Per-core breakdown
mpstat -P ALL 1 5

# Per-process CPU
pidstat 1 5

# Real-time top consumers
top -b -n 1 | head -20

# CPU flame graph (shows WHERE CPU time is spent)
perf record -F 99 -a -g -- sleep 30
perf script | stackcollapse-perf.pl | flamegraph.pl > cpu.svg
```

### Memory Issues

```bash
# Memory state
free -m
cat /proc/meminfo

# Per-process memory
ps aux --sort=-%mem | head -20

# Slab cache (kernel memory)
slabtop -o | head -20

# Page scanning (memory pressure)
sar -B 1 5
```

### Disk I/O Issues

```bash
# Per-device I/O
iostat -xz 1 5

# Per-process I/O
iotop -b -n 3

# Queue depth and latency
iostat -x 1 5  # avgqu-sz, await columns
```

### Network Issues

```bash
# Interface stats
ip -s link

# TCP state
ss -tunap

# TCP retransmits
netstat -s | grep -i retrans

# Socket buffer status
ss -m
```

---

## Step 2b: Application Layer

When USE shows all resources OK - problem is in application behavior.

### Check Application Logs

```bash
# Systemd service
journalctl -u <service> --since "10 minutes ago"

# Kubernetes pod
kubectl logs <pod> --tail=100

# Docker container
docker logs <container> --tail=100

# Home Assistant
# Check via HA UI or /config/home-assistant.log
```

### What to Look For

1. **Timing information** - "Request took X seconds"
2. **Timeouts** - "Connection timed out"
3. **External dependencies** - "Waiting for response from..."
4. **Error messages** - Stack traces, exceptions

### If Logs Reveal External Service Latency

Go to Step 3 (Standard Tracing Tools)

---

## Step 3: Standard Tracing Tools

Use EXISTING tools - don't reinvent.

### Network Timing (curl)

```bash
# Full timing breakdown
curl -w "DNS: %{time_namelookup}s\nTCP: %{time_connect}s\nTLS: %{time_appconnect}s\nTTFB: %{time_starttransfer}s\nTotal: %{time_total}s\n" \
  -o /dev/null -s http://<target>/

# Interpretation:
# - DNS slow?    -> Check resolver, /etc/resolv.conf
# - TCP slow?    -> Firewall, routing, network path
# - TLS slow?    -> Certificate issues, crypto overhead
# - TTFB slow?   -> Server processing time
# - Total slow?  -> Response size, bandwidth
```

### Network Path

```bash
# Route to target
traceroute <host>

# Latency
ping -c 10 <host>

# MTU issues
ping -M do -s 1472 <host>
```

### TCP Connection Tracing (eBPF)

```bash
# Watch new TCP connections
tcpconnect-bpfcc

# TCP session durations
tcplife-bpfcc

# TCP retransmits
tcpretrans-bpfcc
```

### Packet Analysis

```bash
# Capture traffic on specific port
tcpdump -i any -nn port <port> -w capture.pcap

# Live view
tcpdump -i any -nn port <port>
```

### DNS Tracing

```bash
# DNS query latency
gethostlatency-bpfcc

# Manual DNS check
dig <hostname>
time nslookup <hostname>
```

### Syscall Tracing

```bash
# Slow syscalls
syscount-bpfcc -L

# File opens
opensnoop-bpfcc

# Off-CPU time (where is process waiting?)
offcputime-bpfcc -p <pid>
```

---

## Quick Reference: Which Tool for What

| Symptom | Tool | Command |
|---------|------|---------|
| General slowness | USE checklist | `use-checklist.sh` |
| Network latency | curl | `curl -w @timing` |
| Connection issues | tcpconnect | `tcpconnect-bpfcc` |
| DNS slow | dig | `dig +trace <host>` |
| Packet loss | ping | `ping -c 100 <host>` |
| Route problems | traceroute | `traceroute <host>` |
| CPU hotspot | perf | `perf top` |
| Memory leak | free + ps | `free -m; ps aux --sort=-%mem` |
| Disk I/O | iostat | `iostat -xz 1` |
| File access | opensnoop | `opensnoop-bpfcc` |
| Process blocking | offcputime | `offcputime-bpfcc` |

---

## Anti-Patterns

**DON'T:**
- Assume the bottleneck without measuring
- Check only one resource (tunnel vision)
- Create custom scripts when standard tools exist
- Skip the USE method and jump to app-specific debugging

**DO:**
- Always start with USE checklist
- Check ALL resources before deep diving
- When USE is clean -> logs -> tracing
- Let the DATA tell you where to look

---

## Validation Test Case: Voice PE <-> HAOS

**Symptom**: "Voice PE TTS is slow"

### Apply the Flowchart (Using Scripts)

**Option A: Full Automated Diagnosis**
```bash
scripts/perf/diagnose.sh --target proxmox-vm:116 --url http://homeassistant.maas:8123/api/
```

**Option B: Step-by-Step**

**Step 1: USE Method**
```bash
scripts/perf/run-on-proxmox-vm.sh 116  # Checks BOTH VM and HOST layers
```
Expected: Either all OK (→ Step 2b) or issues found (→ Step 2a)

**Step 2a: Resource Deep Dive** (if USE found issues)
```bash
scripts/perf/memory-deep-dive.sh --target proxmox-vm:116
```
Expected: Identifies memory consumers, OOM history, swap activity

**Step 2b: Application Logs** (if USE clean)
```bash
scripts/perf/app-logs.sh --target proxmox-vm:116
```
Expected: Logs reveal which phase is slow

**Step 3: Network Timing** (if logs point to external)
```bash
scripts/perf/network-timing.sh http://homeassistant.maas:8123/api/
```
Expected: Timing breakdown shows exact bottleneck

**Success**: Flowchart leads to root cause without assumptions.

---

## Script Portfolio

All scripts are in `scripts/perf/`. **ALWAYS use these - no one-off commands.**

### Orchestration

| Script | Purpose | Usage |
|--------|---------|-------|
| `diagnose.sh` | **Main orchestrator** - follows flowchart | `./diagnose.sh --target proxmox-vm:116` |

### Step 1: USE Method

| Script | Purpose | Usage |
|--------|---------|-------|
| `use-checklist.sh` | Full USE method sweep | `./use-checklist.sh --context ssh:root@host` |
| `quick-triage.sh` | 60-second analysis | `./quick-triage.sh` |
| `run-on-proxmox-vm.sh` | USE Method on Proxmox VMs (both layers) | `./run-on-proxmox-vm.sh 116` |

### Step 2a: Resource Deep Dive

| Script | Purpose | Usage |
|--------|---------|-------|
| `memory-deep-dive.sh` | Memory pressure analysis | `./memory-deep-dive.sh --target proxmox-vm:116` |
| `cpu-deep-dive.sh` | CPU hotspot analysis | (planned) |
| `disk-deep-dive.sh` | Disk I/O analysis | (planned) |
| `network-deep-dive.sh` | Network saturation analysis | (planned) |

### Step 2b: Application Layer

| Script | Purpose | Usage |
|--------|---------|-------|
| `app-logs.sh` | Application log analysis | `./app-logs.sh --target k8s-pod:frigate/pod` |

### Step 2c-f: Reproduce, Measure, Research

| Script | Purpose | Usage |
|--------|---------|-------|
| `network-topology.sh` | Cross-subnet latency analysis | `./network-topology.sh --from <ip> --to <ip>` |
| `network-timing.sh` | HTTP endpoint timing breakdown | `./network-timing.sh http://service:8123/` |
| `ping` | Basic latency measurement | `ping -c 10 <device-ip>` |

### Step 3: Standard Tracing

| Script | Purpose | Usage |
|--------|---------|-------|
| `network-timing.sh` | curl -w timing breakdown | `./network-timing.sh http://service:8123/` |

### Utilities

| Script | Purpose | Usage |
|--------|---------|-------|
| `install-crisis-tools.sh` | Pre-install diagnostic tools | `./install-crisis-tools.sh` |

---

## Tags

performance, perf, latency, debugging, troubleshooting, USE-method, brendan-gregg, sre, runbook, methodology, bpftrace, eBPF, tracing, scripts
