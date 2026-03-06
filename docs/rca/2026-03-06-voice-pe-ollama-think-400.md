# RCA: Voice PE Silent Failure — Ollama 0.17 Think Parameter Incompatibility

**Incident Date**: 2026-03-06
**Duration**: Unknown start — user reported during evening routine
**Impact**: Voice PE heard wake word and detected notifications correctly (blue LED) but never responded to "what's my notification"
**Detection**: User-reported
**Related RCA**: [2026-02-23 Ollama Voice PE Slow Response](2026-02-23-ollama-voice-pe-slow-response.md)

---

## Incident Summary

The Home Assistant Voice PE satellite correctly detected the wake word and identified a package notification (blue LED), but returned no spoken response when asked "what's my notification." The Ollama pod was running and healthy, but every `/api/chat` request from Home Assistant returned HTTP 400.

Root cause: HA's Ollama conversation integration was sending `think: true` to `qwen2.5:7b`, which does not support Ollama's thinking feature. Ollama 0.17 added the `think` parameter and returns 400 for models that lack thinking support.

---

## Timeline

| Time (UTC) | Event |
|------|-------|
| Unknown | HA Ollama conversation subentry configured with "Think before responding" enabled |
| 18:09 | Ollama logs: `400` on `POST /api/chat` from `10.42.0.1` (HA) |
| 18:48 | Second `400` on `/api/chat` — user reports Voice PE not answering |
| 18:49 | Investigation begins — K3s cluster accessed via `qm guest exec` on pumped-piglet |
| 18:49 | `k3s-vm-still-fawn` found `NotReady`, QEMU guest agent not running |
| 18:50 | Ollama pod `tw6bj` confirmed Running 1/1, API responding on `192.168.4.85` |
| 18:52 | Direct `curl` to `/api/chat` returns 200 — Ollama works fine without `think` |
| 18:52 | Ollama logs show successful 200 for direct test, 400 for HA requests |
| 18:55 | HA conversation API test: default agent returns intent error, Ollama agent returns 500 |
| 19:03 | Reproduced: `think: true` + `qwen2.5:7b` → `400: "qwen2.5:7b does not support thinking"` |
| 19:10 | Fix: upgrade Ollama `0.17.0` → `0.17.7`, switch model to `qwen3.5:4b` (supports thinking) |
| 19:12 | Git push, Flux reconcile begins |
| 19:18 | New Ollama pod running 0.17.7, confirmed via `/api/version` |
| 19:25 | `qwen3.5:4b` pulled, old models deleted, thinking test passes |
| 19:30 | HA model config updated to `qwen3.5:4b`, Voice PE responding |

---

## Root Cause Analysis

### Root Cause: Think Parameter + Non-Thinking Model = 400

Home Assistant 2026.1.3's Ollama integration exposes a "Think before responding" toggle in the conversation agent subentry configuration. When enabled, HA sends `"think": true` in the `/api/chat` request body.

Ollama 0.17 introduced the `think` parameter for reasoning models. When a model does **not** support thinking (like `qwen2.5:7b`), Ollama returns:

```json
{"error": "\"qwen2.5:7b\" does not support thinking"}
```

HTTP status: **400 Bad Request**.

HA receives the 400, has no fallback, and the Voice PE gets no response — stuck on blue LED indefinitely.

### Contributing Factors

1. **Silent failure**: No HA error log entry, no notification, no UI indication. The Voice PE just sits on blue.
2. **k3s-vm-still-fawn NotReady**: Unrelated but complicated initial diagnosis — QEMU guest agent down, SSH unreachable, kubectl commands had to route through pumped-piglet.
3. **Stale kubeconfig**: Local `~/kubeconfig` was stale, adding another red herring.

### Why It Wasn't Caught Earlier

The "Think before responding" option was likely toggled during experimentation. The default is `false`. Since `qwen2.5:7b` never supported thinking, every voice request after the toggle was silently failing.

---

## Resolution

### Immediate Fix

1. Upgraded Ollama from `0.17.0` → `0.17.7` in `gitops/clusters/homelab/apps/ollama/deployment.yaml`
2. Created model update job to pull `qwen3.5:4b` (supports thinking natively)
3. Deleted old models: `qwen2.5:7b`, `qwen2.5:3b`, `gemma3:4b`
4. Updated HA Ollama conversation agent model to `qwen3.5:4b`

### Commit

```
4fec36f fix: upgrade Ollama to 0.17.7 and switch to qwen3.5:4b for thinking support
```

### Verification

```bash
# Ollama version
curl http://192.168.4.85/api/version
# {"version":"0.17.7"}

# Thinking works
curl http://192.168.4.85/api/chat -d '{"model":"qwen3.5:4b","messages":[{"role":"user","content":"what is 2+2"}],"stream":false,"think":true}'
# Thinking: "Analyze the Request..." → Response: "The answer to 2 + 2 is 4."

# Voice PE responds to "what's my notification"
```

---

## Lessons Learned

1. **400 ≠ model missing**: The fast response time (~44ms) was the clue — a missing model returns a proper error, but a parameter validation failure returns 400 almost instantly.
2. **Test think compatibility before enabling**: Not all models support `think`. Check with a direct curl before toggling in HA.
3. **Ollama version gates model availability**: `qwen3.5` requires Ollama ≥ 0.17.5. The 412 error on pull was clear but would have been missed in an automated job.
4. **Third Voice PE incident in 3 months**: Same symptom (blue LED, no response), different root cause each time. The voice pipeline has too many silent failure modes.

---

## Models After Resolution

| Model | Size | Thinking | Purpose |
|-------|------|----------|---------|
| qwen3.5:4b | 3.4 GB | Yes | HA Voice PE conversation agent |
| qwen3:4b | 2.5 GB | Yes | Backup / testing |

**Tags**: voice-pe, ollama, qwen, thinking, think-parameter, 400, http-400, voice-assistant, home-assistant, RTX-3070, qwen3.5, model-upgrade
