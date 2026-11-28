# Tune workloads sharing compute

Use this procedure for overlapping workloads through their own evidence adapters.
Cricket, indexing, transcription, face processing and services are examples, not
an allowlist or shared model/schema. The target's quality and whole-job objective
must improve while distinct peers retain their progress and service budgets.
Keep baseline workers and scheduled reservations protected.

This is an operating procedure, not a claim that a fleet-wide controller is
deployed. The cricket worker's local memory guard alone cannot enforce it.

## Establish the current workload mix

Before changing workers, record a timestamped resource-to-workload map from live
services, pods, model servers and queue/exporter observations. Repeat it at trial
boundaries and whenever a workload starts, stops, changes model or moves host.
Use `proxmox/inventory.txt` for host discovery and the existing read-only
[performance investigation procedure](../methodology/performance-diagnosis-runbook.md).
Check physical hosts as well as their guests and pods.

Include these consumers when present; this list is a starting point, not an
exhaustive allowlist:

| Workload | Useful progress, counted once | Resources to check |
| --- | --- | --- |
| Cricket | Unique source minutes analyzed and effective results committed; separately, results published | Decode CPU, inference slots, GPU/Metal, source storage, ledger and publication |
| Knowledge index | Expected document/asset versions committed and searchable | Embeddings/captions, inference slots, CPU, storage, database and publication |
| Life-stage/action | Validated scene revisions committed through the existing OpenLABEL writer | Vision inference, frame extraction, PostgreSQL and derived publication |
| Dog identification | Unique assets with durable decisions, including valid negatives | Detection/embedding CPU or Metal, memory, source storage and queue writer |
| Immich face processing | Submitted frames with completed detection and native face records read back | Upload/network, detection/recognition queues, ML device, database and storage |

Trace indirect sharing too: cricket and captions may use the same model server;
dog identification can use the same Metal device through a different process.
Separate servers do not imply separate GPU or unified-memory capacity. Include
scheduled ingestion, backups and other observed consumers of the same disks,
network, CPU or accelerator. Do not count a host, guest and pod as three pools.

For every affected workload record desired and active workers, runnable backlog,
arrival rate, oldest ready job age, durable completion rate, tail latency,
errors/retries, model/device, and telemetry timestamp. Verify actual placement.
Shared server counters cannot attribute progress to an individual client; use
its completion ledger or labelled metrics. Preserve minimum allocations and
scheduled-demand reservations in the trial record.

Distinguish idle, finished, unhealthy and unobserved workloads. Zero active
workers with pending work needs investigation. An empty dog queue does not prove
that its next scheduled batch has no reservation. Missing/stale knowledge-index
telemetry is not evidence that it is idle. If an affected workload cannot be
observed, retain the last proven allocation and hold capacity trials on that
shared resource. Unrelated pools may continue independently.

## Cover every plausible CPU and accelerator

