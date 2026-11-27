# Actual-worker traces and missing-preview throughput incident

Observed November 26, 2026, Pacific time (November 27 UTC). These are traces of
existing production workers, not extra inference jobs or a matched-photo hardware
benchmark. The production targets remain Mac 16 (one Metal, 15 CPU), still-fawn
four CPU, PVE two desired/one admitted, and one guarded native worker per host.
Chief-horse remains standby; RTX remains unused.

## Hypotheses and measurements

The question was why still-fawn's i5 was competitive with the Mac's M5 Pro in
completed photos per worker. After fixing the indexed FIFO claim path, remaining
hypotheses were request overhead, model execution/feeding, shared resource
pressure, and error backoff. The owner requested tracing actual workers while
production continued.

At 23:24, native stack samples of the existing Mac Metal worker recorded 841
main-thread observations. Disjoint leaf-stack classification found 24.85% in TLS
handshakes, 39.71% in HTTPS reads, 0.59% in TCP connection setup, 30.68% in Python
condition waits, and 4.16% elsewhere. Two actual CPU extras spent 31.22% and
25.09% in HTTPS reads plus handshakes, and 61.30% and 68.28% in condition waits.

These are wall-stack observations, not CPU utilization or GPU kernel occupancy.
HTTPS reads include remote application work as well as transport. Condition waits
include asynchronous model workers. The Metal worker received 3.117 Mbit/s in a
separate 15-second nettop interval, with 1,398 retransmitted bytes. This does not
establish network bandwidth saturation. Source inspection shows new HTTP client
connections per request and a synchronous one-photo adapter that prevents useful
cross-photo model batching. Both are concrete places where faster silicon can be
left waiting, but their separate contributions have not been measured by a fix.

At 23:27, eBPF traced the actual still-fawn baseline process for 20 seconds. It
recorded three clock_nanosleep calls totaling 15.0003 seconds and poll calls
totaling 0.6824 seconds. This window caught unavailable-preview error backoffs,
not steady inference, so it cannot establish CPU-versus-GPU execution speed.

The owner-run privileged Mac capture collected 20 power samples over 20.9902
seconds. All reported Heavy thermal pressure; whole-host GPU busy time averaged
97.08%. **No per-task GPU fields were emitted**, despite the requested flag, and
powermetrics emitted 20 `Second underflow occured.` warnings. Another GPU-capable
process was active. Thus the capture does not establish that Waffles used 97% of
the GPU or quantify thermal throttling. It also overlaps the preview-failure
interval. The Metal worker appeared in 11 emitted task records totaling 0.0538
CPU seconds; omitted idle records and capture warnings limit interpretation.

## Failed diagnostic attempts retained

The first Linux syscall capture exceeded bpftrace's 512-probe limit and failed.
A focused 83-probe capture succeeded. The original Mac DTrace capture hung beyond
its expected 20 seconds; SIGINT did not terminate it. The owner killed only that
profiler. It exited 137 with no trace output; powermetrics exited zero and its
capture was recovered. No production worker was killed or restarted. The reusable
sudo wrapper now prints startup, profiler PIDs, progress every five seconds and
completion, and forcibly terminates only its own profiler children at its deadline.

## Fleet-wide drop: measured before the intervention

The repeatable incident report captured database completions and Prometheus
history at 23:34:26. Complete one-minute database buckets show:

| Pacific minute | Mac completed | still-fawn | PVE | fun-bedbug |
|---|---:|---:|---:|---:|
| 23:24 | 529 | 170 | 33 | 10 |
| 23:26 | 366 | 84 | 20 | 8 |
| 23:27 | 18 | 3 | 0 | 0 |
| 23:29 | 14 | 9 | 3 | 1 |
| 23:31 | 55 | 12 | 3 | 1 |
| 23:33 | 479 | 141 | 28 | 10 |

Exhausted `thumbnail_http_404` jobs rose from 80 at 23:27 to 333 at 23:31
and 453 at 23:33. Telemetry consistently showed one Metal plus 15 CPU Mac workers
and four still-fawn workers throughout this interval. PVE retained one admitted
worker. fun-bedbug's independent guard intermittently returned it to standby.
Coordinator usage during 23:27–23:31 was 0.031–0.048 CPU cores with zero measured
CPU-quota throttling; the database snapshot showed no blocked workload query.

The source retries each bad asset up to four times with a 30-second queue delay,
but additionally sleeps each inference worker for five seconds after a failed
attempt. The simultaneous drop, rising missing-preview counts, unchanged worker
counts, and actual-worker sleep trace identify missing-preview retry/backoff as
the cause of this incident. This is separate from the earlier exporter duplicate
series bug and the indexed-FIFO bottleneck. Successful-photo processing times
alone omit this lost capacity.

## Registered intervention: scan previews ahead of inference

After seeing the drop, the owner requested a separate background scanner to find
404s and remove them from the runnable queue. The intervention will check pending
production jobs with bounded HTTP concurrency, timeout and retries; retain
confirmed missing previews as failed jobs with an audit record; preserve photos
and all already-claimed work; and keep inference worker counts unchanged.

Before/after evidence must include scanner request/error counts, failed-job counts,
actual ready workers, completed photos per backend and coordinator load. A higher
rate after moving to a different part of the library is operational evidence, not
a matched-photo hardware speedup. Scanner rollout and outcomes will be appended
to the JSONL journal; implementation is not itself a successful result.

## Reproduction

Use `diagnose-throughput-drop.py --output PRIVATE_REPORT.json` for aggregate
20-minute correlation; `diagnose-mac.py PRIVATE_DIRECTORY` for live native stacks;
`trace-live-network.py PRIVATE_DIRECTORY` for live per-process network deltas;
`trace-live-linux.py PRIVATE_DIRECTORY` for bounded syscall tracing; and
`summarize-live-traces.py PRIVATE_DIRECTORY --output PRIVATE_SUMMARY.json` to
reproduce the summaries. `trace-live-mac-sudo.sh` is the owner-run privileged
capture. Raw process metadata stays outside Git. The timestamped record is
[the append-only journal](2026-11-26-fifo-capacity.jsonl).
