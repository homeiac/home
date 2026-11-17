## Context
Phase 1 (#214) reserved `media_summaries` (schema in `scripts/knowledge-index/kidx.py`, views in `knowledge.sql`). The GPU is the RTX 3070 (8 GB)
on K3s node `k3s-vm-pumped-piglet-gpu`, requested as `nvidia.com/gpu: 1` by Frigate (`gitops/clusters/homelab/apps/frigate/deployment.yaml`); an
`ollama-gpu` Deployment (`apps/ollama`) also requests one GPU. Photos live in a ZFS dataset on the Proxmox host, ingested there by
`gphotos-ingest-host.sh`. K3s VM 105 must never do bulk writes. Research (2026-11-16): photo captioners exist for Immich/PhotoPrism; no tool
describes every video of a library.

User decisions: Frigate may be stopped while analysis runs; the switch must be automatic when new photos arrive (rare); the enricher is a pod built from a Dockerfile.

## Goals / Non-Goals
- Goals: summaries + tags for all photos and videos, searchable in SQL; restartable; automatic; Frigate always restored; no cloud; GitOps-managed.
- Non-Goals: Immich integration, face recognition, embeddings, Drive/OneDrive media, a web UI.

## Decisions
1. **Packaging:** a container image (Dockerfile in `scripts/knowledge-index/enrichers/`, python + ffmpeg + duckdb + faster-whisper, pinned versions, no `latest`) run as a
   Kubernetes **Job** (Flux-managed template, one run per trigger). It carries `media_summary.py` as-is; the model server is a sidecar/second container (Ollama,
   Qwen2.5-VL) or the existing `ollama-gpu` Deployment if that one can hold the GPU instead of Frigate (to verify: node, GPU count/time-slicing).
2. **GPU handoff (Frigate down only while running):** the Job's controller step (a small `handoff` entrypoint in the same image, with a ServiceAccount allowed to patch
   `deployment/frigate` and nothing else) does: annotate Frigate `kustomize.toolkit.fluxcd.io/reconcile: disabled` (so Flux does not revert the scale-down, and Git is
   untouched) -> scale to 0 and wait for the GPU to free -> run the enricher -> scale to 1, remove the annotation. Restore runs in a `finally` AND a separate watchdog CronJob
   (every few minutes: if Frigate is scaled down by this mechanism and no enrich Job is active, or a max-duration deadline passed, restore it). Max run duration default 2 h,
   then resume at the next trigger.
3. **Automatic trigger:** `gphotos-ingest-host.sh` already calls `index-unit.sh` per archive. After a successful index the host checks the queue
   (`kidx.py query ... gphotos_to_summarize(...)`); if non-empty it creates the Job from the Flux template (`kubectl create job --from=cronjob/media-summaries` via `qm guest exec`,
   the repo's existing mechanism for kubectl on the host, no kubeconfig on the host). A suspended CronJob used as a template gives GitOps-owned config and an on-demand `--from` trigger.
   A concurrency guard (one active Job; `concurrencyPolicy`/lock) prevents double runs. Manual start/sample stays available.
4. **Data access:** the pod needs the photos dataset (read-only) and the index dataset (read-write, small Parquet files). Both live on the Proxmox host's ZFS pools; options:
   NFS export from the host to the GPU VM (preferred; read-only for photos), or virtiofs. Decide in task 1.2; never bulk-write inside VM 105.
5. **Model API and prompts:** unchanged: OpenAI-compatible endpoint, Qwen2.5-VL 3B first (7B Q4 if it fits once Frigate is down: the whole 8 GB is available during a run, so
   7B Q4 or larger context is realistic), photo = 1 image, video = up to 8 frames + optional Whisper transcript, context from `gphotos_media`.
6. **Idempotence:** Parquet per batch via tmp + rename; views pick the latest row; enricher id encodes model + prompt version.

## Risks / Trade-offs
- Frigate is blind (no detection/recording) while a run is active. Accepted by the user; mitigated by the time limit, the watchdog, and rare triggers. The first backfill
  (~119k items) will take hours-days: run it in bounded windows (e.g. nights) rather than continuously; the trigger/window policy is a task.
- RBAC: the Job's ServiceAccount can scale Frigate; scope it to that one Deployment (resourceNames).
- Flux per-object `reconcile: disabled` annotation must be removed on restore, or Frigate drifts un-managed: the watchdog also checks for a stale annotation.
- Quality of 8-frame video summaries is unproven: pilot on ~20 videos and ~50 photos before any bulk run.
- Model hallucination: summaries are labelled with model and prompt version; never used to delete anything.
