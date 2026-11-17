## Context
Phase 1 (#214) reserved `media_summaries` (schema in `scripts/knowledge-index/kidx.py`, views in `knowledge.sql`). The GPU is the RTX 3070
(8 GB) in the pumped-piglet GPU VM, shared with the Frigate ONNX detector (nvidia.com/gpu: 1). Photos live on a ZFS dataset on the Proxmox
host; the K3s VM 105 must never do bulk writes. Research (2026-11-16): photo captioners exist for Immich/PhotoPrism; no tool describes
every video of a library.

## Goals / Non-Goals
- Goals: summaries + tags for all photos and videos, searchable in SQL; restartable; polite to Frigate; no cloud.
- Non-Goals: Immich integration, face recognition, embeddings, Drive/OneDrive media, a web UI.

## Decisions
1. **Runner placement:** the script runs on the Proxmox host (reads the photos dataset directly, writes batches to the index dataset); only the model server runs in the GPU VM and is reached over the LAN. Rejected: runner in the GPU VM (needs the dataset mounted there).
2. **Model API:** an OpenAI-compatible vision endpoint (Ollama or llama.cpp server) with Qwen2.5-VL 3B first, 7B Q4 if VRAM allows. The enricher
   stays model-agnostic; the model name is part of the enricher id (e.g. `qwen25vl-3b-p1`). vLLM native video input is deferred: too large for 8 GB.
3. **Photos:** resize to long edge 1024, one image plus a context prompt, JSON answer `{summary, tags}`.
4. **Video:** `ffmpeg` samples N frames (start 8, uniform or scene-based, capped by duration) at reduced resolution; `faster-whisper` small model
   transcribes speech; one prompt with frames + transcript + context. Record `frames_sampled`, `duration_s`.
5. **GPU politeness:** `nvidia-smi` free-memory check before load; systemd unit with Nice and idle I/O; batches of ~200 files.
6. **Idempotence:** Parquet per batch via tmp + rename (same pattern as `adapters/gphotos.py`); views pick the latest row.
7. **Context in prompts** comes from the existing views (`gphotos_media`: taken_ts, has_geo, album, people).

## Risks / Trade-offs
- 8 GB shared with Frigate may not fit even a 3B model plus frames: measure first; fallbacks are a smaller model (moondream, MiniCPM-V) or running only when
  Frigate is idle.
- Quality of 8-frame video summaries is unproven: pilot on ~20 videos and ~50 photos before the full run.
- Model hallucination: summaries are labelled with model and prompt version; never used to delete anything.