Follow the [fleet discovery and completion gate](../methodology/distributed-ai-performance.md#discover-capacity-beyond-the-current-routes) before declaring capacity exhausted. Create a stage-by-pool table from physical inventory and local compute. Include still-fawn and other CPU hosts even when no model service is running. Keep CPU inference and preparation as separate candidates.

For each missing measurement, check runtime availability, model memory fit, input access and peer headroom, then run a bounded sample through the existing workload adapter where feasible. Measure useful completed output and quality on the reviewed cohort. Include cold startup separately from warmed performance. If model provisioning is required, use the established GitOps or host installation path and assign the next step. Record a deferral with an owner and revisit trigger when it cannot proceed.

Keep baseline workers running. A hold for an unobserved peer on the RTX pool applies to that pool's experiment. Independently check the CPU host's peers and shared dependencies before its canary. A failed image-size experiment closes that candidate and leaves other hardware candidates open.

## Define a trial before changing capacity

Record the target workload, frozen inputs, quality checks, all affected peers,
current allocation vector, proposed allocation vector, rollback vector, and
per-workload acceptance thresholds. Keep units separate: photos/minute and
searchable documents/minute cannot be added into a meaningful fleet rate.
Count retries, cache hits and repeated benchmark inputs separately from unique
production progress. Measure downstream readback, not just inference responses.

Use existing service budgets where available. Otherwise preregister these
conservative trial defaults before admitting extra work:

- Compare equal warmed windows of at least five minutes, with at least ten
  durable completions per continuously backlogged workload. Extend both windows
  to accommodate long jobs; if there is insufficient comparable work after
  fifteen minutes, label the comparison inconclusive and do not promote it.
- Each peer must retain at least 90% of its comparable baseline useful rate and
  stay within its latency/error budget. If none exists, allow at most a 10%
  increase in p95 latency and no increase in terminal-error rate. Record input
  size/difficulty buckets so a different job mix is not mistaken for contention.
- Require every backlogged peer to keep making progress. Predeclare a no-progress
  timeout using its normal job duration and lease/deadline; a service being
  active or answering health checks does not establish useful progress.
- Sample resource and peer health at least every 15 seconds. Record telemetry
  freshness limits from exporter cadence. Missing samples invalidate promotion;
  restore the last proven allocation if observation is lost during a trial.

These defaults are trial gates, not measured service guarantees. Record tighter
existing limits and any justified replacement before starting. If a baseline
already fails its budgets, resolve or explicitly account for that condition
before testing additional pressure.

## Make one objective determine whether to proceed

For finite work, freeze one remaining-work snapshot and use
`completion_objective.py OBJECTIVE --at-ns CUTOFF` to compute both combined
production rates and projected remaining times. The object is also consumed by
`workload.py qualify-capacity`; dashboards display that same result instead of a
second calculator. Require actual verified contribution from an added backend.
Replays stay separate, and checkpoint-only projections remain diagnostic when
canonical readback is missing. An unverified speedup or peer-budget pass cannot
promote. Services use their measured SLO objective instead of backfill ETA.

Use the [adapter contract](../reference/workload-adapter-contract.md) for declarative
observers, source-version deduplication, native readback and saved execution
provenance. OpenLABEL remains the media authority. Nonmedia keeps its existing
schema and native store; performance receipts do not become another content store.
The offline qualification command always reports `not_admitted`/`proceed=false`
until ordered phase/repetition and live lease/dispatch gates are implemented.

## Start at the shared ceiling, then reduce

Once the implementation and quality approach are qualified, start at the highest
concurrency supported by measured capacity **after** all peer reservations. A
four-slot server is one four-slot pool, not four slots per indexer. Derive the
ceiling from the tightest constraint across slots, GPU/host memory, CPU/decode,
storage, database and downstream queues. Keep headroom for live service demand.
An unmeasured backend needs a readiness check before a capacity sweep.

Change one workload's allocation on one shared pool at a time. Use one operator
or controller owner for that pool so independent indexers cannot simultaneously
claim the same spare capacity. Record ownership and the experiment end time;
expiry or restart restores the last proven settings. Preserve all peer baseline
allocations; reduce only the workload being tuned. Never pause knowledge indexing
or dog identification to make cricket's benchmark look better.

Sweep downward from that ceiling. For example, test four, then two cricket
requests only if four is the available shared allowance, not merely cricket's
configured hard bound. Change frame-upload/decode concurrency separately from
inference; submitted frames can leave a growing Immich queue after upload ends.

Drain the target's additional requests immediately on OOM/allocation failures,
new service unavailability, missed no-progress deadlines or sustained resource
pressure. Step down when a warmed comparison breaches any peer budget or target
throughput plateaus. Respect leases and finish in-flight work; preserve corrections
and committed outputs. Verify peer recovery before the next trial. If conditions
do not recover, investigate rather than attributing every failure to the trial.

Retain adjacent baseline/trial/recovery controls. A no-increment control that also
slows means the single trial cannot establish causation. Predeclare additional
controls/repeats; do not keep retrying until one passes or use the slowest control
as a convenient new anchor. Use actual sampled bounds rather than process wall
time. Capture profile/mode/input difficulty and retained-stage reuse to assess
comparability, and leave hardware cause unknown without stage/device evidence.

Repeat eligible candidates on matched inputs in reverse order. Select the fewest
workers within 5% of the fastest reproducible useful target rate that passes
**every** peer gate and the quality checks. A 30% cricket gain with a 20% knowledge
index regression fails under the default peer budget. A target gain with missing
peer measurements is inconclusive, never a win.

If a peer becomes busy, a scheduled job starts, or another controller changes
capacity, mark the comparison as a changed environment and reacquire a baseline
for that workload mix. Do not pool it with the prior comparison. Continue existing
production; back down the trial allocation if shared headroom is no longer proven.

## Retain evidence and revisit decisions

Journal UTC times, workload mix, observed callers, physical resource graph,
before/trial/after allocations, per-workload rates and queue ages, quality,
latency/errors, pressure, failed settings, and observed recovery. Keep private
inputs and credentials outside Git. Use bounded workload/stage/backend labels in
metrics; retain detailed provenance in the private experiment record.

Preserve selected, rejected, partial and unmeasured settings separately. If the user
requests consolidation, report best supported measured configuration, not a global
optimum. Persist private raw evidence with verified manifests/permissions; keep
aggregate science-journal conclusions and source references in Git.

Persist the winning allocation with the workload mix, model and policy versions.
Requalify it after a workload returns or changes placement. Capacity measured for
dog identification plus knowledge indexing does not automatically qualify cricket
plus knowledge indexing, even on the same machine.
