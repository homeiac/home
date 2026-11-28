# Cricket shared-workload implementation plan

Date: 2026-11-27 (America/Los_Angeles). Tracking issue: [#250](https://github.com/homeiac/home/issues/250).

Implement the remaining cricket integration using the existing
[distributed AI playbook](../methodology/distributed-ai-performance.md).
This plan is based on master commit
[`b4a19672`](https://github.com/homeiac/home/tree/b4a19672cd37301206a5487c8f2e192c34f75bb7),
including the [media publication contract](../architecture/media-workload-contract.md),
[telemetry contract](../reference/workload-telemetry.md) and
[shared-indexer tuning policy](../runbooks/shared-indexer-tuning.md).

Read with the [design](../architecture/cricket-shared-workload-design.md) and
[completion and verification checklist](cricket-shared-workload-checklist.md).
The checklist is the current status authority. The
[original feature plan](adil-cricket-highlights.md) retains the product requirements
and historical PR sequence; this document defines the remaining integration order.

## Outcomes and boundaries

1. The user can find and correct Adil's batting, bowling, boundaries and dismissals,
   including distinguishing an attempted run-out from an actual dismissal. Long
   highlights include the lead-in and full original playback remains available.
2. Cricket uses the life-stage OpenLABEL model and native Immich face IDs. Age,
   timestamped coordinates and nearby kit evidence support identity without
   converting an assumption into a recognition result. Corrections survive reruns
   and become searchable through verified publication.
3. Cricket can use measured spare capacity while Knowledge Index and other users
   of the same resources retain their baseline service and progress. Every promoted
   setting has peer measurements, quality evidence and a tested recovery path.

The scope is cricket's adoption of the common framework and the shared extensions
needed for that adoption. Reuse the existing CLI, checker, scene writer, observability
stack and supervisors. General replacement of all workload controllers is outside
this plan. Best-effort recognition remains acceptable; missing faces, uncertain
outcomes and pending processing must remain distinguishable and correctable.

## Starting point

| Evidence at the pinned revision | Consequence for implementation |
| --- | --- |
| PRs [#270](https://github.com/homeiac/home/pull/270), [#271](https://github.com/homeiac/home/pull/271) and the master integration [#273](https://github.com/homeiac/home/pull/273) are merged | Reuse their policy and OpenLABEL adapter; do not recreate them |
| The broader feature stack through [#269](https://github.com/homeiac/home/pull/269) remains open | Reconcile its worker/UI/deployment dependencies onto master before wiring the live pipeline |
| `verify-cricket-publication.sh` exercises the real writer and a disposable PostgreSQL database | Local publication can be verified; this is not production publication evidence |
| The historical journal records 633 videos and 867 photos analyzed | Do not reset the live ledger or count this as a new peer-qualified backfill |
| The native pilot retained five face IDs from photos; video-face recall was not established | Qualify extraction and face coverage before another album-wide pass |
| The observer exposes partial activity; the CLI emits decisions but does not actuate | Complete caller/peer evidence and connect decisions to the owning supervisor |
| Diagnosis seals two intervention types; the existing caption controller adds one lane | Add an explicit bounded concurrency trial; neither currently implements cricket's descending sweep |

## Small PR sequence

The identifiers P01–P10 are planning IDs, not GitHub PR numbers. P01 is a
reconciliation milestone across the existing small PRs; do not import the entire
stack in one new PR. P02–P10 are intended small PR boundaries; split a cross-service
adapter into separately reviewed sub-PRs if needed, retaining the parent gate.
Each PR records its actual URL and source revision in the checklist. Keep production dispatch
disabled for new paths until their own gate passes. Each PR must be independently
reviewable and include the focused verification below.

### P01 — Reconcile the feature stack and freeze acceptance cases

**Depends on:** the pinned master foundation. **Owner:** cricket integration.

Reconcile the required worker, correction API/UI, reanalysis and deployment modules
from the open stack onto current master through their existing individual PRs.
Record merge and regression evidence for each dependency. Resolve overlap with #273 explicitly;
preserve its PostgreSQL test and shared checker. Record the current deployed
release, authoritative ledger, policy and rollback release read-only. Freeze a
private reviewed cohort containing true/attempted run-outs, batting boundaries,
bowling wickets, helmets, other players, no-event scenes and long videos.

**Verify:** existing correction, full-playback, retry and source-fencing tests;
clean deployment manifest with immutable source hashes; no production mutation.
The cohort manifest names expected facts and uncertain cases without requiring
perfect automatic recognition. Record stage-specific quality thresholds before
live tuning. Do not silently turn the historical four-worker setting into a new
reservation.

### P02 — Add run identity and closed telemetry exports

**Depends on:** P01. **Owner:** cricket worker/telemetry adapter.

Create a private `workload.py start --output-kind media` session per comparison.
Its baseline prediction and intended trial share a run ID; record phase allocation
revisions separately and exclude only the declared knob from the fixed environment
fingerprint. New cohorts/models or unrelated configuration changes require a new
comparison. Carry trace context through queue claims, retries and publication.
Instrument ingest, fetch/decode, classify, publish and verify with declared stage
IDs. Export closed OTLP files and a watermark atomically. Include caller identity
at the shared serving boundary and filter metric labels to the common allowlist.

**Verify:** real SDK encoding, async parent/link propagation, fresh attempt spans,
single-host diagnostic slices, restart-safe exports, and rejection of leaked or
undeclared labels. Do not increment `workload.verified` on a model response; wire
its durable completion boundary in P03.

### P03 — Publish manifests and independently verify saved scenes

**Depends on:** P01–P02. **Owner:** cricket publisher.

Extend the existing adapter with a resumable publication/outbox record, private run
references, independent PostgreSQL readback and a durable verification receipt.
Represent successful no-event analysis with an explicit typed completion context
in a versioned vocabulary release, retaining checker compatibility for older scenes.
Keep pending face detection separate. Deduplicate verified items by source version
and analysis version, including retries across runs. Preserve event occurrence IDs
through corrections; never overwrite another producer's scene.

**Verify:** real PostgreSQL tests for initial publish, correction, dismissal,
identical retry, changed source, crash between commit and receipt, duplicate
readback/reference, wrong run, dangling relation and valid no-event output.
`workload.py verify-media` must pass independently exported rows. A validated local
JSON scene alone cannot satisfy this task. Count source completions separately
from face/action references and from analyzed source minutes.

### P04 — Produce complete resource and peer measurements

**Depends on:** P02; P03 for cricket verified progress. **Owner:** shared telemetry
with each affected workload's adapter.

Expand serving pool → physical device → observed callers, including direct Metal
users and scheduled demand. Add measured CPU/decode, storage and database routes
when the changed knob uses them. Capture equal-window verified progress, cohort,
quality, p95, terminal errors, baseline allocation and freshness for each peer.
Reuse existing Knowledge Index and Waffles exports where sufficient; fill their
gaps rather than infer peer quality from cricket. Define explicit service budgets
for non-indexing peers such as Frigate before admitting work on their device.

**Verify:** active/idle/stale distinction, unregistered caller discovery, returning
scheduled peer, physical resource deduplication, changed caller mix and a faster
cricket run with a losing peer. Missing peer evidence must hold the trial. Do not
invent durable completion counts for service-only peers; an explicit common
contract extension is required if they need different admission fields.

### P05 — Register bounded maximum-first concurrency experiments

**Depends on:** P02–P04. **Owner:** common review contract.

Add a supported pre-change concurrency experiment registration path to the shared
CLI. Seal the measured ceiling, peer reservations, allocation/rollback vectors,
fixed inputs, quality criteria, sample minimum, deadlines and descending sweep
order. Preserve the existing diagnosis rules and strict review gates. Match the
candidate action, configuration and cutoff to the sealed record during review.

**Verify:** a genuine descending sweep can be reviewed; changing its ceiling,
target pool, reservations, policy, action or baseline invalidates the receipt.
Queue-index or GPU-isolation receipts cannot authorize a concurrency change.
Missing, stale or incomparable evidence holds; demonstrated regression rolls back.
No command in this PR changes production capacity.

### P06 — Connect review decisions to the cricket supervisor

**Depends on:** P04–P05. **Owner:** cricket supervisor; shared pool coordination.

Add an exclusive, expiring trial ownership record for the affected pool and
persist the baseline, candidate and last proven allocation. Start at the measured
shared ceiling, reduce only cricket's extra dispatch, and leave peer baselines
running. Apply `hold`, `rollback` and `eligible` correctly; eligibility still
requires repeated owner checks. Drain on pressure, missed progress deadlines,
telemetry loss or ownership expiry. Record requested and observed allocations.

**Verify:** competing owners cannot allocate the same headroom; stale owners cannot
promote; restart/lease expiry restores proven dispatch; in-flight work and user
corrections survive; rollback restores peer progress. A successful CLI exit must
not be interpreted as approval. Tune upload/decode and inference separately.

### P07 — Qualify identity and event evidence on reviewed media

**Depends on:** P01–P03; P04–P06 before live capacity experiments. **Owner:** cricket
evidence/model pipeline and review UI.

Resolve the pilot's rejected per-event coordinates and unproven video-face recall.
Evaluate better frame selection/resolution without full-album reprocessing.
Retain every native detection's face ID, distinguish person assignment from face
occurrence, and use age/kit/continuity as bounded support. Show exactly which
person, role, result and time interval each correction changes. Preserve the
batting assumption as an editable assertion and require separate bowling identity
evidence. Keep attempted run-out and continued-play evidence out of dismissal
filters.

**Verify:** reviewed cases for helmets, missed detections, multiple faces, cuts,
age conflicts, jersey reuse, another bowler, true/attempted run-out, four/six,
no-event scenes and long-video playback. Record recall/false positives and
uncertainty rather than manufacture identities. Corrections round-trip through
P03. All structural identity and correction checks are mandatory; best-effort
classification thresholds are frozen with the cohort.

### P08 — Project verified revisions into review and search

**Depends on:** P03 and P07. **Owner:** publication/read models.

Publish versioned derived views from verified OpenLABEL revisions while retaining
the existing correction/import interface. Show the last verified generation and
publication lag. Make a saved correction immediately effective in review, then
reconcile it into the next verified scene/search generation. Resolve current names
without rerunning vision. Preserve explicit conflict handling for another
producer's accepted facts.

**Verify:** correct, confirm, dismiss, undo and reanalyze a moment through UI →
ledger → PostgreSQL readback → search. A failed publication retains the last valid
generation; a stale revision cannot overwrite a newer correction. Migration
backups and rollback retain all edits. No hidden duplicate face store is introduced.

### P09 — Run the observed pilot and descending comparisons

**Depends on:** P01–P08. **Owner:** cricket operations.

Start with a fresh live census and a frozen reviewed pilot, using the common
intake, diagnosis/registration, publication and review commands. Run the measured
maximum shared allowance first, then lower candidates one pool at a time. Repeat
qualifying comparisons in reverse order. Keep Knowledge Index and any other
baseline workers processing throughout.

Use fresh inference in an isolated evaluation receipt namespace for each phase and
repetition. Repeated frozen inputs must not inflate the globally deduplicated
production counter; cached answers do not count toward trial throughput or its
minimum-completion gate. Keep peer production deltas and target production progress
alongside the separate evaluation rates. Verify every evaluation output through
the same publication contract, recording whether an identical saved revision was
reused. Do not confuse a repeated inference result with a newly processed original.

**Verify:** each comparable warmed window is at least 300 seconds; sample gaps are
at most 15 seconds; each backlogged indexing workload completes at least ten
durable items. Peers retain at least 90% of baseline throughput, p95 grows no more
than 10%, terminal-error rate does not increase, and tighter service budgets hold.
If sufficient comparable work is unavailable within the policy's 15-minute bound,
record an inconclusive trial. Select the fewest workers within 5% of the fastest
repeatable qualifying rate. Retain failures and post-backoff recovery evidence.

### P10 — Deploy and resume the scoped backfill

**Depends on:** P09. **Owner:** deployment and cricket operations.

Deploy immutable tested code using the existing rollout/backup path; use Flux for
managed Kubernetes changes. Resume only the intended source/analysis version and
preserve completed work, leases and corrections. Persist the qualified allocation
with its workload mix. Requalify when peers, models or placement change.

**Verify:** production manifest/readback and metric/ledger reconciliation, review
and search correctness, peer progress, service restart, expiry/backoff and recovery.
Report analyzed, published, verified, pending-face and terminal-error counts
separately. Remaining missed faces or uncertain outcomes retain reviewable states.
Check off live completion only with a production run receipt and acceptance review.

## Review and rollout discipline

Each PR updates its checklist row and links its tests/evidence; a merge alone
does not check the verification box. Do not expand a code PR to change models,
recognition thresholds and worker capacity simultaneously. Archive private
manifests and traces under the run directory and commit only aggregate evidence.
The design and checklist must be amended when a contract or acceptance gate
changes. No new full-album inference, frame upload or production deployment is
performed merely by approving these planning documents.
