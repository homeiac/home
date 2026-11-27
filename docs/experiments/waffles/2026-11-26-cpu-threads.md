# One model, more CPU threads

The continuous-production process sweep found that three extra Mac CPU processes
encountered sustained memory pressure. One extra process passed both repetitions.
Rather than duplicate more model weights, test intra-operation CPU parallelism
within one extra model. This is a separate experiment; do not pool its rates with
the process sweep or the interrupted CPU/Metal comparison.

Keep every admitted baseline worker running, including Mac Metal. Keep selected
still-fawn extra capacity processing production, if the previous experiment found
a valid selection. Change only the Mac extra process's thread count. A live policy
change drains/replaces that extra process, then warms it; it does not restart the
baseline. Report the actual PyTorch thread count from its heartbeat before running.

Source inspection found an important confound: although the previous adapter set
`OMP_NUM_THREADS=2`, pinned Ultralytics resets its detector's PyTorch thread count
to `min(8, cpu_count-1)`. Earlier process-sweep rows therefore are not verified
two-thread measurements. This phase explicitly configures that pinned selector
alongside PyTorch and the process environment before loading inference models.
It leaves weights, preprocessing, confidence threshold and baseline code unchanged.

Use 2 → 4 → 8 → 16 → 16 → 8 → 4 → 2 threads, one CPU process, the same frozen
122 photos, and six warm-up photos excluded from measurement. Reverse input order
in the second half. Sixteen threads are below the observed eighteen logical
CPUs, but this is not CPU affinity or a reservation for other work; library and
runtime threads may add concurrency. Low scheduling priority remains. This is a
test bound, not a claim that sixteen is optimal.

Require two valid repetitions, at least 9/13 Waffles matches, zero of 13 false
positives, unchanged binary decisions, one attempt per photo, and no process
crashes or newly unhealthy workloads. Retain the existing memory/thermal guards.
If quality or resources fail, record the failed attempt and restore previous extra
settings. Never pause production. Select the fewest threads within 5% of the
fastest eligible pooled rate, recording both repetitions and whole-Mac CPU/GPU,
memory, swap and production deltas. Do not call a higher CPU percentage a win
unless completed throughput improves while quality passes.

Preregister this protocol and runner before executing `thread-experiment.py`.
All photos and asset identifiers remain outside Git; aggregate observations and
failed attempts belong in `2026-11-26-cpu-threads.jsonl`.

## Amendment: reduced Rancher allocation and observed warnings

After the first attempt stopped before measurement, the owner requested reducing
Rancher Desktop and explicitly authorized starting jobs despite warning pressure.
Rancher's VM allocation changed from 24 GiB to 8 GiB; all 14 previously healthy
local Kubernetes workload owners and the Dagger container recovered. Waffles'
native Mac baseline and homelab workers remained unchanged.

Run a new session with `--allow-memory-warning`. Record macOS level 2 as an
observation, allowing startup and continued inference. Level 4 critical pressure,
unknown pressure/probe failure, process crashes, baseline unavailability and
recognition failures remain stop conditions. The Mac-specific worker guard and
experiment now agree on this policy. Linux worker guards are unchanged.

Keep the frozen sample, classifier, trial order, two repetitions and quality
criteria unchanged. Record this amendment in protocol metadata. Earlier warning
rejections remain in the append-only journal; they establish neither an optimal
Mac concurrency nor a demonstrated memory capacity failure. Do not pool results
across the changed Rancher allocation and warning policy.
