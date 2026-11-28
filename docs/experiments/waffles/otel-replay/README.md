# Waffles diagnosis replay · November 27, 2026

## What the loop selected

The selector read one ten-minute window per decision. It received only the attributes listed below and no outcome file, action label, device-client name or after measurement. We recorded and reported the following prediction checksums before invoking a separate scorer. The underlying incidents and their resolutions were already known when we wrote the rules. This retrospective checks their behavior and the diagnostic evidence boundary. Estimating accuracy on new incidents requires independent cases.

| Case and UTC cutoff | Evidence available at the cutoff | Selected trial | Registered check |
|---|---|---|---|
| Queue, 06:56:20 | 67 Mac baseline intervals. Mean cycle 2.598 s, processing 0.378 s. A successful candidate SELECT took 1,661.587 ms, sorting 54,406 eligible rows to return one in run creation and job ordinal order. | Canary an indexed ready FIFO preserving eligibility, ordering, leases and retries. | The successful candidate SELECT must at least halve in duration and eliminate the backlog sort. |
| Mac GPU, 18:27:35 | Two warmed passes of 26 matched photos spent 97.50–97.52% of wall time in Metal-backed detection and embedding. Two whole-host samples about ten seconds apart showed 100% device activity with the benchmark worker absent. | Inventory other device clients, isolate one candidate, replay matched inputs and a CPU control, restore the candidate and repeat. The data available at the cutoff identify no individual process. | The isolated Metal rate must beat both adjacent phases by at least 10%. The CPU control must gain less proportionally. Binary decisions must agree and the original process must resume and pass its health check. |

The prediction receipts contain the evidence checksum, the selector source checksum, the cutoff, the exact action and its numeric gates. Their checksums are reproducibility checks. [Queue receipt](queue.prediction.json) · [GPU receipt](gpu.prediction.json)

## Held-out observations

| Case | What happened | Interpretation |
|---|---|---|
| Queue | The successful SELECT fell from 1,661.587 to **0.286 ms**, with **zero rows sorted**. Fleet commits rose from 157.3 to 434.0 photos/min in the accompanying three-minute windows. | The indexed lookup passed the registered check. The SELECT excludes locking and updating. Input mix and concurrency could affect the fleet comparison. Lease parity, ordering under retries and output quality were outside this measurement. |
| Mac GPU | Metal delivered **345.5 → 627.1 → 374.9 photos/min** across running, paused and restored phases. CPU delivered 501.0 → 519.4 → 387.8. All 52 decisions per variant agreed on 26 distinct photos. The original competing process resumed and passed its HTTP health check. | Temporary isolation increased Metal throughput by **81.5%**, versus **3.7%** on CPU. One A/B/A cycle supports co-tenant interference. Pausing the process changed both CPU and GPU load. |

Both mechanism checks passed. Neither experiment measured the impact of a permanent placement policy on every tenant. [Queue study](https://github.com/homeiac/home/blob/d21253f8b0af575cc617d9726895de5aff5c1080/docs/experiments/waffles/2026-11-26-fifo-before-after.md) · [Matched-worker study](https://github.com/homeiac/home/blob/3a4c900272b8937304d16fdc67a9e936bf8f5307/docs/experiments/waffles/2026-11-27-matched-worker-analysis.md)

## Repeat the separation

Run from the repository root. Choose a fresh output directory so previously registered predictions cannot be overwritten.

```sh
receipts=$(mktemp -d)
data=docs/experiments/waffles/otel-replay
predict=scripts/perf/otel_diagnosis.py
score=scripts/immich-pet-tagger/per-worker/score-diagnosis-replay.py

python3 "$predict" "$data/queue.otlp.jsonl" --as-of 2026-11-27T06:56:20Z --seal "$receipts/queue.json"
python3 "$predict" "$data/gpu.otlp.jsonl" --as-of 2026-11-27T18:27:35Z --seal "$receipts/gpu.json"

# Inspect both predictions here. Only these next commands open the held-out measurement files.
python3 "$score" queue "$receipts/queue.json"
python3 "$score" gpu "$receipts/gpu.json"
```

The queue packet projects the before-only bottleneck capture at 06:56:19 UTC from source revision `684e300`. The GPU packet projects the archived `mac-mps-serial-repeat` passes from revision `3511a2c` and two timestamped host observations. Aggregate observations use their report timestamps. These historical runs predate end-to-end tracing. OTLP log records carry the original measurements for replay. The integration test separately exercises the span path with real SDK encodings and controlled stage timings. No Waffles spans were synthesized. The scorer reads bundled aggregate observations projected from the queue outcome at revision `d21253f` or the restored A/B/A at `3a4c900`. [Projection script](../../../../scripts/immich-pet-tagger/per-worker/export-diagnosis-replay.py) · [Host observations](../2026-11-27-gpu-backtest-snapshots.json) · [Regression tests](../../../../scripts/perf/tests/test_otel_diagnosis.py)
