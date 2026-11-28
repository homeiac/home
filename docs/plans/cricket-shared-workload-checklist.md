# Cricket implementation and verification checklist

Updated: 2026-11-27, America/Los_Angeles. Issue:
[#250](https://github.com/homeiac/home/issues/250).

[Implementation plan](cricket-shared-workload-implementation.md) ·
[Design](../architecture/cricket-shared-workload-design.md) ·
[Authoritative playbook](../methodology/distributed-ai-performance.md)

This is the status authority for the remaining integration. Each P identifier
matches one small PR in the plan. Update this file in the PR that changes its
status. A checked item must name evidence and its scope. No live services or worker
allocations were changed while preparing these documents.

## How to use the checklist

| Status | Evidence required |
| --- | --- |
| Implemented | Concrete source revision and actual PR link, with the planned behavior present |
| Merged | Target branch and merge commit; an open PR does not satisfy it |
| Locally verified | Exact command, source revision, result and environment; failures/skips retained |
| Deployed | Environment, immutable deployed release and read-only inspection receipt |
| Live verified | Run ID/evidence pointer, expected result, observed result, peer impact and recovery where relevant |

Keep implementation, local verification and live verification separate. Record
`not applicable` with a reason for a purely local contract task; do not mark it
live-verified. Unchecked means not yet demonstrated at this scope, not necessarily
that no prototype exists. If a new change invalidates an earlier check, uncheck it
and append the reason; retain the original receipt.

## Verified foundations

- [x] **F01 — Current playbook and supporting contracts inspected.** Source is
  master `b4a19672`; the actual CLI, shared reviewer and media checker were inspected.
  Evidence: E01. Scope: repository implementation, not live integration.
- [x] **F02 — Shared tuning policy and OpenLABEL adapter are on master.** PRs #270,
  #271 and #273 are merged. Evidence: E01. The broader feature stack remains open.
- [x] **F03 — Current shared-workload and media contract tests pass locally.**
  Evidence: E02, 83 tests passed; the first dependency failure is retained below.
- [x] **F04 — Synthetic PostgreSQL publication and independent readback pass.**
  Evidence: E02; two revisions after a correction, identical retry creates no third
  revision, stable action occurrence, references verified, another producer preserved.
- [x] **F05 — Historical native-face and backfill evidence inventoried.** Evidence:
  E03. This establishes what earlier runs reported; it does not qualify a new run.
- [ ] **F06 — Production pipeline satisfies the full playbook.** Requires E04–E06;
  local tests and historical journal entries do not satisfy this item.

## Small-PR progress

| ID | Scope | Actual PR / source | Implemented | Merged | Local verification | Deployment / live verification |
| --- | --- | --- | --- | --- | --- | --- |
| P01 | Reconcile feature stack; freeze acceptance cohort | P01-a [#276](https://github.com/homeiac/home/pull/276); P01-b `codex/cricket-p01-inference`; P01-c `codex/cricket-p01-worker` | Backend reconciled; UI/cohort pending | No | E09: 136 passed, 43 subtests | Authority/policy/rollback inventory captured; no new deployment |
| P02 | Run identity and closed telemetry | To create | No | No | Pending | Pending |
| P03 | Manifest, readback, receipt and no-event output | Adapter exists in #271/#273; extension PR to create | Partial foundation | Foundation only | E02 covers synthetic writer, not production adapter | Pending |
| P04 | Complete resource/peer measurement | Common observer/reviewer exist; adapter PR to create | Partial foundation | Foundation only | E02 covers common gates | Complete live peer windows pending |
| P05 | Maximum-first trial registration | To create | No | No | Pending | Local contract; live use through P09 |
| P06 | Owning supervisor and pool lease | To create | No | No | Pending | Pending |
| P07 | Reviewed identity/outcome evidence | Existing #264/#266/#269; follow-up PR to create | Partial | Existing feature PRs open | E03 contains unresolved pilot results | Fresh quality pilot pending |
| P08 | Verified review/search projection | Existing #259; canonical projection PR to create | Partial legacy view | Existing feature PR open | End-to-end canonical test pending | Pending |
| P09 | Peer-qualified descending pilot | Evidence PR to create after prerequisites | No | No | Prerequisites required | Pending |
| P10 | Deploy and resume scoped backfill | Release/evidence PR to create | No | No | Prerequisites required | Pending |

### P01 — Reconcile and freeze

- [x] **P01-a-I/V:** Reconcile inventory selection, age context and caption/contact-
  sheet helpers with the existing ledger, native faces, coordinates and kit clues;
  restore their original regression tests. Evidence: E07. This is a local
  integration slice, not the entire feature stack or a production deployment.
- [x] **P01-b-I/V:** Reconcile existing model transports, transcript outcome guards
  and matched evaluation helper. Evidence: E08. All model requests in these tests
  are mocked; this does not qualify live inference or automatically admit a trial.
- [x] **P01-c-I/V:** Reconcile the existing dispatcher, renewable leases, proposal
  reconciliation, versioned operations and their regression tests. Evidence: E09.
- [ ] **P01-I:** Reconcile required open feature modules with master, preserving
  #273's contracts and PostgreSQL test; record exact PR/source/merge state and
  regression evidence for each existing small PR, rather than one bulk import.
- [ ] **P01-V:** Run correction/playback/retry regressions and freeze the reviewed
  cohort, input versions, quality rubric and thresholds.
- [x] **P01-D:** Record current deployed release, authoritative ledger, policy and
  rollback location without replacing or resetting live state.
  Evidence: E09. Backup locations are inventoried, not restore-tested here.

### P02 — Trace and export

- [ ] **P02-I:** Add media run intake, caller identity, queue/writer trace propagation,
  declared stages and atomic closed OTLP exports.
- [ ] **P02-V:** Verify SDK encoding, retries, asynchronous handoffs, one-host
  diagnostic slices, label filtering and restart-safe watermark behavior. Confirm
  the baseline and intended trial share a run ID with separate allocation phases.
- [ ] **P02-L:** Capture a real cricket job and reconcile its stage spans and attempts
  with the operational ledger. Link private capture and aggregate receipt in E04.

### P03 — Publish and read back

- [ ] **P03-I:** Emit manifest/outbox records, independently query committed scenes,
  persist verification receipts and introduce the versioned no-event context.
- [ ] **P03-V:** Verify schema/run/digest/typed links, crash recovery, retry dedup,
  valid negatives, pending detection, stale corrections and foreign-producer refusal
  against disposable PostgreSQL. Existing E02 is the foundation, not this extension.
- [ ] **P03-L:** Produce a real media run accepted by `workload.py verify-media`;
  reconcile unique sources, source minutes and referenced occurrences separately.

### P04 — Measure every affected workload

- [ ] **P04-I:** Complete server and device caller census, measured routes,
  scheduled reservations and workload-specific progress/quality/service adapters.
- [ ] **P04-V:** Demonstrate stale/absent/idle distinctions, unknown callers, changed
  workload mix and rejection of a cricket gain that breaches a peer budget.
- [ ] **P04-L:** Capture complete simultaneous windows for cricket, Knowledge Index
  and all other affected active callers; explicitly account for inactive peers.
  Do not invent counts for service-only peers such as Frigate.

### P05 — Register the intended experiment

- [ ] **P05-I:** Add a supported bounded concurrency action, immutable pre-change
  registration, measured ceiling/reservations and descending comparison schedule.
- [ ] **P05-V:** Reject tampered/stale action, source, policy, ceiling and allocation
  records; verify a concurrency trial cannot borrow a FIFO or isolation receipt.
- [ ] **P05-M:** Merge the contract extension before P09 uses it; record the actual
  merge revision and keep the common review CLI free of production actuators.

### P06 — Actuate and recover

- [ ] **P06-I:** Wire decisions into the cricket supervisor with exclusive pool
  ownership, fencing/expiry, desired-versus-observed counts and drain behavior.
- [ ] **P06-V:** Test two competing owners, stale owner, restart, deadline, telemetry
  loss, in-flight completion and bounded rollback without losing corrections.
- [ ] **P06-L:** Verify deployed recovery and peer progress while removing only the
  cricket trial allocation. Record all other actuators' coordination participation.

### P07 — Qualify cricket evidence

- [ ] **P07-I:** Resolve per-event coordinate output, evaluate video face coverage,
  and connect age/kit/continuity evidence without manufacturing native IDs.
- [ ] **P07-V:** Score the frozen cohort: helmets, other players, cuts, true versus
  attempted run-out, four/six/wicket, no-event scenes, long clips and pending faces.
  Every returned detection retains its native ID; unknown person name is separate.
- [ ] **P07-L:** Verify correction controls and full original playback on the pilot;
  show which person/role/result/time is being corrected and preserve edits on rerun.

### P08 — Reconcile review and search

- [ ] **P08-I:** Project verified canonical scene revisions into search/review while
  retaining immediate effective edits and an explicit publication-lag state.
- [ ] **P08-V:** Exercise correct/confirm/dismiss/undo/reanalyze through ledger,
  PostgreSQL readback and derived views; reject stale overwrite and retain last
  valid publication on failure. Check name refresh without vision rerun.
- [ ] **P08-L:** Confirm a real correction survives a new generation and appears in
  the correct filters; validate migration backup and rollback without data loss.

### P09 — Run and qualify the shared-capacity pilot

- [ ] **P09-R:** Seal the fresh census, source cohort, hypothesis, budgets, ceiling,
  rollback and comparison order before the trial; link the receipt in E05.
- [ ] **P09-H:** Run the highest measured shared allowance first, then lower counts
  on one pool; keep all baseline workloads running and record every failed setting.
- [ ] **P09-A:** Use fresh evaluation receipts per phase/repetition, exclude cached
  answers from trial rate/minimum counts, and keep repeated evaluations separate
  from production completions. Record actual peer and target production deltas.
- [ ] **P09-V:** Satisfy equal warmed windows ≥300 seconds, sampling gaps ≤15 seconds,
  minimum ten completions for backlogged indexing peers, matched inputs/environment,
  media readback and semantic quality gates. Honor tighter existing service budgets.
- [ ] **P09-P:** Confirm peer rate ≥90%, p95 growth ≤10%, no increased terminal-error
  rate, and recovery after backoff. Missing/incomparable evidence stays inconclusive.
- [ ] **P09-S:** Repeat in reverse order and select the fewest workers within 5% of
  the fastest repeatable qualifying rate; persist the exact qualified workload mix.

### P10 — Roll out and close

- [ ] **P10-D:** Deploy the qualified immutable release with existing backups and
  Flux where applicable; inspect the actual running release and policy.
- [ ] **P10-R:** Resume only the scoped source/analysis version; retain prior work,
  leases, native IDs, user corrections and explicit terminal/pending states.
- [ ] **P10-V:** Reconcile production ledger, manifests, PostgreSQL/readback,
  projections and metrics; verify peer service plus restart/expiry recovery.
- [ ] **P10-C:** Record residual recognition errors and pending work, link the live
  acceptance receipt, and mark completion only for the demonstrated scope.

## Evidence register

### E01 — Source and merge inspection

On 2026-11-27, inspected the requested playbook and related implementation at
[`b4a19672cd37301206a5487c8f2e192c34f75bb7`](https://github.com/homeiac/home/commit/b4a19672cd37301206a5487c8f2e192c34f75bb7).
GitHub reports [#270](https://github.com/homeiac/home/pull/270),
[#271](https://github.com/homeiac/home/pull/271) and
[#273](https://github.com/homeiac/home/pull/273) merged. The feature PRs #251–#266
and #269 listed in the original plan remain open at this check. Do not assume
their complete worker/UI stack is present merely because a publication subset is
on master. Recheck statuses when P01 starts; this is a dated observation.

### E02 — Fresh local verification

Source: `b4a19672`. Run completed at approximately **2026-11-27 20:50 PST**
(`2026-11-28T04:50:54Z` observation). Result: **83 passed in 4.22 seconds**, zero
skips reported. This count belongs to the current master verification command,
not the historical feature branch's different test set.

Command from the repository root:

```bash
PYTHON=/path/to/test-environment/bin/python \
ASAM_OPENLABEL_1_0_SCHEMA=/private/path/openlabel-1.0.0.json \
bash scripts/perf/verify-cricket-publication.sh
```

Environment: Python 3.14, pytest 9.2.0, jsonschema 4.26.0, psycopg 3.3.9,
OpenTelemetry SDK/exporter 1.45.2 and protobuf 7.36.2; PostgreSQL 16 tools on PATH.
The schema was the local 1.0.0 artifact accepted by the CLI's canonical digest
check. PostgreSQL used a disposable directory and local Unix socket; no production
database was written. The fixture stops its server and removes its directory.

The first run returned **82 passed, 1 failed** because `google.protobuf` was absent
from the isolated test environment. Installed the missing OTel exporter/protobuf
dependency and reran the same command. The final run passed. A pytest-asyncio
default-loop-scope deprecation warning remains informational.

The [publication test](../../scripts/knowledge-index/cricket/test_publication_readback.py)
checks the real shared writer, independent SQL readback, stable action identity,
two append-only revisions, identical retry, reference verification and preserving
another producer's scene. The
[common reviewer tests](../../scripts/perf/tests/test_shared_workloads.py) exercise
peer regression and missing evidence. Neither test proves production caller
coverage, video-face recall or live peer-safe throughput.

### E03 — Historical evidence, not a new qualification

Source: [cricket experiment journal](../experiments/cricket/science-journal.md).
It records an initial 633-video/867-photo pass, four attempted-run-out corrections,
full-video playback, a failed coordinate-placement trial, and the native face pilot.
The OpenLABEL pilot validated nine scenes with 44 sampled frames and five native
faces; some detection work remained pending and video-face recall was unproven.
These observations have not been refreshed as part of this documentation task.

### E04 — Production integration receipt

**Pending.** Required: private run/evidence location; source and deployed revisions;
session and trace identity; independently exported scene revisions; schema and
reference checker results; unique source/attempt/reference reconciliation; a
reviewed correction through UI/search; any unresolved cases.

### E05 — Shared-capacity experiment receipt

**Pending.** Required: sealed pre-change action; physical resource closure and
caller census; peer reservations/budgets; per-window inputs and actual allocations;
per-peer progress, quality, latency/errors and freshness; all failed settings;
reversed repetitions; selected count; post-backoff recovery and requalification
conditions. Include each review decision, not only the final winner.

### E06 — Deployment and live acceptance receipt

**Pending.** Required: immutable release and backup/rollback reference; scope and
analysis version; analyzed/published/verified/pending/terminal counts; manifest to
database to derived-view reconciliation; preserved corrections; peer health;
restart/expiry/recovery result; outstanding best-effort recognition issues.

### E07 — P01-a identity dependency reconciliation

Branch: `codex/cricket-p01-evidence`, based on the planning PR #274 and master
`b4a19672`. Reused the original implementation at `d5eeda7` without changing its
behavior: inventory import and owner/person selection (#254), caption/contact-sheet
context (#256), date/age guards (#264), and coordinate/nearby-kit regression coverage
(#266), plus the durable correction ledger tests (#251 and follow-ups).
The newer master OpenLABEL writer/readback tests remain present.

Verification on 2026-11-27: the E02 command passed **111 tests and 19 subtests in
3.82 seconds** against disposable PostgreSQL. Early collection attempts exposed
missing importer, context and contact-sheet dependencies; the complete identity
dependency slice now passes. Model dispatch tests were left for the runtime slice
rather than importing that subsystem implicitly.

Read-only deployment inspection found the GUI release
`dashboard-1795836747906611473`; GUI and audio-story services were active, and
Knowledge Index enrichment reported `activating` at that instant. The private
receipt is `/private/tmp/cricket-p01-deployment-20261127.json`. This is not a peer
throughput or readiness qualification. No live worker or release was changed.

Dependency inspection also found photo-review PR #218 still open and conflicting
with its base (`feat/media-summaries-enricher`). The cricket UI stack builds on it.
Keep frontend reconciliation explicit; do not bulk-import that application or
replace the newer deployed dashboard merely to make a backend test pass.

### E08 — P01-b inference dependency reconciliation

Branch: `codex/cricket-p01-inference`. Restored `models`, `reactions`, `trial` and
their original regression tests from `d5eeda7` (feature PR #256 and follow-ups).
The E02 verification command passed **121 tests and 43 subtests in 4.86 seconds**.
Requests are mocked; no new media upload, inference or worker allocation occurred.
This legacy evaluation helper must still be wired to the new run/review contract
before an authorized capacity experiment; it is not a replacement for P02–P06.

The shared CLI's `start --live --output-kind media` intake expanded Mac Bonsai to
Metal and found Knowledge Index and Waffles as registered peers. The private
receipt is `/private/tmp/cricket-p01-intake/session.json`, run
`cricket-p01-integration`, and its decision is `observe_only`. Cricket had no active
or queued jobs and four desired workers; Waffles had no active Mac workers. The
Knowledge Index summary enricher was active with a fresh successful exporter
observation. These are activity observations, not complete matched peer windows.

### E09 — P01-c worker reconciliation and authority inventory

Branch: `codex/cricket-p01-worker`. Restored dispatcher/lease/reconciliation modules
from `d5eeda7`, preserving the current master's OpenLABEL and shared-workload
modules. Original feature provenance is #257, #258, #260 and #265. The E02 command
passed **136 tests and 43 subtests in 4.10 seconds**. This covers stale-lease
fencing, bounded failed-job retries, checkpoint reuse, preserving corrections and
versioned reanalysis. These worker tests mock inference and do not launch a backfill.

Added the reusable read-only `python -m cricket.inspect_state --host HOST --output
PRIVATE.json` command. The private receipt is
`/private/tmp/cricket-p01-state-20261127.json`. It opens SQLite with `mode=ro` and
`query_only`, and reads the live policy without invoking its mutation commands.
Observed: authoritative ledger `/var/lib/photo-enrichment/cricket/ledger.sqlite3`,
1,500 completed jobs (633 videos, 867 photos), four saved correction revisions,
Mac desired/hard limit 4/4, RTX 0/2, all four inspected services active. The GUI
release remains `dashboard-1795836747906611473`; the inspected GUI release does not
contain `cricket/openlabel.py`. Thus canonical publication is not deployed there.
Five retained deployment-backup directories were inventoried under
`/opt/photo-enrichment/backups`; no backup restore was attempted.

## Updating evidence

For each new receipt record date/time, task ID, source/PR, environment, exact
command or run identifier, expected outcome, observed outcome, pass/fail/skips,
aggregate metrics, private evidence location and remaining criterion. Keep personal
media, source IDs, transcripts and access material out of Git. Link a durable
private archive before deleting temporary captures. A checkbox without that
receipt must remain unchecked.
