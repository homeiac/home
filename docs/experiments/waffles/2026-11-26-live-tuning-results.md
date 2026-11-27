# Waffles live tuning results — interrupted

See the [preregistered protocol](2026-11-26-live-tuning.md) and [append-only journal](2026-11-26-live-tuning.jsonl).
Times are UTC. These are warm benchmark results on 122 fixed photos, including 26 reviewed holdouts. Benchmark runs do not write Immich faces.

| Trial | Photos/min | Wall seconds | Mean seconds/photo | P95 seconds | Waffles / 13 | False positives / 13 | Changed decisions | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| tune-1127045925-mac-1-a | 114.04 | 64.189 | 0.315 | 0.453 | 9 | 0 | 0 | True |
| tune-1127045925-mac-2-a | 310.34 | 23.587 | 0.260 | 0.417 | 9 | 0 | 0 | True |
| tune-1127045925-mac-4-a | 413.26 | 17.713 | 0.342 | 0.649 | 9 | 0 | 0 | True |
| tune-1127045925-mac-4-b | 751.85 | 9.736 | 0.221 | 0.354 | 9 | 0 | 0 | True |
| tune-1127045925-mac-2-b | 319.01 | 22.946 | 0.239 | 0.398 | 9 | 0 | 0 | True |
| tune-1127045925-mac-1-b | 142.45 | 51.387 | 0.264 | 0.418 | 9 | 0 | 0 | True |
| tune-1127045925-still-fawn-1-a | 75.98 | 96.337 | 0.548 | 0.730 | 9 | 0 | 0 | True |
| tune-1127045925-still-fawn-2-a | 100.36 | 72.934 | 0.973 | 1.349 | 9 | 0 | 0 | True |

## Selection and repeatability

- mac: selected 4 process(es), using the preregistered 5% preference for fewer processes.
  - 1 process(es): pooled 126.67 photos/min; fastest/slowest repetition spread 24.9%.
  - 2 process(es): pooled 314.62 photos/min; fastest/slowest repetition spread 2.8%.
  - 4 process(es): pooled 533.35 photos/min; fastest/slowest repetition spread 81.9%.

## Resource observations

Values below are snapshots after each pass. Process RSS is the sum of process high-water marks, not current memory, and may exclude Metal allocations. Swap is system-wide and includes unrelated applications. Kubernetes CPU values average the preceding minute; working-set values are snapshots, not measured peaks.

| Trial | Mac process peak RSS, GiB | still-fawn working set, GiB | still-fawn CPU cores | Mac swap used, GiB |
|---|---:|---:|---:|---:|
| tune-1127045925-mac-1-a | 1.88 | 1.04 | 0.00 | 15.62 |
| tune-1127045925-mac-2-a | 3.64 | 1.04 | 0.00 | 15.62 |
| tune-1127045925-mac-4-a | 6.49 | 1.04 | 0.00 | 20.38 |
| tune-1127045925-mac-4-b | 6.49 | 1.04 | 0.00 | 20.36 |
| tune-1127045925-mac-2-b | 3.64 | 1.04 | 0.00 | 20.20 |
| tune-1127045925-mac-1-b | 1.88 | 1.04 | 0.00 | 20.16 |
| tune-1127045925-still-fawn-1-a | 7.01 | 1.05 | 1.18 | 20.04 |
| tune-1127045925-still-fawn-2-a | 7.01 | 2.04 | 1.76 | 20.03 |

## Deviations, failures and observations

- 2026-11-27T04:59:09.876065+00:00: Initial execution aborted before any measured trial: the production drain check counted three expired rollout leases as active. Cleanup restored both production runs at 04:58:59 UTC. Corrected preflight to count only unexpired leases; stale claims remain recoverable on production resume. Sample, trial order and quality criteria unchanged. Added Mac host memory-pressure and swap observations.
- 2026-11-27T05:00:37.130779+00:00: During the first Mac baseline, a dashboard-only commit restored node-frame joins after a display-formatting regression. No inference code, model, queue configuration, worker processes, resource limits or experiment criteria changed. Browser verification and ordinary desktop activity remain background-load confounders.
- 2026-11-27T05:10:17.804355+00:00: User changed the operating constraint: retain baseline production workers on every node throughout tuning. Interrupting the pause-based protocol, preserving its completed trials as preliminary evidence, and restoring production. Subsequent trials require a new continuous-production protocol and separate worker lanes; do not combine their results with this isolated sweep.
- 2026-11-27T05:10:17.900795+00:00: Experiment interrupted

## Interpretation limits

Two repetitions per configuration provide a directional result, not a confidence interval. Background desktop activity, source I/O and shared-host load can vary. The journal includes CPU, memory, swap and process observations before and after each pass. A selected sample of 13 positive and 13 negative dogs cannot establish library-wide precision or recall. Production throughput also includes Immich writes.

The user interrupted this protocol to require continuous baseline workers on all nodes. Production was restored at one worker per admitted backend. The combined ABBA comparison was not run; no final combined gain or completed-study selection is claimed.
RTX remained unused. Subsequent continuous-production measurements belong to a separate protocol.
