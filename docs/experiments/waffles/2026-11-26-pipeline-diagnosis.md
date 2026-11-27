# Why still-fawn looks competitive with the Mac

The strongest demonstrated bottleneck is getting work from the queue. The Mac's
Metal worker spends most sampled main-thread time waiting for HTTPS responses,
and a read-only execution of the queue's candidate selection took roughly half
a second while scanning and sorting about 61,000 eligible jobs. Faster model
execution cannot accelerate that database wait.

The owner requested diagnosis only, then separately requested increasing the Mac.
The only capacity change during this diagnosis was that explicit increase: Mac
now has one unchanged Metal baseline plus two CPU production workers at the
quality-valid two-thread setting. still-fawn has one baseline plus two CPU extras.
The automatic thread sweep was interrupted so it cannot overwrite this policy;
its two completed cells both retained 9/13 Waffles matches, zero false positives
and unchanged decisions. Neither configuration is claimed as a completed optimum.
No queue query, index, lock, client transport or recognition setting was changed.

## Evidence collected while jobs ran

Times below were observed around 22:24–22:29 Pacific on November 26, 2026.
The [aggregate evidence](2026-11-26-pipeline-diagnosis.json) contains no photo IDs,
images, credentials or raw stack traces. Raw samples remain in private temporary
storage. All original baseline process/pod identities remained unchanged.

| Observation | Mac Metal baseline | still-fawn CPU baseline |
|---|---:|---:|
| Mean thumbnail + detection + embedding + classification | 0.3755 s | 0.6795 s |
| Mean interval between committed results | 0.9854 s | 1.2797 s |
| Small read-only queue request median | 18.1 ms over HTTPS | 12.2 ms over in-cluster HTTP |

These are recent production samples with different photos, not a controlled
hardware benchmark. The processing timer includes thumbnail fetching and CPU
preprocessing, and excludes claiming and finishing the job. Completion intervals
also reflect scheduling and the independent Immich writer. Their difference is
useful evidence of pipeline overhead, not an exact exclusive timing breakdown.

A ten-second native `sample` trace of the existing Metal process produced 825
main-thread samples. Across all main-thread branches, 580 (70.3%) were within
HTTPS socket reads, 35 (4.2%) within TLS handshakes, and 145 (17.6%) within Python
condition waits used by the asynchronous model workers. The first inspection
counted only the largest HTTPS branch (473, 57.3%); the full-branch count is 70.3%.
These stack categories are not GPU utilization percentages. HTTPS waits include
both queue and thumbnail response paths; the stack alone cannot name the endpoint.

The Mac's whole-GPU reading remained 100%, while the whole-host CPU sample was
about 13–14%. Other GPU workloads were running. Native stacks confirmed Metal/MPS
calls, but per-process GPU-time attribution through `powermetrics` required
interactive sudo and was not collected. No conclusion assigns all GPU load to
Waffles or claims that GPU execution itself is the dominant delay.

## Queue-side diagnosis

The read-only candidate SELECT took **477.589 ms** for Mac baseline and
**646.332 ms** for Mac extras. It visited about 61,000 eligible rows and sorted them
to return one. PostgreSQL reported shared-buffer hits and zero physical reads for
those plans, so these observations do not indicate a disk-read bottleneck.

Only the SELECT portion was executed, inside `BEGIN READ ONLY`; row locking and
all updates were removed. A separate `EXPLAIN` without `ANALYZE` confirmed that the
actual production UPDATE also plans a bitmap scan, sort, then `LockRows` and LIMIT.
The SELECT timings are therefore diagnostic evidence, not exact measured duration
of a production claim including lock waits and writes. The still-fawn SELECT
short-circuited because its baseline slot was occupied; that timing is excluded
from comparisons.

Source inspection shows an advisory transaction lock keyed by backend name around
the claim. All Mac pools use the same key. Adding Mac workers therefore still
serializes their claims through this relatively expensive selection. One observed
PostgreSQL connection was waiting on that advisory lock. The evidence points to
this queue path as a substantial constraint that masks the Mac's faster processing
stage. Query/index design and the duration of the per-backend critical section are
the next diagnostic targets; no fix was applied.

## Network and resource checks

The small GET probe had only a roughly 6 ms median difference between Mac and
still-fawn. A reused TLS-context probe was slower in its separate window, so no
TLS optimization benefit is claimed. The samples are too short to exclude all
jitter or quantify thumbnail-transfer bandwidth. Waiting on an HTTPS response
can mean waiting for server-side SQL, rather than a slow network link.

Over a separate 20-second sample, still-fawn's baseline used about 0.96 CPU cores,
with 0.000832 seconds of cgroup CPU throttling and no new cgroup OOM events. Its
pod network namespace had zero TCP retransmits or input errors. The VM showed
CPU and memory pressure (CPU PSI some avg10 about 54%, memory some about 6.8%),
roughly 0.83% I/O wait and 4.27% CPU steal. The Proxmox host was about 72% CPU busy
with zero memory PSI in that sample. Host TCP counters included eight retransmits,
which cannot be attributed to the VM's worker traffic. No whole-network clean bill
of health is claimed.

The existing USE orchestrator produced partial CPU/memory results, then stopped
because its SSH application-log stage requires a service name. Its displayed
“All resources appear OK” was not accepted as a conclusion. Separate read-only
Linux host/VM/cgroup and Mac counters filled in the resource observations above.

## Reproduction

- `diagnose-mac.py PRIVATE_DIRECTORY`: native stack samples and host/process counters,
  using the existing Mac virtual environment; no process restart.
- `diagnose-network.py`: eight read-only queue GETs and client profile, plus eight
  separate reused-context GETs on HTTPS; no change to production clients.
- `diagnose-queue.py`: aggregate timings, waits and table statistics in a read-only transaction.
- `diagnose-claim.py`: candidate SELECT timing without row locks or writes.
  `--full-plan-only` plans the actual claim without executing it.
- `diagnose-linux.py`: two resource snapshots twenty seconds apart, run inside the
  existing worker and over SSH to the inventory-verified Proxmox host.

The jobs remain running. This diagnosis does not establish a maximum sustainable
Mac throughput or a CPU-versus-GPU hardware ranking.
