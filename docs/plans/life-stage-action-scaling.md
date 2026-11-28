# Implementation plan for scaling life stage and action

The first deliverable lets an operator open Grafana and see how many face observations Mac and RTX saved, how many reached the album store, and which other jobs share those devices. That baseline makes the first cricket arrival measurable. Stage and action quality take precedence over a higher inference rate.

[Scaling design](../architecture/life-stage-action-scaling.md) · [Task and evidence checklist](../experiments/life-stage-action/scaling-checklist.md) · [Photo memory epic](https://github.com/homeiac/home/issues/228) · [Existing implementation plan](photo-memory-implementation-plan.md)

## Smallest independently verifiable changes

Start with S1. Each row is one reviewable change or a measurement-only trial. An existing adapter or panel that passes the exit check can close the task with evidence alone. Update this plan and the active story **before** changing implementation when a measurement changes the next step. Record what changed, why, the new acceptance check and what was deferred.

| ID | Change and owner | Depends on | Exit check |
|---|---|---|---|
| S1 | Photo operator captures a read-only baseline. Record physical devices, endpoints, actual lanes and pass modes, queue dispositions, observed callers, scheduled reservations and telemetry age. Mark an idle, unhealthy or unobserved peer explicitly. | Existing workers | Reconcile one closed production window against the queue and the Mac/RTX graph. Record scope, UTC bounds, private receipt and a Grafana link. Leave gaps visible. |
| S2 | Telemetry owner registers the photo workload against both Bonsai pools and their devices. Reuse workload intake and export bounded per-stage spans and counters. | S1 | A trace follows a face from claim to writer, including retry. Each affected caller appears in the census. Dashboard rates reconcile to unique checkpoint completions for the window. |
| S3 | Publication owner adds a photo adapter for the existing shared media verifier or proves the current adapter satisfies it. | S1 | Independently read back the expected PostgreSQL occurrence, revision, digest, vocabulary and actor relations. Replay a retry and a correction. Demonstrate one effective result, preserved native IDs and zero lost corrections. Test a foreign-owned scene. |
| S4 | Performance owner applies the shared trial gates to either subject and exposes the decision in the existing dashboard layout. | S2, S3 | Recorded photo and cricket fixtures both hold on missing peer samples and roll back on known loss. Verify the before/after panels in deployed Grafana against the same ledger window. |
| S5 | Photo operator runs one matched live trial on one backend at a time. Diagnose claim, preview, model and write using closed spans before selecting a change. | S4 | Reverse-order repeat passes the gates below. Record Mac and RTX separately, including a rejected or inconclusive setting. Retain the last proven allocation if no candidate wins. |
| S6 | Cricket operator adds a bounded real video batch with the photo baseline still active. Test preparation/upload separately from model lanes. | S4, current baseline for the mixed run | Count unique source minutes, read back effective events, check correction preservation and reconcile the Immich detection queue. Record the impact on photo output and all other callers. Repeat on each pool proposed for cricket. |
| S7 | Supervisors promote the qualifying settings for the measured mix and rehearse rollback and restart. | S5 and S6 for a mixed allocation | Drain only the increment, read back already committed results, check for double publication and confirm peer recovery. Save the winning allocation and dashboard comparison with the workload mix and policy versions. |

S5 and S6 each have their own baseline. A photo-only win can qualify photo-only operation. If cricket arrives before S5 finishes, retain the photo workers, close the old window and start a mixed baseline. A wait for real cricket demand leaves S6 open. The next step never depends on pretending that an idle queue is a backlogged peer.

## November 27 execution update

The live intake sees the cricket controller and the shared GPUs. It omits photo face completions as an independent caller. Split S2 into a first PR registering both photo routes and reading the existing stage-scoped queue and backend counters, then a worker instrumentation change for end-to-end traces. Verify the first PR against the same private checkpoint used in S1. The library reader serves SQLite, and the cluster enrichment database has no OpenLABEL scene table. Leave the independent publication count unknown until S3 supplies its manifest and readback. Keep the historical album pilot separate. The cricket integration has its own [plan and checklist](https://github.com/homeiac/home/pull/274).

## Model-server timing probe

Before changing a prompt or image, measure a common live window. On RTX, pair the runner's input and output timers by slot and task. On Mac, sample numeric slot progress before and after decoding begins. Keep client latency, queue delay and device execution distinct. Reuse the reviewed-face comparison for previous pass-count settings. Record the outcome with the per-backend Grafana results. A candidate that would add a lane requires the peer headroom and quality gates below.

## Guarded input trial

Use the existing twelve-face reviewed cohort, with original prompts, pass modes and unchanged close-ups. Alternate original-first and smaller-first paired generations on each backend. One serial test client per backend submits at most one request at a time through the existing serving pool. Keep ordinary workers running. Retain the original marked scene if 640 px would reduce the marked face below 12 px. Record valid dispositions, exact reviewed stages, full action phrases and elapsed request time privately. Compare quality before considering any production change. This bounded screening cannot qualify a new fleet allocation. A failing quality arm ends promotion and keeps S5 open.

## Acceptance contract for a live trial

1. **Declare the trial.** Freeze cohort, model/quantization, prompt, media sizes, pass modes and versions. Use matched inputs for quality and separate production counters for rate. Record each baseline, trial, reserved and rollback allocation and a target minimum gain before starting. Use the last known effective settings if actual headroom is unknown.
2. **Measure peers.** Use equally long warmed windows of at least five minutes, samples no more than 15 seconds apart and at least ten durable completions per continuously backlogged workload. Extend matched windows for long jobs. If they still lack comparable evidence after 15 minutes, hold. Each peer must retain at least 90% of its useful rate, with at most 10% higher p95 and no increase in terminal-error rate. Apply any tighter service budget. Predeclare a no-progress deadline from normal job duration and lease/deadline.
3. **Check meaning.** On the same reviewed faces compare stage accuracy, supported action on the marked actor, and both correct together, per backend. Require no drop in these paired scores or completion coverage and no new wrong named actor, duplicate occurrence or lost correction. Cover multiple people, uncertain date, small/obscured face and an appropriate withholding. For cricket, use reviewed time windows, event/actor decisions and corrected clips. Record eligible denominators, unresolved cases and withheld counts so abstentions cannot inflate scores.
4. **Protect production.** Unknown or stale peers hold the trial. OOM, unavailability, missed progress deadline or demonstrated regression drains the trial increment. Keep baseline work running, verify recovery and enter the failed setting in the checklist. Repeat qualifying settings in reverse order. Persist the smallest allocation within 5% of the fastest repeatable passing rate.
5. **Close the task.** Independently reconcile published output, record the decision and attach before/trial/recovery Grafana windows per backend. Keep private records outside Git. The checklist can mark a code change implemented while live verification remains open. Reopen the promotion gate after a change in workload mix, backend, model, prompt or publication path.

Use the existing trial directory and CLI. The owner supplies the comparison, time-bounded traces and independent readback. A successful CLI exit only establishes that review ran. Inspect its decision and the reviewed examples before promotion. [Playbook and evidence workflow](https://github.com/homeiac/home/blob/b4a19672cd37301206a5487c8f2e192c34f75bb7/docs/guides/shared-workload-agent.md) · [Detailed peer budgets](https://github.com/homeiac/home/blob/b4a19672cd37301206a5487c8f2e192c34f75bb7/docs/runbooks/shared-indexer-tuning.md)


## Still-fawn CPU canary

Readiness found the prior loopback CPU endpoint stopped and no reusable runtime or weights in the guest's standard storage roots. VM 108 has roughly 20 GiB available memory. Use a temporary, time-bounded loopback-only CPU server with the same pinned Bonsai weights and projector, one lane and at most two CPU threads. Verify downloads by digest and prevent duplicate servers with an exclusive lock. Keep startup/download time separate. Probe the same reviewed full scene and crop with the unchanged joint prompt and validator. Record stage, actor-action support, latency and peer progress. A temporary canary cannot qualify ongoing allocation. Persist any selected worker through GitOps after quality and peer checks.


## Shared stage normalization during CPU evaluation

Extract the existing allowed-stage/confidence check and low-confidence-to-unknown mapping into a pure helper in the existing library worker. Reuse it in production inference and the CPU evaluator, retaining the current prompts, validation errors, checkpoint fields and abstention behavior. Add a regression check for invalid fields and low-confidence normalization. Bind the helper source revision to subsequent trials. Earlier immutable trial results keep their original profile and are scored using the same production semantics.


## Correct the unit of throughput qualification

The first CPU arms were stopped using per-backend rate floors. Those backend measurements remain valid, but Metal and CPU serve the same face workload. Reopen their aggregate qualification under the user's total-throughput objective. Preserve reserved GPU worker counts, combine newly verified face outcomes and workload latency/errors across backends, and protect distinct peer workloads separately. A per-backend slowdown alone cannot close a candidate. Keep the original stopped-trial receipts and label the policy correction and missing production-output evidence. The dashboard must show the scope of that reassessment.


## Opt-in unique-job CPU canary adapter

Prepare the adapter with CPU lanes zero by default and a finite job limit. The existing owner controls serving capacity and the Kubernetes pool lease. Before each claim and commit, verify that lease and its holder. Reuse production inference, prompts, normalization and the indexed SQLite claim path, with an injected CPU observer. Add an atomic claim hook and expected-claim-state fencing while preserving existing callers' defaults. Record CPU reservations with unique generations, expiry and the exact input so stale results cannot overwrite a retry or a changed source, including after the GPU supervisor resets running jobs. Expired recovery must match the CPU generation.

Store model/profile provenance with stage and action results. Release interrupted jobs safely and bound bad-response retries. Export separate bounded mac-cpu/still-fawn-cpu counters, while retaining existing legacy-backend handling. Verify concurrent claims, lost ownership, changed inputs, restart/reclaim fencing and partial reuse with isolated tests. The adapter remains disabled and cannot claim real jobs until reviewed quality and capacity evidence qualifies a bounded live canary. The existing scene writer supplies publication/readback after an accepted result.


The enabled CPU canary also requires the existing registered photo RunTelemetry provider. Trace claim, inference, checkpoint and write stages with native job/input/profile/generation context. Forward its actual caller/run/W3C headers through both OpenAI HTTP and guest-agent curl. The adapter records checkpoint saves; only independent publication receipts may increment verified-output counters. Disabled operation has no telemetry dependency and no queue mutation.
