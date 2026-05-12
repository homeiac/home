# Ollama Service Guide

Client-side guide for consuming the in-cluster Ollama service. For deployment
tuning see `ollama-gpu-server.md` and `docs/source/md/guides/ollama-gpu-optimization-guide.md`.

## Endpoint

| Field    | Value                                                          |
|----------|----------------------------------------------------------------|
| Service  | `ollama-lb` in namespace `ollama` (type `LoadBalancer`)        |
| URL      | `http://192.168.4.85` (port 80 → container 11434)              |
| Ingress  | `ollama.app.homelab` (legacy host; prefer the LB IP)           |
| Auth     | none — LAN-only, no internet exposure                          |
| Manifest | `gitops/clusters/homelab/apps/ollama/service.yaml`             |

The LB IP is reachable from any host on `192.168.4.0/24`. From off-LAN, use
Tailscale.

## Deployment summary

FluxCD manages the deployment under `gitops/clusters/homelab/apps/ollama/`.
The pod runs on a node labeled `nvidia.com/gpu.present=true`
(RTX 3070 on `pumped-piglet`) with `runtimeClassName: nvidia`. Relevant caps
set in `deployment.yaml`:

- `OLLAMA_MAX_LOADED_MODELS=1` — one model resident at a time
- `OLLAMA_NUM_PARALLEL=1` — one concurrent request
- `OLLAMA_FLASH_ATTENTION=true`
- Default keep-alive: 5 minutes (see `expires_at` in `/api/ps`)

Changes go through git → Flux. Manual `kubectl apply` is reverted within ~1 min.

## Available models

Re-check with:

```bash
curl -s http://192.168.4.85/api/tags | jq -r '.models[].name'
```

As of last verification (2026-05-12): `gemma4:e2b` (5.1B Q4_K_M, 7.2 GB),
`qwen3.5:4b` (4.7B Q4_K_M, 3.4 GB), `qwen3:4b` (4.0B Q4_K_M, 2.5 GB).

To add a model, prefer the `job-model-update.yaml` GitOps Job; ad-hoc pulls via
`kubectl exec deployment/ollama-gpu -- ollama pull <model>` won't survive a pod
restart of the PVC-backed model dir without GitOps reconciliation.

## Calling the API

List models:

```bash
curl -s http://192.168.4.85/api/tags | jq
```

What's loaded right now (and when it will be evicted):

```bash
curl -s http://192.168.4.85/api/ps | jq
```

Chat (non-streaming):

```bash
curl -s http://192.168.4.85/api/chat -d '{
  "model": "qwen3:4b",
  "messages": [{"role":"user","content":"Say PONG."}],
  "stream": false,
  "think": false,
  "options": {"num_predict": 64}
}' | jq -r '.message.content'
```

Generate (single-shot completion):

```bash
curl -s http://192.168.4.85/api/generate -d '{
  "model": "qwen3:4b",
  "prompt": "Reply with PONG.",
  "stream": false,
  "think": false,
  "options": {"num_predict": 64}
}' | jq -r '.response'
```

OpenAI-compatible endpoint (same host, `/v1/...`):

```bash
curl -s http://192.168.4.85/v1/chat/completions -d '{
  "model": "qwen3:4b",
  "messages": [{"role":"user","content":"Say PONG."}]
}' | jq -r '.choices[0].message.content'
```

## Performance notes (measured, not folklore)

- Cold load of a 4B Q4 model: ~9 s (`load_duration` ≈ 9.2 s in `/api/generate`).
- Warm `/api/chat` against `qwen3:4b`: ~17 ms/token (`eval_duration / eval_count`).
- Default `num_predict` in the API is small. A response ending with
  `"done_reason":"length"` is truncated, not a model failure — raise
  `options.num_predict`.

## Gotchas (sourced from incidents in this repo)

- **`qwen3` thinks by default.** Clients that don't strip `<think>` blocks, or
  that hit a small `num_predict`, will appear to "fail" mid-thought. Pass
  `"think": false` unless you actually want reasoning. RCA:
  `docs/rca/2026-03-06-voice-pe-ollama-think-400.md`.
- **One model at a time.** With `OLLAMA_MAX_LOADED_MODELS=1`, the first call to
  a different model evicts the loaded one and reloads (~5–10 s for a 4B Q4).
  Pin one workload to one model.
- **Pinned image.** Deployment uses `ollama/ollama:0.20.2` on purpose; don't
  bump to `latest`. Model pulls are a separate concern handled by
  `job-model-update.yaml`.
- **Ingress hostname is legacy.** `ollama.app.homelab` is from the pre-Traefik
  wildcard era — use the LB IP unless you've also set up the homelab DNS.

## Status / health check

```bash
KUBECONFIG=~/kubeconfig scripts/ollama/check-ollama.sh
```

Without a kubeconfig you still get the API-level signals via the curl commands
above:

1. `curl http://192.168.4.85/api/version` — alive check.
2. `curl http://192.168.4.85/api/ps` — confirms a model is resident, shows
   `size_vram` and `expires_at`.

## Runbooks and prior incidents

- `docs/source/md/troubleshooting/ollama-troubleshooting-runbook.md`
- `docs/source/md/troubleshooting/ollama-high-cpu-usage-rca.md`
- `docs/source/md/guides/ollama-gpu-optimization-guide.md`
- `docs/runbooks/voice-pe-ollama-diagnosis-runbook.md`
- `docs/rca/2026-03-06-voice-pe-ollama-think-400.md`
- `docs/rca/2026-02-23-ollama-voice-pe-slow-response.md`
