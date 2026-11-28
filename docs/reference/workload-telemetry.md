# Workload telemetry fields

Applies to new adapters using `scripts/perf/workload.py review`. The two archived Waffles captures contain aggregate observations and use the historical replay CLI.

## IDs and joins

| Wire field | Scope and example | Rule |
|---|---|---|
| `service.name` | Trace resource · `cricket-indexer` | Originating workload; equals session `workload` and publication manifest `workload` |
| `host.name` | Trace resource · `mac` | Measured worker or serving host; one host per diagnostic window |
| `workload.run.id` | Trace resource · `cricket-replay-01` | One run and configuration. Equals manifest `run_id`. Many traces can share it |
| `traceId` | OTLP span · 32 hex digits | One distributed trace. Carry W3C trace context across the queue and writer |
| `spanId`, `parentSpanId` | OTLP span · 16 hex digits each | One operation and its immediate parent. Root has no parent. All-zero IDs are invalid |
| `workload.stage.id` | Span attribute · `classify` | Stable stage name declared with `--stage`; repeats across jobs and attempts |
| `workload.stage` | Span attribute · `job` or `accelerator` | Timing role consumed by the GPU rule. Mark the whole job and direct accelerator children. Overlapping child durations count once |
| `startTimeUnixNano`, `endTimeUnixNano` | OTLP span · decimal Unix nanoseconds | Review includes completed spans fully inside the selected window |

A retry keeps its logical job identity and gets a new span ID. A new trace for an asynchronous handoff can carry a span link. The GPU rule uses direct parent-child spans within one trace. [OTLP JSON encoding](https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding) · [W3C Trace Context](https://www.w3.org/TR/trace-context/#traceparent-header)

## Metric names and labels

| OTLP instrument | Type and unit | Measurement boundary |
|---|---|---|
| `workload.verified` | Monotonic sum, `{item}` | Count one durable, verified output at its owning stage and backend. Deduplicate retries at the ledger |
| `workload.stage.duration` | Histogram, `s` | Elapsed time for one stage attempt, including waits inside that stage |

Both instruments require exactly these **point labels**. They are the repo contract for new adapters. Existing dashboards also use producer-specific series.

| Label | Example | Allowed values |
|---|---|---|
| `workload` | `cricket-indexer` | Session workload |
| `stage_id` | `classify` | Same vocabulary as span `workload.stage.id` |
| `backend` | `mac-m5/bonsai-slots` | One of the session’s resolved serving or device pools |

On these metric resources, the checker allows only `service.name` and `host.name`. Filter automatic SDK resource attributes before this export. Keep trace IDs, span IDs, run IDs, media IDs and evidence pointers out of point labels. Report throughput as verified delta / window minutes and per-worker rate as verified delta / integrated ready-worker minutes.

## Diagnostic logs and existing metrics

| Source | Fields or selector | Interpretation |
|---|---|---|
| `worker.cycle` | `samples`, `cycle_s`, `processing_s` | Matched serial interval and processing time in seconds |
| `db.claim.plan` | `latency_ms`, `returned`, `sort_input_rows`, `order_keys` | Cost and shape of the eligible lookup |
| `worker.profile` | `samples`, `accelerator_stage_fraction` | Fraction of elapsed time in accelerator stages, 0–1 |
| `device.sample` | `utilization_pct`, `worker_present` | Device percent, 0–100, paired with worker presence |
| `knowledge_index_photo_stage_backend_completed` | `stage="library-face-observations"`, backend `mac-metal` or `rtx3070` | Unique newly saved face results in the library checkpoint. Compare deltas per backend. Publication and readback have a separate verification gate. |
| `knowledge_index_photo_stage_items` | Same stage, state pending/running/reused/withheld | Face occurrences. Use the stage-specific progress timestamp for freshness. A missing or stale series means unknown. |
| `cricket_workers` | `backend="mac", kind="active"` or `kind="desired"` | Current requests or configured lanes |
| `knowledge_index_caption_recovery_saved_per_minute` | `backend="Mac Metal"` | Published captions/min for the recovery stage |
| `waffles_worker_active_instances` | `worker="mac"` | Active worker processes |

Existing exporter labels are read by the [Prometheus adapter](../../scripts/perf/observe-shared-workloads.py). Use its source heartbeat to distinguish stale data from a measured zero. The review CLI consumes OTLP JSONL files before Prometheus name translation.

Service-only and inactive peers use the additional [peer measurement contract](shared-peer-measurements.md). Durable indexer counters remain unchanged.

## Deterministic adapters and completion objectives

All workload IDs now share warmed-window, sample-gap, minimum-completion, idle
reservation and workload latency/error checks. Declare service measurement kinds
explicitly; service objectives are reported separately from verified durable
outputs. Supply a [versioned adapter](workload-adapter-contract.md) for native data
and declarative observer mappings instead of editing a workload name into the
engine. Saved observer responses replay with an explicit cutoff and mapping/input
hashes.

Private attempt envelopes retain workload/run, hashed job/source-version/execution
IDs, immutable profile, mode, retained-stage/action flags, backend, purpose,
disposition and actual timing. Canonical IDs are preserved in their native store.
Combined latency comes from raw distinct production attempts, not mean backend
p95s. Replays/cache/withheld outputs do not create new production counters.

The single `completion_objective` binds fixed remaining work to baseline/trial
production and verified backend totals, durations and evidence references. Its
diagnostic ETA does not establish publication verification, semantic quality or a
causal CPU/GPU/memory bottleneck. `qualify-capacity` consumes the same projection
function and remains offline/not admitted while execution gates are pending.
