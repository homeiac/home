# Waffles live concurrency experiment

Protocol recorded at 2026-11-27 04:48 UTC, before the live-concurrency trials.
The machine-readable journal is `2026-11-26-live-tuning.jsonl` in this directory.
Earlier distributed and frontier results are retrospective evidence, not
preregistered results of this protocol.

## Question and hypotheses

How far can concurrency increase completed throughput without changing recognition
quality or exceeding the resource envelope?

- Mac: 2 or 4 independent Metal processes may overlap thumbnail fetching and
  preprocessing better than one, but GPU and memory-bandwidth contention may erase
  the gain.
- still-fawn: 2 processes within the same two-core, 3 GiB pod limit may improve
  overlap, or simply compete for the same CPU budget.
- The fastest individual configurations may not deliver the same proportional
  improvement when combined with PVE because the queue, thumbnail source and
  single Immich writer are shared.

## Fixed inputs and controls

Use the frozen 96-photo chronological sample plus the 26 owner-reviewed holdouts,
deduplicated by asset ID. Record the final count and SHA256 in the journal. Keep
the fitted classifier snapshot, 0.90 threshold, YOLO confidence, model versions,
and resource limits fixed. Private asset IDs and model inputs stay outside Git.

Pause production claims during measured trials and drain in-flight work. Model
processes must be ready before warm-up and measurement. Warm-up performs fresh
inference and is excluded from timing. Benchmark mode does not write Immich faces.
The original Mac caption workload and unrelated services remain unchanged and
are recorded as possible background-load confounders.

Run Mac slots 1 → 2 → 4 → 4 → 2 → 1 and still-fawn slots 1 → 2 → 2 → 1. Reverse
the sample order in the second half. Then compare the original three-backend
configuration with the selected configuration in matched before/after passes.
Record any deviation and its reason before interpreting results.

## Acceptance criteria

1. Every measured job completes, with no exhausted retries or model errors.
2. All binary Waffles decisions agree with the frozen one-process baseline on
   the exact sample. The reviewed holdouts must retain at least 9/13 positives
   and 13/13 negatives; no new false positives are allowed.
3. No worker OOM, unplanned restart, or resource-limit change occurs during a
   valid measurement. Native host thermal/memory guards remain enabled.
4. Measure wall time from run start to last committed result, not observer poll
   completion. Report combined throughput, per-job latency, backend distribution,
   memory high-water marks and available CPU/memory telemetry.
5. Select the highest valid repeated throughput. If configurations differ by
   less than 5%, prefer fewer processes. If repetitions disagree materially,
   report the ambiguity rather than claiming a precise gain.

On failure, pause the affected trial, drain active work, restore the last known
good concurrency and record the failure. Always resume the previously running
production queue after the experiment, including on interruption or exceptions.

## Known limits

This sample is selected and small. It can detect regressions against the known
examples but cannot establish library-wide accuracy. Measurements include
thumbnail I/O and inference. Benchmark timings exclude production face/tag writes.
Memory telemetry is a process high-water mark and may not include every Metal
allocation. More processes do not imply proportionally more compute capacity.
