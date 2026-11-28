# Cricket publication and independent readback

The opt-in publisher uses the existing life-stage OpenLABEL writer and canonical
PostgreSQL scene table. It adds an outbox and distinct-source receipt table to the
operational SQLite ledger after an online backup. It does not reset analysis jobs
or corrections, change worker counts, or start an album-wide run.

A source is eligible only when its requested analysis version is complete, the
completion checkpoint retains its source fingerprint, and every sampled frame has
completed native face detection. The new worker preserves that fingerprint and
trace context on completion. Historical checkpoints without the fingerprint are
rejected; do not fill this field by assumption or replace the live ledger with a
bootstrap copy. A reviewed migration or explicitly scoped reanalysis is separate.

From `scripts/knowledge-index` in the worker environment, using the existing
private libpq connection configuration:

```bash
python3 -m cricket.publication \
  --ledger /private/cricket/ledger.sqlite3 \
  --evidence /private/cricket/evidence \
  --shared-module /path/to/checkout/scripts/knowledge-index/memory-acceptance \
  --schema /private/openlabel-1.0.0.json \
  --owner OWNER_UUID --album ALBUM_UUID --asset ASSET_UUID \
  --version ANALYSIS_VERSION --run-id SHARED_RUN_ID \
  --backend mac-m5/bonsai-slots \
  --telemetry-session /private/run-directory/session.json \
  --output /private/run-directory/publication-bundle
```

The telemetry session must declare `publish` and `verify` in addition to the
[analysis stages](cricket-telemetry.md). Existing analysis trace context must
belong to this run. The publisher opens separate write/read connections and uses
read-only SQL for readback. A committed scene earns a durable receipt only after
the independent checker validates its exact revision, digest and typed completion
reference. It records one production completion per source fingerprint and
analysis version/digest across retries, corrections and runs. Occurrence references
and unique source counts remain separate.

From the repository root, verify the exported bundle:

```bash
python3 scripts/perf/workload.py verify-media \
  --session /private/run-directory/session.json \
  --references /private/run-directory/publication-bundle/media-observations.jsonl \
  --readback /private/run-directory/publication-bundle/scene-readback.jsonl \
  --schema /private/openlabel-1.0.0.json
```

The export contains saved independent SQL readbacks, not producer-side substitutes.
Its final `publication-summary.json` marks bundle completion. A partial bundle is
incomplete; retry the export to a new path. Saved historical receipts remain
append-only, but an export omits snapshots invalidated by local edits or new inputs.
The production counter is historical completed work, not a count of currently
unchanged annotations. The [telemetry capture command](cricket-telemetry.md) imports these receipts into
OTLP counters. Automatic worker publication dispatch remains an integration gate.

The publisher holds a ledger write transaction across each source's SQL write and
readback to prevent a concurrent correction from being overwritten. PostgreSQL
statements and connection setup have timeouts; publication is deliberately one
source at a time. A correction waiting on this transaction may need to retry if
the database is slow. UI retry behavior belongs to the review integration gate.

A crash after the SQL commit leaves a recoverable intent. Retrying the same intent
uses the writer's digest deduplication, then obtains a new independent readback.
Attempts are persisted before contacting PostgreSQL and bounded at three. Changed
inputs, conflicting producers and invalid readbacks require review; they never
earn a receipt. A corrected source gets a new intent. Errors record exception types,
not potentially sensitive database messages. Do not reset attempts automatically
or restore an old ledger over newer corrections.
