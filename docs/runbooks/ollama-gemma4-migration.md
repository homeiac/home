# Ollama Gemma 4 Migration Runbook

**Date**: 2026-04-05
**Author**: Claude Code
**Status**: Complete

## Summary

Migrate Ollama models from current stack to Gemma 4 (e2b) after benchmark testing showed decisive performance improvements.

## Context

### Current Model Stack (pre-migration)
| Use Case | Model | Speed | Notes |
|----------|-------|-------|-------|
| Voice PE conversation | qwen3.5:4b | 5.4 tok/s | BELOW 10 tok/s threshold |
| Camera vision analysis | gemma3:4b | ~15 tok/s | LLM Vision blueprint |
| Package delivery detection | llava:7b | ~8 tok/s | llmvision.image_analyzer |

### Hardware
- **GPU**: NVIDIA RTX 3070 (8GB VRAM)
- **Node**: k3s-vm-pumped-piglet-gpu
- **Constraints**: OLLAMA_MAX_LOADED_MODELS=1, OLLAMA_GPU_OVERHEAD=1GB

### Benchmark Results (2026-04-05)

**qwen3.5:4b vs gemma4:e2b** across 4 Voice PE scenarios, 3 iterations each:

| Test | qwen3.5:4b | gemma4:e2b |
|------|-----------|-----------|
| Quick Q&A | 8.84s / 5.1 t/s | 0.99s / 21.7 t/s |
| Time parsing | 3.58s / 6.0 t/s | 0.92s / 20.8 t/s |
| Entity control | 5.89s / 5.3 t/s | 1.31s / 18.3 t/s |
| Multi-step reasoning | 6.06s / 5.4 t/s | 1.60s / 19.6 t/s |
| **Overall** | **6.09s / 5.4 t/s** | **1.21s / 20.1 t/s** |

**Result**: gemma4:e2b is 269% faster, 80% less latency. Passes Voice PE threshold (>10 tok/s). Response quality is concise and natural (better for voice).

### Gemma 4 Model Selection

| Variant | Size | VRAM Fit (8GB) | Notes |
|---------|------|----------------|-------|
| gemma4:e2b | 7.2GB (q4_K_M) | YES | Best fit for RTX 3070 |
| gemma4:e4b | 9.6GB (q4_K_M) | NO | Exceeds VRAM with 1GB overhead |
| gemma4:26b | 18GB | NO | Way too large |

## Migration Steps

### Step 1: Upgrade Ollama (DONE)
- **File**: `gitops/clusters/homelab/apps/ollama/deployment.yaml`
- **Change**: `ollama/ollama:0.17.7` -> `ollama/ollama:0.20.2`
- **Why**: Gemma 4 requires Ollama 0.20.0+

### Step 2: Update model-update Job
- **File**: `gitops/clusters/homelab/apps/ollama/job-model-update.yaml`
- **Change**: NEW_MODEL=`gemma4:e2b`, OLD_MODEL=`qwen3.5:4b`
- **Why**: Flux-managed model lifecycle

### Step 3: Update HA conversation agent
- **Script**: `scripts/ollama/set-ha-model.sh gemma4:e2b`
- **What it does**: Edits HA storage JSON inside HAOS container, reloads Ollama integration
- **Rollback**: Timestamped backup created automatically

### Step 4: Update vision automations (NOT changing)
- **LLM Vision** (automations.yaml lines 17, 37): `gemma3:4b` -> keep as-is
- **Package Detection** (lines 189, 319): `llava:7b` -> keep as-is
- **Why**: These use the `llmvision.image_analyzer` action with separate provider config.
  gemma4:e2b is multimodal but the LLM Vision integration manages its own model loading.
  Since OLLAMA_MAX_LOADED_MODELS=1, loading gemma4:e2b for vision would evict
  the conversation model. The vision models are loaded on-demand when events trigger.
  Changing these requires testing the LLM Vision integration separately.

### Step 5: Update model selection reference
- **File**: `scripts/ollama/README.md`
- **Change**: Add gemma4:e2b to model table, mark as recommended

### Step 6: Clean up old models
- Old models (qwen3.5:4b, qwen3:4b) removed via model-update Job
- gemma4:e2b pulled via same Job

## Rollback Plan

1. **Revert deployment image**: `ollama/ollama:0.20.2` -> `ollama/ollama:0.17.7` (only if 0.20.2 unstable)
2. **Revert conversation model**: `scripts/ollama/set-ha-model.sh qwen3.5:4b`
3. **Revert model-update Job**: Change NEW_MODEL back to `qwen3.5:4b`

## Verification

After migration:
```bash
# Check Ollama version and models
scripts/ollama/check-ollama.sh

# Test inference speed
scripts/ollama/test-inference.sh gemma4:e2b "what time is it?"

# Test voice PE end-to-end
# Say "Hey Nabu, what's the weather like?" and confirm response <3s
```

## Future Work

- Test gemma4:e2b with LLM Vision integration for camera analysis (replace gemma3:4b)
- Test gemma4:e2b with package detection (replace llava:7b)
- Consider gemma4:e4b if a GPU upgrade happens
