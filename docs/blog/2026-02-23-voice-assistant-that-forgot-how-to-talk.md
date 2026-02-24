# The Voice Assistant That Forgot How to Talk

*2026-02-23*

"OK Nabu, what's my notification?"

Blue light. Pulsing. Waiting. Nothing.

My Home Assistant Voice PE — a $59 device that's supposed to make my smart home feel like the future — was stuck. Again. The blue LED meant it heard me, sent my words to Home Assistant, and was now patiently waiting for Ollama to think of something to say back. Ollama, apparently, had nothing to say.

## The Investigation

The first instinct is always "is it plugged in?" For a voice pipeline with four moving parts, the equivalent is `scripts/ollama/check-ollama.sh`:

```
--- Pod Status ---
ollama-gpu-696df7df9d-j965p   1/1   Running   0   8d

--- Available Models ---
  qwen2.5:7b      4.7 GB  (7.6B)
  qwen2.5:3b      1.9 GB  (3.1B)
  gemma3:4b        3.3 GB  (4.3B)

--- GPU Status ---
NVIDIA GeForce RTX 3070, 3973 MiB / 8192 MiB, 1%, 52C

--- HA Integration ---
  State: setup_error
```

There it is. `setup_error`. Home Assistant's Ollama integration had given up. The pod was running, the API was responding, the GPU was idling at 52C with nothing to do — but HA had decided, at some point in the past, that Ollama was unreachable, and never tried again.

## The Silent Failure

This is what makes `setup_error` insidious. Unlike a pod crash (which Kubernetes restarts), or a network failure (which times out with an error), `setup_error` is a permanent surrender. The integration tried to connect, failed once, and stopped trying. No retry. No alert. No indication in the HA UI unless you go looking.

```bash
scripts/haos/reload-config-entry.sh ollama
# Domain 'ollama' → entry_id: 01KDWN1FFY773DKCC1WS8V1ZD0
# Reloading config entry...
# New state: loaded
```

One API call and it's back. But the Voice PE was still stuck blue from the old request, so:

```bash
scripts/haos/reset-voice-pe.sh
# Voice PE state: responding
```

"OK Nabu, what's my notification?"

Blue light. Pulsing. Waiting. Still waiting. Eventually, after about a hundred seconds: "I don't have access to real-time information..."

Working, but unusably slow.

## The VRAM Problem

```bash
scripts/ollama/test-inference.sh qwen2.5:7b "what time is it?"
# Response: ...
# Model load:   23.6s
# Inference:    75.0s (69 tokens)
# Speed:        0.9 tokens/sec
# ⚠ SLOW — likely running on CPU
```

One token per second. For a voice assistant that should respond in under two seconds, this is like asking someone a question and having them respond one... word... at... a... time... over... the... next... minute.

The Ollama logs explained why:

```
gpu VRAM usage didn't recover within timeout
runner.size="5.9 GiB" runner.vram="2.7 GiB"
```

The qwen2.5:7b model needs 5.9 GiB when loaded. The RTX 3070 has 8 GiB, but after driver overhead and CUDA context, only 2.7 GiB was available. So Ollama split the work: 46% GPU, 54% CPU. A 7-billion parameter model running mostly on CPU is not a voice assistant. It's a philosophy professor composing a dissertation.

## The Fix

```bash
scripts/ollama/set-ha-model.sh qwen2.5:3b
# Creating backup: core.config_entries.backup.20260224_000746
# Changed: qwen2.5:7b -> qwen2.5:3b
# Verified: model = qwen2.5:3b
# Integration state: loaded
```

The 3b model fits in VRAM with room to spare: 86% GPU, 14% CPU. Response time drops from 100 seconds to a few. The quality difference for "what's my notification" or "turn off the lights" is negligible.

## The Part Where I Corrupted the Config

I should mention this because it's the most important lesson.

My first version of `set-ha-model.sh` tried to pipe JSON through `qm guest exec` (Proxmox VM command execution) into a file inside a Docker container inside a VM. The pipe silently truncated. The config file went to 0 bytes. Home Assistant's brain — every integration, every device, every automation reference — gone.

Fortunately:
1. HA was still running with the config in memory
2. HA creates `.backup` files automatically
3. I restored from the most recent backup

The rewritten script now:
- Creates a timestamped backup **before any modification**
- Edits **inside the container** using `docker exec python3` (no piping through qm guest exec)
- Verifies the file is valid JSON with the correct model **after writing**
- Rolls back to the backup if anything fails

This is the "measure twice, cut once" principle, except the first version was "don't measure, use a chainsaw."

## What I Built

The real output of this incident wasn't fixing the voice assistant. It was building the scripts so that next time — and there will be a next time — it takes 30 seconds instead of 30 minutes:

```bash
# "OK Nabu isn't working"
scripts/ollama/check-ollama.sh          # What's broken?
scripts/haos/reload-config-entry.sh ollama  # Fix HA integration
scripts/haos/reset-voice-pe.sh          # Unstick the Voice PE
scripts/ollama/test-inference.sh         # Is it fast enough?
scripts/ollama/set-ha-model.sh qwen2.5:3b  # Switch models safely
```

Seven scripts. Each one is a thing I did by hand with raw curl commands, then realized I'd done the same raw curl commands three months ago, then finally made it a script.

## The Takeaway

The voice pipeline has four components: Voice PE hardware, Home Assistant STT/TTS, the conversation agent integration, and Ollama inference. Any one can fail silently. The combination of "integration permanently gives up after one failure" and "model silently falls back to CPU" meant the voice assistant was both broken AND slow, for different reasons, at the same time.

For a $59 device that's supposed to feel magical, the infrastructure behind it is anything but. But that's the difference between a demo and a daily driver. Demos work once. Daily drivers need runbooks.

**Scripts**: `scripts/ollama/` and `scripts/haos/`
**Runbook**: `docs/runbooks/voice-pe-ollama-diagnosis-runbook.md`
