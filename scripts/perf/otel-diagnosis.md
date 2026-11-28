# Deterministic OTel diagnosis

The selector reads a completed capture at an explicit UTC cutoff. It returns a next probe or a trial proposal. The streaming driver runs it again as an adapter closes each new window. Supply additional telemetry from the requested probe in the next capture. The driver also returns a separate fleet review. Without peer measurements the driver reports `observe_only`. The commands operate on local captures and emit decisions. [Replay on both Waffles incidents](../../docs/experiments/waffles/otel-replay/README.md)

## Workload adapter

Emit one OTLP JSON request per line. Set resource attributes `service.name` (the originating workload), `host.name` (the measured backend) and `workload.run.id` (one comparable cohort, configuration and device). Keep this scope constant in each diagnostic capture. Give co-tenant window data to the separate fleet review. The two rules currently consume the following events from `resourceLogs`.

| OTLP eventName | Scalar attributes | Measurement |
|---|---|---|
| `worker.cycle` | `samples`, `cycle_s`, `processing_s` | Mean completion interval and mean processing duration from the same serial worker window |
| `db.claim.plan` | `latency_ms`, `returned`, `sort_input_rows`, `order_keys` | A timed plan for an eligible lookup and the rows entering the sort implementing its queue order |
| `worker.profile` | `samples`, `accelerator_stage_fraction` | Matched serial passes, fraction of elapsed time spent in accelerator-backed stages |
| `device.sample` | `utilization_pct`, `worker_present` | Simultaneous host-device and process-lifetime observation |

A trace adapter can supply the stage fraction directly from `resourceSpans`. Label completed root spans with `workload.stage=job` and their direct timed accelerator-backed children with `workload.stage=accelerator`. Use complete job samples with the relevant children instrumented. The selector joins IDs and takes the union of overlapping stage intervals. This measures stage wall time, including synchronization. Device kernel time needs a separate profiler. Keep log and span profiles in separate captures when they summarize the same jobs. Publish closed capture files atomically. For historical replay use evidence archived by the cutoff; a span end timestamp alone cannot establish when the collector first received it.

Use the single-capture CLI to register an immutable-by-default prediction. Use the JSONL driver for successive windows. Each input line has a capture path and an explicit cutoff in nanoseconds. Each output line contains `diagnosis` and `fleet_review`, or identifies an invalid checkpoint. The driver does not start or stop processes.

```sh
python3 scripts/perf/otel-diagnosis-loop.py <<'JSONL'
{"capture":"docs/experiments/waffles/otel-replay/queue.otlp.jsonl","as_of_unix_ns":"1795762580000000000"}
{"capture":"docs/experiments/waffles/otel-replay/gpu.otlp.jsonl","as_of_unix_ns":"1795804055000000000"}
JSONL
```

## Shared serving and compute

Use `observe-shared-workloads.py` for a read-only Prometheus snapshot. Set `activity_capture` in a checkpoint to its saved path. Observations are checked against that checkpoint's watermark and source heartbeat. Pass an optional `topology` object for other installations. It maps each logical or physical resource to `workloads` and underlying resources in `uses`. Include each resource the knob affects. Changing Mac Bonsai slots traverses the serving pool and its underlying Metal device. On that device, Waffles is a potential direct client even when absent from Bonsai's caller list. [Default topology](shared-workloads.json)

For a measured canary, add `comparison` to the checkpoint. Supply:

- `subject` equal to the diagnosed service, the affected `resources`, and predeclared fractional `min_gain` and `max_peer_loss` budgets.
- `baseline` and `trial`, each with integer `start_ns` and `end_ns`, an `environment` fingerprint of the fixed configuration excluding the trial knob, and `callers` keyed by resource. Supply a complete caller census per resource, including callers outside the registry. An empty array denotes observed absence. Count callers at the server with propagated identities and at the device with process attribution. Omit an unavailable census to withhold a decision.
- Each window's `workloads` entry for every declared or observed caller. Include observed `demand` and whether the original baseline allocation was preserved. For an active workload add `verified` output for the whole window, `unit`, matched offered-work `cohort` and boolean `quality_ok` and `slo_ok` from that workload's independent checks. Do not infer quality from an HTTP success or from the other workload's labels.

`eligible` means a measured candidate cleared these checks. The production owner still applies its repeated-window and minimum-sample policy. `rollback` ends a losing increment. `hold` withholds a decision when evidence is missing or incomparable. A faster Cricket trial with declining Knowledge Index throughput is covered by the regression tests. The Prometheus observer supplies partial activity evidence. The deployment still needs complete caller identity propagation and workload-specific quality inputs to supervise live promotions. [Executable examples](tests/test_shared_workloads.py)

For Cricket, both windows must be warmed (`warmed: true`), at least 300 seconds long and sampled at intervals of at most 15 seconds (`max_sample_gap_s`, including window boundaries). Report integer `completed_items` separately from `verified` source minutes. Each continuously backlogged workload needs ten durable completions per window. Active peers also report `p95_s` and `terminal_error_rate` (errors per attempt). The default gate preserves at least 90% of peer throughput, limits p95 growth to 10% and permits no increase in terminal-error rate. Tighter declared service budgets remain in force. If monitoring fails during a running canary, the owner drains the trial increment and verifies recovery. [Shared-indexer tuning procedure](../../docs/runbooks/shared-indexer-tuning.md)
