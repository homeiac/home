# Runbook: Voice PE / Ollama Diagnosis and Recovery

**Last Updated**: 2026-02-23
**Owner**: Homelab
**Related RCAs**:
- [RCA-Voice-PE-Ollama-Outage-2026-01-01](../rca/RCA-Voice-PE-Ollama-Outage-2026-01-01.md) — ZFS/USB cascade
- [RCA-Ollama-Voice-PE-Slow-2026-02-23](../rca/2026-02-23-ollama-voice-pe-slow-response.md) — setup_error + VRAM overflow

## Overview

This runbook covers diagnosis and recovery when the Voice PE device is not responding, showing stuck blue LED, or responding slowly.

**Architecture**: Voice PE → (wake word) → HA STT → HA Conversation Agent (Ollama) → HA TTS → Voice PE speaker

## Voice PE LED States

| LED Color | Meaning | Likely Cause |
|-----------|---------|--------------|
| Off/Dim | Idle, listening for wake word | Normal |
| Blue (pulsing) | Listening/Processing | Normal during interaction |
| Blue (stuck) | Waiting for response | Backend (Ollama/HA) issue |
| Green | Speaking response | Normal |
| Red | Error/Muted | Check mute switch |
| Yellow | Booting/Updating | Wait or check WiFi |

---

## Quick Fix (90% of cases)

```bash
# 1. Full status check
scripts/ollama/check-ollama.sh

# 2. If HA integration shows setup_error → reload it
scripts/haos/reload-config-entry.sh ollama

# 3. Reset the stuck Voice PE
scripts/haos/reset-voice-pe.sh

# Done. Try "OK Nabu" again.
```

---

## Detailed Diagnosis Flow

```
Voice PE Stuck Blue?
        │
        ▼
scripts/ollama/check-ollama.sh
        │
        ├── HA Integration: setup_error? ──→ Section 1
        ├── Pod: Not Running? ─────────────→ Section 2
        ├── GPU: Not available? ───────────→ Section 3
        ├── API: Unreachable? ─────────────→ Section 2
        └── All OK but slow? ─────────────→ Section 4
```

---

## Section 1: HA Ollama Integration Issue

**Symptom**: `check-ollama.sh` shows `State: setup_error`

```bash
# Check integration state
scripts/haos/get-integration-config.sh ollama
# Look for: "state": "loaded" (good) vs "setup_error" (bad)

# Fix: reload the config entry
scripts/haos/reload-config-entry.sh ollama

# Reset the stuck Voice PE
scripts/haos/reset-voice-pe.sh
```

**If reload doesn't fix it** (state stays `setup_error`):
1. Check that Ollama API is actually reachable from HAOS:
   ```bash
   scripts/haos/guest-exec.sh "docker exec homeassistant curl -s http://192.168.4.85/api/tags"
   ```
2. If unreachable → go to Section 2 (pod issue)
3. If reachable but still setup_error → reconfigure in HA UI:
   - Settings → Devices & Services → Ollama → Delete → Re-add with `http://192.168.4.85`

**IMPORTANT**: HA integrations do NOT auto-recover from `setup_error`. Manual reload is always required.

---

## Section 2: Ollama Pod Not Running

**Symptom**: `check-ollama.sh` shows pod not Running, or API unreachable

```bash
# Detailed pod status
export KUBECONFIG=~/kubeconfig
kubectl get pods -n ollama -o wide
kubectl describe pod -n ollama -l app=ollama-gpu
kubectl logs -n ollama -l app=ollama-gpu --tail=30
```

**If Pending**: Check GPU node status → Section 3

**If CrashLoopBackOff**:
```bash
kubectl logs -n ollama -l app=ollama-gpu --previous --tail=50
# Common: OOM, GPU driver mismatch, image pull failure
```

**If no pod at all**:
```bash
kubectl get deploy -n ollama
# If 0 replicas → check Flux reconciliation
flux reconcile kustomization flux-system --with-source
```

---

## Section 3: GPU Node / VM Issue

**Symptom**: GPU node NotReady, Ollama pod Pending

```bash
# Check nodes
kubectl get nodes

# If GPU node NotReady, check k3s inside VM
ssh root@pumped-piglet.maas "qm guest exec 105 -- systemctl status k3s --no-pager"

# If guest exec times out → VM may be hung
ssh root@pumped-piglet.maas "qm list"

# Check ZFS (common cause of VM hangs)
ssh root@pumped-piglet.maas "zpool status -x"
```

