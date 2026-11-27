# Waffles tuning with continuous production

This supersedes the operating conditions of the interrupted
[isolated experiment](2026-11-26-live-tuning.md). The user requires a baseline
production worker on every node throughout tuning. Earlier isolated results
remain preliminary evidence and must not be pooled with this experiment.

## Invariants

- Keep one baseline production process on each admitted backend. Mac uses Metal;
  still-fawn, PVE and the native Linux hosts use CPU. RTX remains unused.
- Baseline services remain separate from additional worker services. Experiment
  cleanup may drain extra workers and pause benchmark runs, never production.
- Chief-horse remains a desired baseline on guarded standby until sufficient
  memory is available and its quality evaluation passes. Do not silently relax
  the guard or claim it is processing while it is not.
- Freeze the same 122 photos and classifier snapshot. Retain the 26 reviewed
  holdouts and compare every decision with the first valid one-process baseline.
- Keep recognition thresholds fixed. Require at least 9/13 positive matches,
  zero of 13 negative matches, unchanged binary decisions, no retries or worker
  crashes. Failed trials and protocol deviations remain in the journal.

## Questions

1. How much additional throughput do 1, 3, 5 and 7 extra Mac processes deliver
   while its baseline process continues production? Repeat in reverse order.
2. On still-fawn, how much does additional CPU capacity help while its baseline
   pod continues production? Evaluate a separate CPU worker pod so its allocation
   adds to, rather than replaces, the existing two-core baseline limit.
3. Where do memory pressure, accelerator saturation, shared-source I/O or CPU
   contention make further processes ineffective?

Record CPU utilization and Apple GPU utilization separately; a lightly used CPU
does not establish that a Metal worker has spare accelerator capacity. Reuse the
existing Mac experiment's `ioreg` GPU observation and macOS memory-pressure guard.
Record per-process accelerator allocations, host swap and CPU/thermal conditions.

## Interpretation

The frozen benchmark measures additional-worker throughput under live production
load. Production throughput is recorded separately because historical photos are
not the same inputs in every window. Do not add repeated benchmark completions
to historical-backfill progress. Report paired ranges and resource costs, and
prefer fewer workers within 5% of the fastest eligible repeated configuration.
Higher CPU allocations must have their own recorded settings and warm-up.

## Preregistered schedule and resource gates

The user explicitly approved comparing CPU-only and Metal extras. For each of
1, 3, 5 and 7 extra Mac processes, test CPU then Metal, then repeat the entire
sequence in reverse. Reverse photo order in the second half. A permanent Metal
baseline continues production. Each process requests two OpenMP/BLAS threads, matching
the existing adapter. At most eight model processes run in this initial sweep;
the 15-extra safety bound is not a tested recommendation.

Drain Mac extras before the still-fawn sweep. Hold two extra processes fixed and
test 1 → 2 → 3 → 3 → 2 → 1 CPU-affinity lanes within the extra pod's three-core
ceiling. Baseline still-fawn retains its existing two-core ceiling throughout.
Combined ABBA compares one extra Mac Metal process plus one extra still-fawn
process on one lane against the selected repeated configurations. These results
measure additional capacity under live production, not a baseline-only speedup.

Warm each configuration on at least six photos (three per extra process), then
measure all 122. Choose among configurations with two valid repetitions by pooled
photos/minute, preferring fewer processes/CPU lanes within 5% of fastest. Report
both repeat rates. No guarantee of increasing throughput is assumed.

Sample resources at least every 15 seconds and at trial boundaries. Require all
four admitted baseline workers ready. Stop extras if macOS memory pressure reaches
critical (4) or stays at warning (2) for six seconds, still-fawn host temperature reaches 68°C or thermal telemetry is
missing, host available memory falls below 512 MiB, queue health fails, or a
previously healthy still-fawn workload becomes unready/restarts. A preexisting
unready Frigate IP webhook is recorded but is not attributed to this experiment.
Guest memory was independently observed at 18.5 GiB available; hypervisor available
memory alone excludes the VM's existing allocation. Record host PSI, CPU ticks,
swap, Mac CPU/GPU utilization and production progress; do not hide resource costs.

A convergence deadline of six minutes and a measured-run deadline of fifteen
minutes bound each trial. A failed quality/resource gate aborts the experiment,
restores original extra capacity, and retains failure evidence. No production
state changes or baseline restarts are allowed in the runner or cleanup.

These settings and code must be committed before execution. This preregistration
does not claim that the new trials have run.

## Amendment before measured trials, 05:35 UTC

The first attempt was interrupted to investigate three production failures:
existing VIDEO assets returned preview-thumbnail 404, while asset metadata was
available. They remain failed and are not counted as successful classifications.
The second attempt stopped during Metal model startup on one OS warning sample,
before any measured trial finished. The deployment already uses a six-second
sustained-warning guard. Align the experiment with that rule, sample warning
follow-ups every two seconds, retain each observation and stop critical pressure
immediately. New processes still refuse startup outside normal pressure. Start
with CPU then Metal at each concurrency, and reverse the complete order for the
second pass. Prior attempts remain in the journal; no completed result is reused.

The owner clarified that warnings should not interrupt work when they concern
Immich 404s or similar per-photo failures. Production jobs already have a four-
attempt bound and 30-second retry delay; retain failed status and continue other
assets. Never pause the experiment just because an unrelated historical asset
lacks a thumbnail. A missing input in the frozen evaluation set still makes that
trial invalid, rather than silently reducing its denominator. This clarification
does not remove memory or quality safeguards.

## Resource-limited follow-up

Session `1127054012` completed one valid CPU pass (260.3 photos/min, 9 true
positives, zero false positives, unchanged decisions). The extra Metal process
then unloaded under sustained memory pressure, before its measured pass completed.
Earlier Metal startup attempts also encountered pressure. Do not relax safeguards
or claim a device speedup from that incomplete comparison. Existing baseline
Metal remains available and production stays running.

Continue with `--devices cpu` and an explicit protocol note: repeat all CPU cells
1 → 3 → 5 → 7 → 7 → 5 → 3 → 1 with fresh run IDs, followed by the still-fawn
CPU-lane sweep. The first CPU pass above is not pooled with this follow-up.
A resource-rejected configuration is attempted once; record the failure, drain
extras, and skip that capacity and larger capacities on that device. Resume lower
eligible repeated cells after pressure returns to normal, bounded by two minutes.
Quality failures and unhealthy baseline/host workloads still abort the experiment.
Combined ABBA uses one extra **CPU** Mac worker and one extra still-fawn worker as
before; selected eligible extra capacity is after. Missing Immich assets continue
to use the independent four-attempt per-asset policy.

## Thread-count provenance correction

Subsequent source inspection found pinned Ultralytics calls
`torch.set_num_threads(min(8, cpu_count-1))` when selecting CPU or MPS. The process
environment requests above therefore do not prove that every detector ran with
two threads. No actual thread-count claim is attached to these process-sweep
results. The separate [one-model thread protocol](2026-11-26-cpu-threads.md)
controls that selector explicitly on Mac CPU extras and validates it at
2, 4, 8 and 16 threads before measuring. Existing Linux behavior stays unchanged.
