# Life-stage/action science journal

## Question: what happened when CPU inference was added?

The existing **four Mac Metal and three RTX lanes stayed running**. CPU trials used frozen evaluation faces. They did not claim new library jobs, and their answers do not count as production completions.

The table below projects the same **24,305 pending/running face jobs**, observed at **2026-11-27T23:40:05-08:00**, at each recorded baseline and during-trial production rate. This fixes the amount of work rather than confusing elapsed progress with a speed improvement. Withheld cases are outside that queue. These are historical diagnostic projections, not a live ETA or causal speedup estimate.

| Added Mac CPU | GPU production faces/min before → during | Projected remaining time before → during | Projected minutes saved | Shared completion objective |
|---|---:|---:|---:|---|
| Mac +10 CPU threads · joint | 25.99 → 26.58 | 15h 35m → 15h 14m | +21 | HOLD |
| Mac +6 CPU threads · joint | 25.99 → 27.39 | 15h 35m → 14h 48m | +48 | HOLD |
| Mac +7 CPU threads · two calls | 31.18 → 29.38 | 13h 00m → 13h 47m | -48 | HOLD |

The positive projections do **not** establish useful CPU production gain. GPU workload mix and controls varied, no new CPU production faces were published, and independent annotation publication/readback counts are unknown. The six-thread arm passed the measured workload budgets but had incomplete quality coverage. The ten-thread and seven-thread arms breached workload latency budgets. Keep the existing GPU allocation and CPU production lanes zero.

## Where was the bottleneck?

| Added Mac CPU | CPU requests measured | CPU model time processing prompt | CPU model time generating answer | Mac GPU faces/min before → during | RTX GPU faces/min before → during |
|---|---:|---:|---:|---:|---:|
| Mac +10 CPU threads · joint | 5 | 84.2% | 15.8% | 7.40 → 6.20 | 18.59 → 20.39 |
| Mac +6 CPU threads · joint | 4 | 86.4% | 13.6% | 7.40 → 6.40 | 18.59 → 20.99 |
| Mac +7 CPU threads · two calls | 4 | 91.0% | 9.0% | 7.99 → 6.59 | 23.18 → 22.78 |

**Measured slow stage inside the added CPU model: prompt processing.** Runner prompt timers account for 84–91% of its measured prompt-plus-generation time. This does not isolate the image encoder. These fractions cover all completed evaluation requests in each arm, including drain; their denominator differs from the fixed production-rate windows.

**Observed production symptom: Mac Metal throughput fell. Hardware cause: not established.** The saved GPU windows do not contain matched per-stage/device attribution sufficient to separate CPU contention, memory bandwidth, image processing or another cause. A no-CPU control also fell from 156 to 139 production checkpoints per five minutes. Neither utilization nor throughput alone proves a causal resource bottleneck.

## Query the evidence directly

[Existing timing evidence JSON](../../../scripts/knowledge-index/library-server-timing.json) contains `cpu_backfill_comparisons`. Each row has:

- `completion_objective`: fixed remaining work, original time bounds, production counts and backend breakdowns; CPU replays separate; unmeasured verified publication fields explicitly null.
- `completion_assessment`: the shared engine's exact decision, reasons, diagnostic rates, finish-time projection and objective fingerprint.
- `cpu_timing`: raw aggregate prompt/generation seconds, request denominator, scope and receipt reference; unknown causal attribution explicit.

[Runnable DuckDB query](../../../scripts/knowledge-index/cpu-backfill-comparison.sql) recomputes production rates and projected time from those counts and bounds, and returns measured slow stage, per-backend changes, unknown cause and the recorded shared completion verdict. It was checked against the engine's projection for all three trials.

From the repository root, with the existing Python DuckDB environment:

```sh
python3 - <<'PYQUERY'
from pathlib import Path
import duckdb
query = Path('scripts/knowledge-index/cpu-backfill-comparison.sql').read_text()
duckdb.sql(query).show(max_width=300)
PYQUERY
```

The computation is `remaining / (unique production count / window seconds)`, holding remaining work fixed. Positive `projected_minutes_saved` means a shorter projection. It is not proof of quality, publication or causation.

## Deterministic decision and provenance

The shared `completion_objective.project` engine produces the stored projection and HOLD reasons. Its source SHA-256 is bound in each row; its objective SHA-256 must match before the dashboard renders. Missing independent production readback and missing new CPU production contribution cause HOLD. The seven-thread trial additionally has no projected finish-time reduction. The existing qualification path still applies reviewed quality, workload/service budgets, original controls, repeats and ownership; the completion helper never admits a trial by itself.

This reporting change adds no second promotion gate or canonical annotation store. Native face IDs, the existing queue and OpenLABEL publication/readback architecture remain in place. No new inference was run. Full raw receipts and the remaining-queue snapshot stay in private local evidence; only aggregate observations are committed.

## Grafana

- [Throughput and projected remaining backfill time](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index?viewPanel=299)
- [Measured CPU stage and unresolved hardware cause](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index?viewPanel=300)
- [Selected production allocation](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index?viewPanel=298)

## Verification

The direct DuckDB query agrees with the shared projection engine for all three recorded arms. The generated dashboard and metrics suite passed all 44 checks. Flux applied report revision `008f5ad`; independent Grafana-served API readback returned version 89 and verified panels 299–300, including HOLD, the 84.2% stage fraction and explicit unresolved hardware causation. The source helper SHA matches every recorded assessment. No live CPU inference or admission was performed.