**If ZFS SUSPENDED**: See the [full GPU node recovery procedure](#full-gpu-node-recovery) below.

**If VM stopped**:
```bash
ssh root@pumped-piglet.maas "qm start 105"
```

---

## Section 4: Ollama Slow (Responding but Taking Forever)

**Symptom**: Voice PE eventually responds but takes 30+ seconds

```bash
# Check model and GPU split
scripts/ollama/check-ollama.sh
# Look at "Loaded Models" → PROCESSOR column

# Benchmark
scripts/ollama/test-inference.sh qwen2.5:3b "hello"
```

**Key metric**: The PROCESSOR column in `ollama ps`:
| Split | Meaning | Action |
|-------|---------|--------|
| 100% GPU | Full GPU acceleration | Good — issue is elsewhere |
| 80%+ GPU | Mostly GPU | Acceptable for voice |
| 50/50 | Split CPU/GPU | Model too large — switch to smaller |
| 100% CPU | No GPU | GPU not available — check nvidia-smi |

**Switch to a faster model**:
```bash
# Switch HA conversation agent to qwen2.5:3b (fits in VRAM)
scripts/ollama/set-ha-model.sh qwen2.5:3b

# Pre-load the model
kubectl exec -n ollama $(kubectl get pods -n ollama -l app=ollama-gpu -o name | head -1) -- ollama run qwen2.5:3b "hi"
```

### Model Selection Guide (RTX 3070, 8GB VRAM)

| Model | Size | GPU Split | Speed | Voice Use |
|-------|------|-----------|-------|-----------|
| qwen2.5:3b | 1.9 GB | 86% GPU | Fast | Recommended |
| gemma3:4b | 3.3 GB | ~70% GPU | Medium | Good quality |
| qwen2.5:7b | 4.7 GB | 46% GPU | ~1 tok/s | Too slow |

---

## Recovery Procedures

### Reset Voice PE (Quick)

```bash
scripts/haos/reset-voice-pe.sh
# Or with custom message:
scripts/haos/reset-voice-pe.sh "System reset complete"
```

### Reload HA Ollama Integration

```bash
scripts/haos/reload-config-entry.sh ollama
```

### Change Ollama Model

```bash
# Safe: creates backup, edits atomically, verifies, rolls back on failure
scripts/ollama/set-ha-model.sh qwen2.5:3b
```

### Check Current Model Configuration

```bash
scripts/haos/read-ha-storage.sh core.config_entries \
  '.data.entries[] | select(.domain == "ollama") | .subentries[0].data'
```

### Restart Ollama Pod

```bash
kubectl rollout restart deployment/ollama-gpu -n ollama
```

### Full GPU Node Recovery

```bash
ssh root@pumped-piglet.maas

# 1. Check ZFS
zpool status -x

# 2. If SUSPENDED → unplug faulty USB drive, power cycle host

# 3. After host is back, remove problematic disks if needed
qm set 105 --delete scsi1      # 20TB data disk
qm set 105 --delete virtiofs0  # virtiofs share

# 4. Start VM
qm start 105

# 5. Verify
qm guest exec 105 -- systemctl status k3s --no-pager
```

---

## Key IPs and Hosts

| Component | IP/Host | Notes |
|-----------|---------|-------|
| Home Assistant | 192.168.4.240 | HAOS on chief-horse (VMID 116) |
| Ollama LoadBalancer | 192.168.4.85 | MetalLB IP |
| pumped-piglet (Proxmox) | pumped-piglet.maas | Hosts GPU VM |
| k3s-vm-pumped-piglet-gpu | VM 105 | GPU node (RTX 3070) |
| k3s-vm-pve | VM 107 on pve.maas | Control plane |

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/ollama/check-ollama.sh` | Full status: pod, API, models, GPU, HA integration |
| `scripts/ollama/test-inference.sh` | Benchmark model with timing breakdown |
| `scripts/ollama/set-ha-model.sh` | Change HA conversation model (backup + atomic) |
| `scripts/haos/get-integration-config.sh` | Get any HA integration's config entry |
| `scripts/haos/reload-config-entry.sh` | Reload config entry by domain or entry_id |
| `scripts/haos/reset-voice-pe.sh` | Reset stuck Voice PE satellite |
| `scripts/haos/read-ha-storage.sh` | Read .storage files from HA container |
| `scripts/haos/get-entity-state.sh` | Get any HA entity state |

## Monitoring Gaps

- [ ] HA integration health checks (detect `setup_error` automatically)
- [ ] Ollama model VRAM monitoring (alert when CPU/GPU split > 50%)
- [ ] ZFS pool health alerts (DEGRADED, SUSPENDED states)
- [ ] Voice PE stuck-blue detection (satellite state monitoring)

**Tags**: voice-pe, ollama, runbook, diagnosis, troubleshooting, k3s, proxmox, zfs, pumped-piglet, home-assistant, gpu, qwen2.5, model-selection, vram
