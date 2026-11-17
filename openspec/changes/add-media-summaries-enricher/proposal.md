# Proposal

## Why
The knowledge index (#212) can say where every photo and video is and whether Google counts it against quota, but not what
is in it. Existing open-source tools caption photos (Immich add-ons, PhotoPrism) but none describes what happens in every
video of a library. A local vision model on the homelab GPU can fill that gap with no data leaving the house.

## What Changes
- New enricher that reads photos and videos read-only, asks a local vision-language model for a summary and tags, and writes
  them to the index's `media_summaries` table (reserved in Phase 1) as Parquet batches.
- Work queue is driven by SQL (`gphotos_to_summarize`): only media without a successful summary for their current bytes.
- Control commands to sample, start, stop and watch a run; runs share the GPU politely with Frigate.
- Runbook section: operations, re-running with a new model or prompt, search examples.

## Capabilities

### New Capabilities
- `media-summaries`: model-generated summaries and tags for photos and videos, stored in the knowledge index and searchable by SQL.

### Modified Capabilities
(none: `openspec/specs/` is empty; the Phase 1 index is documented in `docs/runbooks/knowledge-index.md`)

## Impact
- New: `scripts/knowledge-index/enrichers/`, enrich commands in `knowledge-index-ctl.sh`, tests, runbook section.
- Runs on the GPU VM of the pumped-piglet host (RTX 3070, 8 GB, shared with the Frigate ONNX detector); reads the photos dataset read-only;
  writes only to the index dataset.
- Depends on PR #214 (knowledge index Phase 1). No cloud calls, no secrets, no change to stored or deleted data.
- Out of scope: Immich integration, face recognition, embeddings/semantic search, Drive/OneDrive files.
