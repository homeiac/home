# RCA: Voice PE Slow Response — Ollama Integration setup_error and Model VRAM Overflow

**Incident Date**: 2026-02-23
**Duration**: Unknown start — user reported during evening routine
**Impact**: Voice PE stuck blue (waiting for response), "OK Nabu what's my notification" taking forever
**Detection**: User-reported
**Related RCA**: [RCA-Voice-PE-Ollama-Outage-2026-01-01](RCA-Voice-PE-Ollama-Outage-2026-01-01.md)

---

## Incident Summary

The Home Assistant Voice PE satellite was unresponsive — stuck on blue LED when asking "OK Nabu what's my notification." Two independent root causes discovered:

1. **HA Ollama integration in `setup_error` state** — HA couldn't reach Ollama even though Ollama was running and the network path was fine
2. **qwen2.5:7b model too large for GPU** — 5.9 GiB model with only 2.7 GiB fitting in VRAM, causing 54% CPU / 46% GPU split and ~1 token/sec inference

---

## Timeline

| Time | Event |
|------|-------|
| Unknown | HA Ollama integration enters `setup_error` |
| 23:44 UTC | User reports "OK Nabu" taking forever |
| 23:45 | `scripts/ollama/check-ollama.sh` → Pod running, API responding, GPU available |
| 23:46 | `scripts/haos/get-integration-config.sh ollama` → state: `setup_error` |
| 23:46 | Manual inference test: 100 seconds for "what time is it?" (qwen2.5:7b) |
| 23:46 | `ollama ps` → qwen2.5:7b at 54% CPU / 46% GPU |
| 23:47 | Ollama logs: "gpu VRAM usage didn't recover within timeout" |
| 23:49 | `scripts/haos/reload-config-entry.sh ollama` → state: `loaded` |
| 23:50 | Voice PE still stuck blue (old request queued) |
| 23:51 | `scripts/haos/reset-voice-pe.sh` → state cycled back to idle |
| 23:54 | HAOS can curl Ollama fine (verified from inside HAOS VM) |
| 00:07 | `scripts/ollama/set-ha-model.sh qwen2.5:3b` → model switched |
| 00:07 | qwen2.5:3b loaded: 86% GPU / 14% CPU (vs 54%/46% for 7b) |
| 00:08 | Integration state: `loaded`, Voice PE responsive |

---

## Root Cause Analysis

### Root Cause 1: HA Integration setup_error

The HA Ollama integration was in `setup_error` state. This means HA tried to connect to Ollama at startup (or during a periodic check) and failed. Once in `setup_error`, the integration stays broken until manually reloaded — it does not auto-recover.

**Why it entered setup_error**: Unknown. Likely Ollama was temporarily unavailable (pod restart, model load timeout, or VRAM pressure) and HA's integration setup failed at that moment.

**Fix**: `scripts/haos/reload-config-entry.sh ollama`

### Root Cause 2: qwen2.5:7b VRAM Overflow

The qwen2.5:7b model requires 5.9 GiB to load. The RTX 3070 has 8 GiB VRAM but only ~2.7 GiB was available for the model (remainder used by GPU driver, display, other allocations). This forced Ollama to split: 46% GPU + 54% CPU.

**Evidence**:
```
ollama ps:
NAME          SIZE      PROCESSOR
qwen2.5:7b    6.3 GB    54%/46% CPU/GPU

Ollama logs:
gpu VRAM usage didn't recover within timeout
runner.size="5.9 GiB" runner.vram="2.7 GiB"
```

**Performance impact**: ~1 token/sec (vs 20+ tokens/sec for full GPU). A voice response that should take 2 seconds took 100+ seconds.

**Fix**: Switched to qwen2.5:3b (3.4 GiB) which fits 86% in VRAM → responsive inference.

### Root Cause 3: Config File Corruption During Fix (Self-Inflicted)

During the model switch, the initial `set-ha-model.sh` script attempted to pipe data through `qm guest exec` stdin, which silently truncated the file to 0 bytes. This corrupted `core.config_entries`.

**Recovery**: Restored from `core.config_entries.backup.*` (HA creates these automatically during config changes).

**Fix**: Rewrote script to perform atomic edits inside the container using `docker exec homeassistant python3`, with mandatory backup-before-write and verification-after-write.

---

## Diagnosis Playbook

When Voice PE is stuck blue, run these **in order**:

```bash
# 1. Quick status check — is Ollama even running?
scripts/ollama/check-ollama.sh

# 2. Is HA's integration connected?
scripts/haos/get-integration-config.sh ollama
# Look for: "state": "loaded" (good) vs "setup_error" (bad)

# 3. If setup_error → reload
scripts/haos/reload-config-entry.sh ollama

# 4. Reset the stuck Voice PE
scripts/haos/reset-voice-pe.sh

# 5. If slow → check model performance
scripts/ollama/test-inference.sh qwen2.5:3b "hello"
# Look for: tokens/sec > 10 (good), < 5 (CPU-bound)

# 6. If wrong model or too slow → switch
scripts/ollama/set-ha-model.sh qwen2.5:3b
```

---

## Model Selection Guide

| Model | Size | VRAM Needed | RTX 3070 Split | Speed | Recommended |
|-------|------|-------------|----------------|-------|-------------|
| qwen2.5:3b | 1.9 GB | ~3.4 GB loaded | 86% GPU / 14% CPU | Fast | Yes — voice assistant |
| gemma3:4b | 3.3 GB | ~4.5 GB loaded | ~70% GPU / 30% CPU | Medium | Maybe — better quality |
| qwen2.5:7b | 4.7 GB | ~5.9 GB loaded | 46% GPU / 54% CPU | Slow (~1 tok/s) | No — too slow for voice |

**Rule of thumb**: For voice, model load + inference must complete in < 5 seconds. Only models that fit mostly in VRAM achieve this on the RTX 3070.

---

## Action Items

| Item | Status |
|------|--------|
| Reload HA Ollama integration | Done |
| Switch model to qwen2.5:3b | Done |
| Create diagnostic scripts | Done (7 scripts) |
| Fix set-ha-model.sh with backup + atomic edit | Done |
| Add HA integration health monitoring | TODO |
| Add Ollama model/VRAM monitoring | TODO |

---

## Lessons Learned

1. **HA integrations don't auto-recover from setup_error** — they require manual reload. This is a monitoring gap.
2. **Model size vs VRAM is not model_size / vram_total** — Ollama needs overhead for KV cache, CUDA context, etc. A 4.7 GB model needs ~6 GB loaded.
3. **Never write files through qm guest exec stdin** — the pipe silently truncates. Always edit inside the container.
4. **Always backup before write** — the `set-ha-model.sh` script now backs up, edits atomically, verifies, and rolls back on failure.
5. **`ollama ps` tells you everything** — the PROCESSOR column shows CPU/GPU split instantly.

**Tags**: voice-pe, ollama, home-assistant, qwen2.5, gpu, vram, rtx-3070, setup_error, slow, inference, model-selection, rca
