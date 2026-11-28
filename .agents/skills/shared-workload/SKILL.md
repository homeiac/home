---
name: shared-workload
description: Observe or tune workloads sharing CPU, accelerators, memory or storage, using their own progress units, service budgets and native publication contracts.
---

Use the [agent journey](../../../docs/guides/shared-workload-agent.md) and
[adapter contract](../../../docs/reference/workload-adapter-contract.md). The workload
owns execution, semantic quality and canonical data; shared scripts review evidence.
Start `scripts/perf/workload.py` with the actual workload/run/stage/resource IDs.

Before scaling, expand stage-by-physical-pool coverage with `plan-compute-trials.py
POLICY --inventory`. Include CPUs without endpoints and deduplicate hosts/guests.
Each unmeasured candidate needs readiness/timing/quality evidence, demonstrated
incompatibility or an owned deferral/revisit. Occupied GPU slots do not exclude
independent pools. Preserve coverage gaps in the checklist.

Coordinate existing chats when user-authorized. Record one actuator per physical
pool, peer and scheduled reservations, expiry, rollback and acknowledged handoff.
Verify process/port/lock cleanup before another owner submits. Derive the maximum
shared allowance after measured demand/reservations; bound aggregate CPU as well as
threads/contexts, start at that ceiling and descend. Keep production workers intact.

Reuse production model clients, parsers, validators, queue and writer. Replay saved
responses before inference. Preserve harness failures separately from model errors.
Freeze source/cohort/model/prompt/extraction/rubric/environment and adapter versions.
Count invalid/abstained quality cases in the full declared denominator; safety stops
remain partial. Review complete semantic claims, including actor/object attribution.

For a finite job, use one fixed remaining-work snapshot and combined unique useful
production across same-workload backends. Run `completion_objective.py OBJECTIVE
--at-ns CUTOFF`; `qualify-capacity` consumes that same result. Evaluation replays,
cache hits, retries and withheld outputs cannot create production gain. Passing
peer budgets alone cannot promote. Missing native readback or no projected reduction
in whole completion time holds the candidate. Keep service objectives in their own
SLO units instead of inventing durable outputs or backfill ETA.

Use declarative observer mappings and saved inputs with an explicit cutoff for
replay. Record hashed job/source/version/execution identity, immutable profile,
mode and retained-stage reuse in private attempt evidence. Sum deduplicated output
within each workload; compute combined latency from raw attempts or mergeable
histograms, never average backend p95s. Backend slowdowns are diagnostic unless a
real backend SLO exists. Protect distinct workloads separately.

Keep baseline/trial/recovery controls and reverse-repeat qualifying settings. A
slow no-increment control leaves causation unresolved; do not retry until a pass or
select a convenient baseline. Require complete sampled windows and fresh health
observations. Distinguish pending jobs blocked before inference from runnable work,
while retaining scheduled reservations. Throughput/utilization alone do not prove
a CPU, GPU or memory-bandwidth bottleneck.

Preserve data architecture: media uses the existing native-ID OpenLABEL writer,
pinned schema, revisions and independent readback. Nonmedia uses a frozen native
adapter for its existing schema/store and saved execution provenance. Do not add a
second canonical store or manufacture origin/first-commit facts. `other` is not a
verification escape hatch. Services use registered measured service contracts.

Diagnose/review closed captures with the shared CLI and use the existing supervisor
for execution. Registration, output summaries, ETA and offline qualification do not
actuate capacity. `qualify-capacity` currently returns `not_admitted`/`proceed=false`
until ordered phases, independent fresh evaluation, repeats and lease/dispatch
execution gates are implemented. Do not describe the one-increment feedback loop
as maximum-first tuning or an `eligible` sub-review as live admission.

Close the requested scope with the science journal/checklist, selected and rejected
settings, timestamps and explicit unmeasured arms. When the user requests
consolidation, report the best supported measured setup with its limits. Keep private
raw evidence under persistent storage with verified hashes/permissions; commit only
aggregate findings and references. Push changes and independently read served
Grafana values, naming GPU series as before/during the added workload so a rejected
increment is not confused with rejection of an incumbent backend.

[Playbook](../../../docs/methodology/distributed-ai-performance.md) ·
[Telemetry](../../../docs/reference/workload-telemetry.md) ·
[Media architecture](../../../docs/architecture/media-workload-contract.md)
