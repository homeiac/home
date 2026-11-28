# Cricket analysis telemetry

This opt-in adapter joins the existing [shared-workload journey](../guides/shared-workload-agent.md).
It records real SDK spans in a private durable journal and exports immutable
captures accepted by the common reviewer. It does not change worker counts.
Analysis success is not publication: verified counters require the durable
[publication receipts](cricket-publication.md). A capture alone cannot qualify a trial.

Install `scripts/knowledge-index/cricket/requirements-telemetry.txt` into the
worker environment. From the repository root, create a fresh private session:

```bash
python3 scripts/perf/workload.py start \
  --session /private/run-directory/session.json \
  --workload cricket-indexer --run-id UNIQUE_COMPARISON_ID --output-kind media \
  --resource mac-m5/bonsai-slots \
  --stage ingest --stage load-evidence --stage analyze \
  --stage classify --stage reconcile --stage publish --stage verify --live
```

Declare every pool used by this worker with another `--resource`. Add the matching
`resource` field to each backend in its private policy. Pass
`--telemetry-session /private/run-directory/session.json` to the existing cricket
worker command. Keep the existing authoritative ledger/evidence/state paths.
The session must reside on the actual worker host. No deployment or trial is
authorized merely by this intake; use the playbook's prerequisites and owner.

The adapter fences changes to the session, actual host, model, source allowlist,
analysis version, endpoint and configured ceiling. Desired worker counts may vary
within the same comparison, but allocation authorization belongs to the supervisor.
Use a new comparison/session for changed fixed inputs. Allocation phases retain
the comparison run identity; separate captures or a new run ID do not establish
fresh inference. Repetitions need their own evaluation receipts. Do not
reuse the earlier P01 intake, which lacks the required `analyze` stage.

From `scripts/knowledge-index` on that same host, close a capture into a new path:

```bash
python3 -m cricket.telemetry \
  --session /private/run-directory/session.json \
  --output /private/run-directory/closed-baseline \
  --publication-ledger /private/cricket/ledger.sqlite3 \
  --schema /private/openlabel-1.0.0.json
```

Run `scripts/perf/workload.py review --session
/private/run-directory/closed-baseline/session.json` from the repository root.
Read its decision; exit status zero does not imply eligibility. Supply the
publisher’s reference/readback bundle and pinned schema to review media output.
Missing peer observations or trial registration must still produce a hold.

The exporter includes only completed spans received by the cutoff and writes the
watermark last before publishing the directory. Captures refuse overwrites.
The journal survives restart. An exporter failure leaves a persistent failure
marker and blocks captures; repair storage and start a fresh session rather than
deleting the marker to make incomplete evidence look complete. Model error text,
prompts and credentials are excluded. Private source IDs remain trace attributes,
never metric labels. Remote request latency is not reported as GPU compute time.

`--publication-ledger` and `--schema` are optional as a pair. Without them, an
analysis-only journal has zero verified output. With them, receipt import opens
the ledger read-only, revalidates saved SQL readbacks and checks run/host/resource
identity. Only the original durable source completion contributes, at stage
`verify`; later correction revisions and repeat-run references do not add another
production item. Receipts from a publisher without host telemetry are not eligible.

The journal binds the receipt source and preserves each receipt's first observed
time. Import before closing the current cutoff. Late imports cannot alter an
already closed historical window, even if the database commit happened earlier.
Restart/repeated import preserve the count; changing an imported receipt is refused.
For timed windows, run receipt import at each sampling boundary. Repeated frozen-
cohort evaluation still needs its separate phase receipt contract; these are
production completions only.

Each worker execution now has a private `cricket.execution_id` on its `analyze`
span and fresh `classify` children. A fresh model call records the source ID,
fingerprint/version, window index and expected count, start/end seconds, analysis
configuration digest and preparation cache digest. These fields stay in the
private trace journal and never enter metric labels. They do not change model
prompts, answer-cache keys or production completion accounting.

Cached windows produce no new classify span. A retry has a different execution ID,
so a successful retry with one new window and one cached window cannot appear to
be two freshly inferred windows in that execution. Failed spans retain the SDK
error status without copying the exception text. Consumers must handle the actual
OTLP enum encoding, including `STATUS_CODE_ERROR`.

This is evidence collection, not yet an evaluation receipt. The remaining verifier
must join every expected frozen window to successful inference, reject reused or
late evidence, and bind it to independently read-back OpenLABEL completion and
quality evaluation. Aggregate `fresh_inference_items` claims alone remain
insufficient to admit a capacity trial.

Other media evaluation callers can reuse the durable SDK journal only with an
explicit matching workload, for example
`RunTelemetry(session, workload="library-face-observations-evaluation")`. The
default still requires Cricket. A mismatched or invalid caller is rejected before
journal creation. Evaluation spans use `evaluation.*` names and the actual session
service identity/headers; they must not masquerade as Cricket production. Private
per-window provenance retains the legacy `cricket.*` trace attribute names.

An evaluation caller cannot import Cricket production receipts. Its captures have
zero production verified items until its own independently checked evidence path
is implemented. Keep frozen fresh-inference evaluations distinct from new unique
library outputs, even when their OpenLABEL readbacks are valid.
