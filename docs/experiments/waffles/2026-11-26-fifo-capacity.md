# Indexed FIFO and Mac capacity protocol

Registered before deployment on November 26, 2026 (Pacific). Issue #244.

The old claim joins and sorts the entire eligible backlog and serializes baseline and extra claims under one backend lock. The replacement resolves the small run list first, then selects the first ready ordinal using a partial ordered index. Baseline and extra pools retain independent transactional caps and fencing. Expired leases return to the ready queue in a bounded recovery batch every 15 seconds; attempts remain limited to four. Ready FIFO intentionally skips delayed retries and rows locked by another claimant. Completion order is not FIFO with concurrent workers.

Before deployment: private PostgreSQL dump verified with a full archive read; isolated PostgreSQL tests cover caps, unique claims, expired fencing, delayed retries, exhausted inference/write attempts, baseline continuity, and an 80,000-row backlog. The scratch candidate took 0.039 ms with an ordered index and no backlog sort. This is not an end-to-end production result.

Use `scripts/immich-pet-tagger/bottleneck-report.py capture LABEL --directory PRIVATE_DIR` before and after a deployment. Capture after at least three minutes of uninterrupted production to avoid mixing rollout intervals into the window. `compare BEFORE.json AFTER.json` reports the same quantities and their interpretation limits. The report is read-only; native profiling is opt-in with `--sample-mac`. Captures cannot overwrite an existing label.

The schema-v5 GitOps rollout briefly restarts the queue and extra Kubernetes pods. Permanent baseline processes are preserved; in-flight jobs retain lease fencing. Do not characterize the API rollout as uninterrupted processing. Verify all admitted baseline pools resume production before starting any measurement.

Mac capacity experiment: keep its one Metal baseline and all other admitted baseline workers running. Keep still-fawn's adopted two CPU extras serving production. Compare Mac CPU extras (two threads per process) at 2, 4, 8, 12, 15 processes and Metal extras at 1, 2, 4, 8, stopping escalation within a device only on a critical resource failure, crash, failed quality gate, or two consecutive throughput regressions. Warning memory pressure is recorded, not a stop condition. Repeat each eligible setting on the frozen 122-photo canary in opposite order after warmup. Same classifier and thresholds, at least 9/13 positives, zero of 13 negative controls, all 122 binary decisions identical, no retries or process crashes. These small controls do not establish library-wide precision.

Select the fastest repeated quality-valid setting, then verify sustained production for two minutes with all admitted baselines advancing. Keep the existing three-worker configuration as fallback. Record every request, convergence, resource observation, failed/skipped trial, quality result, and final adoption in the append-only FIFO capacity JSONL. No RTX or unrelated Mac workloads are changed.

## Protocol amendment before measured capacity trials

At 23:01 Pacific, the initial attempt stopped before any measured trial because
fun-bedbug's native capacity guard unloaded its model. The journal retains this
attempt and restoration to the original two CPU extras. Its supervisor remained
active, desired capacity one, and immediately retried model loading. This is a
protected native-host availability event, not evidence against Mac capacity.

The amended Mac experiment requires Mac/PVE/still-fawn baselines to stay ready and
advance; fun-bedbug and chief-horse retain desired baseline one and their unchanged
host guards. Native availability and counts remain in every resource observation.
Only Mac unexpected exits invalidate Mac process stability; native guard cycles
are recorded separately. No claim of uninterrupted processing on a guarded native
host is made. The stable diagnostic window similarly requires the three main
backends and unchanged extra policies.

## Production-first supersedes canary diversion

The owner stopped the sweep after repeated valid 2-, 4-, and 8-extra CPU trials.
Eight CPU extras plus the permanent Metal process became the production floor.
The controller completed no 12-extra measurement and no new Metal-extra trial.
The original interrupted journal is retained. `mac-capacity-experiment.py` is now
retired for execution because it diverted working production capacity to canaries.

`production-capacity.py` raises production extras to 12, then 15, and measures two
real-work windows at each level. It never changes a run to benchmark mode or pauses
production. A fresh recorded production observation may supply the starting rate.
Raised capacity remains in place when measurement is interrupted or a diagnostic
fails; reduction requires negative evidence (both windows below 90% of the prior
accepted rate, a process crash, critical pressure, or lost worker). Warning pressure
is recorded and does not trigger reduction. The CPU device, two-thread setting,
classifier and thresholds are unchanged. Higher concurrency gets operational
validation, not a fabricated new labeled-accuracy result. Native host guards remain
independent and all other worker policies are untouched.
