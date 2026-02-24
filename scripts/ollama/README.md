# ollama Scripts

Scripts for managing Ollama GPU inference server and its Home Assistant integration.

## Scripts

| Script | Description |
|--------|-------------|
| `check-ollama.sh` | Full status check: pod, API, models, GPU, HA integration state. Start here when troubleshooting. |
| `test-inference.sh` | Benchmark model inference speed with timing breakdown (load, prompt, inference, tokens/sec).<br>Usage: `test-inference.sh [model] [prompt]`<br>Example: `test-inference.sh qwen2.5:3b "hello"` |
| `set-ha-model.sh` | Change the HA conversation agent model. Creates backup, edits atomically inside container, verifies, rolls back on failure.<br>Usage: `set-ha-model.sh <model>`<br>Example: `set-ha-model.sh qwen2.5:3b` |

## Quick Reference

```bash
# Voice PE stuck blue?
scripts/ollama/check-ollama.sh
scripts/haos/reload-config-entry.sh ollama
scripts/haos/reset-voice-pe.sh

# Voice PE slow?
scripts/ollama/test-inference.sh qwen2.5:3b "hello"
scripts/ollama/set-ha-model.sh qwen2.5:3b
```

## Model Selection (RTX 3070, 8GB VRAM)

| Model | GPU Split | Speed | Voice Use |
|-------|-----------|-------|-----------|
| qwen2.5:3b | 86% GPU | Fast | Recommended |
| gemma3:4b | ~70% GPU | Medium | Good quality |
| qwen2.5:7b | 46% GPU | ~1 tok/s | Too slow |

## Related

- **Runbook**: `docs/runbooks/voice-pe-ollama-diagnosis-runbook.md`
- **RCAs**: `docs/rca/2026-02-23-ollama-voice-pe-slow-response.md`, `docs/rca/RCA-Voice-PE-Ollama-Outage-2026-01-01.md`
- **HA integration docs**: `docs/reference/integrations/home-assistant/ollama/CLAUDE.md`
- **HAOS scripts**: `scripts/haos/` (reload-config-entry, reset-voice-pe, read-ha-storage)
