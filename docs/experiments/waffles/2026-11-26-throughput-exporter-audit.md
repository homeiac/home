# Throughput drop investigation

The owner reported a simultaneous drop across backend curves near 21:44 Pacific
(05:44 UTC on November 27). Prometheus retained range samples from both queue
pods across the 05:39 coordinator rollout. The query calculated each pod's slope
and summed them, even though both exported the same durable PostgreSQL counts.
When the retired pod's samples left the five-minute window, its extra contribution
disappeared. This created the apparent step down.

| UTC | Mac displayed rate/min | Deduplicated five-minute rate/min | Mac completed assets |
|---|---:|---:|---:|
| 05:43:30 | 166.353 | 59.324 | 4,227 |
| 05:44:30 | 82.752 | 82.755 | 4,326 |

The completed count increased by 99 during that minute. The corrected rate rose;
the old graph's drop was not evidence of a matching drop in production. The
rollout did cause a separate earlier interruption and lease recovery, which the
deduplicated five-minute history still includes. Do not erase that real effect.

The correction takes `max by(run,worker,state)` at each timestamp before applying
the range derivative. Counts and average processing time use the same exporter
deduplication. ETA and node-graph edge rates share the corrected helper.

[Raw aggregate audit](2026-11-26-throughput-exporter-audit.jsonl) includes old-pod
and new-pod contributions for every backend. `inspect-throughput.py` reproduces
the queries. Experimental rates use PostgreSQL start/completion timestamps and
were not calculated from these erroneous Prometheus curves. The science journal
retains the discovery; no benchmark result was retroactively replaced.
