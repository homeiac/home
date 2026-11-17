# Proposal

## Why
The knowledge index (#212) can say where every photo and video is and whether Google counts it against quota, but not what
is in it. Existing open-source tools caption photos (Immich add-ons, PhotoPrism) but none describes what happens in every
video of a library. A local vision model on the homelab GPU can fill that gap with no data leaving the house.

## What Changes
- New enricher that reads photos and videos read-only, asks a local vision-language model for a summary and tags, and writes
  them to the index's `media_summaries` table (reserved in Phase 1) as Parquet batches.
- Work queue is driven by SQL (`gphotos_to_summarize`): only media without a successful summary for their current bytes.
- A Kubernetes Job (Dockerfile image, Flux-managed) that takes the GPU from Frigate for the duration of a run, restores it, and is started automatically after an ingest brings new media; plus manual sample/start commands.
- Runbook section: operations, re-running with a new model or prompt, search examples.

## Capabilities

### New Capabilities
- `media-summaries`: model-generated summaries and tags for photos and videos, stored in the knowledge index and searchable by SQL.

### Modified Capabilities
(none: `openspec/specs/` is empty; the Phase 1 index is documented in `docs/runbooks/knowledge-index.md`)

## Impact
- New: `scripts/knowledge-index/enrichers/` (code + Dockerfile), `gitops/clusters/homelab/apps/media-summaries/` (Job template, RBAC, watchdog), trigger in the ingest, tests, runbook.
- Runs as a pod on the GPU node (RTX 3070, 8 GB); Frigate is stopped while a run is active and always restored; reads the photos dataset read-only; writes only to the index dataset.
  writes only to the index dataset.
- Depends on PR #214 (knowledge index Phase 1). No cloud calls, no secrets, no change to stored or deleted data.
- Out of scope: Immich integration, face recognition, embeddings/semantic search, Drive/OneDrive files.
