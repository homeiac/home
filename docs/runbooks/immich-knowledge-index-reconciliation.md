# Knowledge Index → Immich reconciliation (#217)

The PostgreSQL photo enrichment catalog is the source of enrichment. The worker reads
that catalog and calls the Immich API. It writes checkpoints and a durable queue in
its own `immich_sync` schema in `photo_enrichment`; it never writes Immich's database
or the read-only photo originals. DuckDB/Parquet remain in the existing ingestion
and analytics pipeline.

## Current promotion boundary

The owned Immich custom metadata key is `home.knowledge-index.v1`. It preserves
captions, model provenance, tags, location context, capture/GPS values, group context,
and prior face labels with their confirmation source. These are **preserved records**,
not native Immich descriptions, albums, tags or face assignments. Native caption,
GPS and date updates are gated; native face transfer is disabled.

Immich 3.4.2 can unlock EXIF fields after a failed XMP sidecar write on a read-only
external library. Later metadata extraction may replace native descriptions. The
user selected custom metadata preservation while normal captions remain gated.
A canary custom record survived an explicit UI metadata refresh; its native
caption/GPS/date remained unchanged. The disposable canary key was then removed.

## Scope and conflict handling

- Match the single owner/library named `Existing Google Photos`, then exact path
  under `Google Photos/Photos from YYYY/`, size, availability and path checksum.
- Immich 3.4.2 search needs `withExif: true`; its API has a library ID rather than an
  `isExternal` property. Its external checksum is SHA-1 of `path:` + absolute path,
  **not the image bytes**. Before writes the worker independently reads the original,
  verifies source size/mtime, and computes a content SHA-256.
- A changed source fingerprint queues an update; unchanged applied records are skipped.
- Write intent precedes the API update, and API readback precedes the applied checkpoint.
  Interrupted writes can be acknowledged without duplication.
- Edits/removal of the owned key after a successful sync become conflicts. Other
  metadata keys and all native fields remain untouched. Applied keys are rechecked
  periodically to detect later edits.
- Missing assets and non-year folders are reported, not imported automatically. A
  single worker advisory lock, bounded batches and backoff prevent competing writers.

## Operations

All workload/configuration changes go through this branch's Flux
`photo-enrichment-preview` Kustomization. The generated manifests are under
`gitops/clusters/homelab/apps/photo-enrichment/immich-sync/`.

```bash
# Read-only audit; outputs are private local files, never commit photo metadata.
python3 scripts/knowledge-index/immich-reconcile-audit.py --output /private/tmp/immich-reconciliation
python3 scripts/knowledge-index/check-immich-reconciliation.py
python3 scripts/knowledge-index/check-immich-observability.py

# Regenerate desired state, review, commit with #217, push, and reconcile Flux.
python3 scripts/knowledge-index/gen-immich-sync.py --mode dry-run
python3 scripts/knowledge-index/gen-immich-sync.py --mode apply
python3 scripts/knowledge-index/gen-photo-app-dashboard.py > gitops/clusters/homelab/apps/photo-enrichment/dashboard.yaml
python3 scripts/knowledge-index/gen-dashboard.py > gitops/clusters/homelab/apps/photo-enrichment/knowledge-index-dashboard.yaml
```

Dry-run discovers and records the queue but performs no Immich writes. Switching
back to dry-run pauses writes without erasing checkpoints or preserved records.
Do not remove the whole Kustomization to pause: it also owns the dashboards.

The API key and scoped role password are committed only as SOPS-encrypted Secrets.
Restore the existing age identity using `docs/runbooks/sops-age-key-recovery.md` if
needed; never generate a replacement age key. A plaintext Google Drive API-key
backup is not necessary. The existing encrypted Git copy is the durable backup.
The bootstrap Job is explicitly versioned because Kubernetes Job templates are
immutable; increment its name when changing bootstrap behavior.

## Observability and initial audit

Both value stream maps show the enrichment source, pending queue, preserved
custom records, errors/conflicts and unmatched records separately from thumbnail
and ML jobs. Photo App adds reconciliation time series, mode, discovery age,
oldest pending age, cycle duration and the explicit caption gate. Structured worker
logs carry event/reason codes and hashed source IDs rather than paths or names.

The 2026-11-20 read-only audit saw 118,987 source media, 13,320 successful summaries
in the PostgreSQL snapshot and 89,997 Immich assets. Of the source media, 86,209
matched by path/size, 10 imported-scope videos were missing, one size differed, and
32,767 were outside the year-folder import scope. 3,787 target assets had no source
match (including managed pilot assets). Of matched assets, 8,617 had a summary.
These are audit-time counts; source catalog snapshots can lag Parquet generation.
