# Life-stage/action scaling checklist

**S1 verified for checkpoint saves.** The photo queue and the deployed Grafana totals agree within the sampling resolution. S2 worker tracing and S3 publication readback remain open. The current decision is observe only.

[Scaling design](../../architecture/life-stage-action-scaling.md) · [Implementation plan and acceptance gates](../../plans/life-stage-action-scaling.md)

## Evidence already checked

| Verified scope | Date and result | Receipt |
|---|---|---|
| [x] Queue inventory, one read-only snapshot | 2026-11-28 04:48:53 UTC (Nov 27, 8:48 p.m. Pacific). **82,499 face occurrences** = 47,774 newly complete + 4,600 reused + 848 withheld + 7 running + 29,270 pending. This measures face jobs. Published scene coverage and throughput require separate reads. | Private library checkpoint, reproducible aggregate query below. |
| [x] Backend method comparison on a fixed cohort | Nov 26. Mac kept two calls at four lanes. RTX selected one call at three lanes. Each method had 48 attempts per backend. On the 40 readings with a reviewed stage, both stage and action were correct 16 times for the retained Mac method and 24 times for the selected RTX method. | [Matched readings and rates](../../../scripts/knowledge-index/library-pass-comparison.json) |
| [x] Worker and claim regression checks at the pinned photo source | Nov 27 Pacific. All 11 unit tests in the two modules passed. Coverage includes checkpoint reuse, marked-actor validation, joint inference and claim reconciliation. This is code-level evidence. | [Photo worker tests](https://github.com/homeiac/home/blob/7256a36a9faed4cb0da4fe00b3ebcc09098eb1cc/scripts/knowledge-index/memory-acceptance/test_library_worker.py) · [Claim tests](https://github.com/homeiac/home/blob/7256a36a9faed4cb0da4fe00b3ebcc09098eb1cc/scripts/knowledge-index/memory-acceptance/test_reconcile_claims.py) |
| [x] Existing dashboard definition located | Nov 27. The generator includes per-backend saved results, matched before/after lane comparisons and two-call versus one-call quality. A current mixed-workload dashboard readback is still open. | [Generator](../../../scripts/knowledge-index/gen-dashboard.py) · [Knowledge Index dashboard](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index) |

Reproduce the aggregate inventory with a read-only connection to the private library checkpoint. Use one statement so all states share a snapshot. The ledger primary key is a face occurrence. Repeated images in a benchmark earn no additional library progress.

```sql
SELECT datetime('now') AS observed_utc, status, count(*) AS face_occurrences
FROM jobs
GROUP BY status
ORDER BY status;
```

## Delivery and verification are separate

Mark a task verified only when its owner records the UTC window, scope, receipt, observed result and decision. A check in the first column below means the planned change or trial was carried out. A check in the second means its exit check passed. For a failed trial, record the rollback and recovery even if the candidate is never promoted.

| Done | Verified | ID | Evidence required to close | Current evidence or gap |
|---|---|---|---|---|
| [x] | [x] | S1 | Closed baseline census and ledger-to-Grafana comparison | See the November 27 closed-window receipt below. |
| [ ] | [ ] | S2 | Both pool routes, physical device census, trace through writer, bounded per-caller counters | [PR #275](https://github.com/homeiac/home/pull/275) implements and live-checks the two pool routes and per-backend checkpoint census. End-to-end worker/writer tracing is open. |
| [ ] | [ ] | S3 | Media manifest versus independent PostgreSQL readback, retry, correction and owner collision tests | The library reader uses SQLite. The cluster enrichment database has no scene revision table in any schema. The separate reference-album PostgreSQL cluster was shut down at measurement time. Production coverage is unknown. |
| [ ] | [ ] | S4 | Both subjects exercise sampling, minimum counts, p95/error and rollback gates. Grafana matches the measured windows. | Strict defaults currently branch on the cricket subject. |
| [ ] | [ ] | S5 | Matched photo canary, paired quality scores, reverse-order repeat and per-backend decisions | Historical pass-count trial is available. Full fleet comparison remains open. |
| [ ] | [ ] | S6 | Joint run with real cricket backlog, separate output units, independent readback and every peer within budget | Cricket journal records a pilot. It does not establish the capacity of this mix. |
| [ ] | [ ] | S7 | Promotion record for a named workload mix, expiry, restart/rollback and verified recovery | Await S5 and S6 evidence. |

[Shared reviewer](https://github.com/homeiac/home/blob/b4a19672cd37301206a5487c8f2e192c34f75bb7/scripts/perf/shared_workloads.py) · [Cricket pilot journal](https://github.com/homeiac/home/blob/b4a19672cd37301206a5487c8f2e192c34f75bb7/docs/experiments/cricket/science-journal.md)

## November 27 baseline with cricket idle

Private run `photo-scaling-s1-20261128` observed the library from 2026-11-28T04:55:41+00:00 to 2026-11-28T05:00:41+00:00. The Mac supervisor had four Mac lanes (separate stage and action) and three RTX lanes (joint inference on new work). The local Metal server offered four slots. No capacity change was made.

| Backend | Saved at start | Saved at end | Five-minute ledger rate | Grafana 15-minute trend at end |
|---|---:|---:|---:|---:|
| Mac Metal | 12,777 | 12,818 | 8.20 faces/min | 8.72 faces/min |
| RTX 3070 | 35,198 | 35,302 | 20.80 faces/min | 20.94 faces/min |

The ledger recorded **145 new saves**. At close, 28,922 were pending, 7 running, 4,600 reused and 850 withheld. The Grafana exporter runs less often than the ledger sampler. For each of 5 distinct in-window exporter reports, **both** backend totals fell between the consecutive 15-second ledger reads bracketing its progress timestamp. Panel 274 supplied the totals. Panel 273 fits a 15-minute trend, which explains why its rates can differ from the five-minute count. [Saved totals](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index?orgId=1&from=1795841741161&to=1795842041168&var-photo_stage=library-face-observations&viewPanel=274) · [Per-backend rates](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index?orgId=1&from=1795841741161&to=1795842041168&var-photo_stage=library-face-observations&viewPanel=273)

**Peer demand.** Cricket reported zero active workers and zero queued jobs, with four Mac lanes desired and zero RTX lanes desired. Preserve that potential demand when cricket work arrives. The pet tagger reported zero active Mac workers. Caption recovery reported zero pending assets. Knowledge Index's source heartbeat was stale in 8 of 21 observations using the existing 180-second limit. On the RTX host, Frigate was detecting at both spot checks. Immich face detection, facial recognition and smart search each reported zero waiting, active, paused, delayed or prioritized jobs at the queue check. Neither spot check establishes a full-window latency budget. The photo launch agent is scheduled every 60 seconds and the caption reconciler every five minutes. Reservations beyond these observed settings remain unknown.

**Decision — observe only.** No qualifying mixed-cricket window, verified publication rate or end-to-end peer latency comparison exists for this run. The intake change in [PR #275](https://github.com/homeiac/home/pull/275) exposes photo queue counts to cricket review and holds a trial that omits the photo peer. All 48 shared performance tests passed. The live intake used that PR's checkout.

## Which part of a model request took the time?

On Nov 27 from 9:19:26 to 9:21:30 p.m. Pacific, both production backends spent more time handling input or reaching the first output than producing the rest of the answer. Existing workers continued processing. These measurements describe **requests**. An ordinary Mac face uses two and an RTX face uses one. [Timing panel](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index?orgId=1&viewPanel=293) · [Aggregate receipt](../../../scripts/knowledge-index/library-server-timing.json)

| Backend | Measurement | Result |
|---|---|---|
| Mac Metal | Sample all four slots about once a second. Group by slot and task. Use complete transitions observed before the second output unit. Estimate each boundary halfway between adjacent observations. | Across 31 such requests, the median was 11.03 s before the second output unit and 3.01 s afterward. The longest gap between samples was 2.62 s. This first interval includes startup and initial decoding. |
| RTX 3070 | Join prompt, output and total timings by runner slot and task in the same UTC window. | Across 42 complete tasks, median input evaluation was 4.39 s and generation 2.25 s. Input evaluation accounted for 58.2% of summed runner time. All 42 HTTP calls succeeded. The median HTTP duration was 7.80 s. |

Queue wait before admission remains unmeasured. The Mac observation begins at slot assignment. The RTX HTTP log has no common request ID with the runner, and the attempted time match yielded zero unambiguous pairs under a 100 ms matching limit. Subtracting the two medians would not identify queue time. The RTX server records aggregate traffic through a shared ingress address, so these numbers describe that endpoint.

**Input-size trial.** Reproduce the two saved preview hashes on all 12 reviewed faces. Keep the crop byte-identical and use the production age and action prompts. Cap only the long edge of the marked scene at 640 px in place of 840 px. Use the installed Mac server's count-only endpoint for each pair. The 24 prompts per arm consumed **15,448 → 11,032 input tokens (28.6% fewer)**. One face already had a small enough scene and its count stayed the same. This measures the size of a model input. Throughput and the accuracy of generated observations at 640 px remain untested.

**Decision.** Retain the production preview size. All 12 reference faces passed the existing 12 px minimum at either size, but **3 of 24** previously completed faces in a separate, deliberately small-face sample shrank to 10 px on the marked scene. The floor protects the link between the close-up and the person acting in the scene. This sample measures a failure mode and cannot estimate its prevalence. The next candidate keeps the original scene whenever resizing would cross the floor. Before deployment it must pass a matched generation trial on reviewed faces, including crowded scenes and small actors, and the live peer gates. S5 stays open.

## Receipt to append for each trial

| Field | Record |
|---|---|
| Trial identity | Task ID, owner, UTC start/end, input cohort and version, affected callers, physical pool, reservation and freshness |
| Change | Hypothesis and declared gain, before/trial/rollback lanes, pass mode, model and prompt versions, closed baseline diagnosis |
| Per backend and caller | Unit, baseline/trial/recovery rates, durable counts, ready age, p95, errors, retries, pressure, sampled interval and no-progress deadline |
| Quality and publication | Reviewed denominator, stage/action or cricket event scores, abstentions, correction/duplicate checks, independent readback count and digest-match result |
| Decision | Observe only, hold, rollback or eligible. Record repeat order, recovery or selected allocation, private evidence reference and fixed-time Grafana links. |
| Follow-up | Date, outcome, failed gate if any, next smallest task and plan revision |

Retain the CLI run directory privately with the sealed prediction, comparison, traces, metrics, manifest and independent readback. Commit only aggregate results and references that can be shared. [Run file dictionary](https://github.com/homeiac/home/blob/b4a19672cd37301206a5487c8f2e192c34f75bb7/docs/guides/shared-workload-agent.md)


## Guarded generated-answer comparison

The follow-up screen kept original prompts, the close-up and serving configuration, alternating original-first and candidate-first by face. One serial test client per backend submitted through existing model slots alongside production. The cohort was the same twelve reviewed faces. An image below the 12 px face floor would keep its original scene. Cricket held inference idle during this test.

| Backend and scope | Reviewed stage matches, original → guarded | Supported whole action, original → guarded | Median client request seconds, original → guarded |
|---|---|---|---|
| RTX, 12 paired faces | 6/10 → 5/10 | 10/12 → 9/12 | 10.28 → 9.49 |
| Mac, first four paired faces | 3/4 → 3/4 | 3/4 → 2/4 | 33.77 → 35.19 |

**Reject the candidate.** The RTX stage score breached the quality gate. Stop the temporary test client early and retain the original input. Mac had completed four pairs and one further original reading, which is excluded. Visual review used each marked scene and its crop and judged the entire phrase, including actor attribution. The Mac candidate wrongly assigned a hand on the pink-shirted child's shoulder to that child. These are small, single paired screenings. They establish a failed promotion gate for this candidate. Request latency includes serving contention and cannot establish fleet throughput. S5 remains open. [Aggregate trial](../../../scripts/knowledge-index/library-server-timing.json)

The private run is guarded-face-quality.DW23pN. Baseline production workers continued. Coordinate a new baseline after the temporary clients finish before any further capacity trial.


## CPU readiness and diagnostic canary

Still-fawn's guest had about 20 GiB available memory and no listening model endpoint. Preparation reused the pinned Bonsai model/projector digests and the matching Linux release in a temporary directory, protected by a preparation lock. The first start exposed a missing OpenMP runtime. Extract that dependency into the temporary directory and retry. A second client attempt was refused by the exclusive server lock while the failed start was draining. The actual canary then ran one lane at two CPU threads with both GPU offload paths disabled.

This is a diagnostic sample, with a 650 s request timeout and automatic server cleanup. It uses the original full scene and crop and the unchanged production joint prompt on one reviewed face. Two threads is the probe configuration. The shared maximum and best setting remain unmeasured. The cricket chat will own the next CPU sweep after this request drains and a protected baseline and measured ceiling are established. No continuous CPU worker is qualified by this sample.


**Observed result.** The two-thread diagnostic completed one reviewed school-age face with the correct stage and a supported smile toward the camera. End-to-end including startup was 549.72 s. The runner spent 512.815 s on 1,043 input units and 26.555 s generating 47 output units. There was no cached prefix. This is about 0.11 faces/min for one diagnostic request. It cannot establish sustained throughput, broad quality, independent publication or the best CPU configuration.

The exclusive server process exited, its loopback port refused connections, and available guest memory returned to about 20 GiB. Temporary cached model/runtime files remain for reuse. The production photo completion count advanced from 49,774 to 50,103 over the monitoring interval, which also includes polling. Peer latency and errors were not qualified. CPU/memory pressure was observed during the run, then recent memory pressure declined. Cricket now owns the next CPU actuation and must measure a clean baseline, respect Whisper/pet/control-plane demand, derive the shared quota and test its measured maximum first. No continuous CPU lane was enabled. The reviewed payload and raw model answer remain in the local private trial receipt.
