# Life-stage/action scaling checklist

**S1 is next.** Capture a closed baseline window with per-backend face completions, publication readback and all active or scheduled peers. The existing backfill and the November GPU comparison establish the starting point. Photo-plus-cricket capacity still needs a live trial.

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
| [ ] | [ ] | S1 | Closed baseline census and ledger-to-Grafana comparison | Snapshot and historical trial above. Reservations, peer freshness and same-window rates still needed. |
| [ ] | [ ] | S2 | Both pool routes, physical device census, trace through writer, bounded per-caller counters | Current shared registry has knowledge indexing. Distinct photo life-stage/action still needs end-to-end verification. |
| [ ] | [ ] | S3 | Media manifest versus independent PostgreSQL readback, retry, correction and owner collision tests | Shared writer contract exists. A live photo run receipt is outstanding. |
| [ ] | [ ] | S4 | Both subjects exercise sampling, minimum counts, p95/error and rollback gates. Grafana matches the measured windows. | Strict defaults currently branch on the cricket subject. |
| [ ] | [ ] | S5 | Matched photo canary, paired quality scores, reverse-order repeat and per-backend decisions | Historical pass-count trial is available. Full fleet comparison remains open. |
| [ ] | [ ] | S6 | Joint run with real cricket backlog, separate output units, independent readback and every peer within budget | Cricket journal records a pilot. It does not establish the capacity of this mix. |
| [ ] | [ ] | S7 | Promotion record for a named workload mix, expiry, restart/rollback and verified recovery | Await S5 and S6 evidence. |

[Shared reviewer](https://github.com/homeiac/home/blob/b4a19672cd37301206a5487c8f2e192c34f75bb7/scripts/perf/shared_workloads.py) · [Cricket pilot journal](https://github.com/homeiac/home/blob/b4a19672cd37301206a5487c8f2e192c34f75bb7/docs/experiments/cricket/science-journal.md)

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
