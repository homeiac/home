# Shared-workload peer measurements

The [reviewer](../../scripts/perf/shared_workloads.py) distinguishes durable
indexing output from service-only peers. This contract extends the
[operating policy](../runbooks/shared-indexer-tuning.md); it does not assert that
the live adapters already supply every field.

## Indexers and service peers

Resources can declare `measurement_kinds` for their registered workloads.
Unspecified workloads remain `indexer`. The RTX route declares Frigate as
`service`; Immich face processing remains an indexer because completed native
detection/readback is measurable output. If a service spans several resources,
declare its kind consistently on every route. Conflicting declarations hold the
comparison. A row cannot relabel Knowledge Index as a service to bypass durable
completion requirements, and the target still requires useful-output measurement.

Service peers retain the existing demand, unchanged cohort, quality, service and
baseline-allocation gates. Their observed metrics replace fictitious durable item
counts. Register `comparison.service_budgets[workload]` before a trial. Each metric
has a unit, `direction` (`higher` or `lower` is better), an absolute `min` or `max`,
and a `max_regression` fraction no greater than 0.10. Tighter budgets remain valid.
An increased error rate can be prohibited with `max_regression: 0`.

Each phase's workload row supplies `service_metrics[metric]` containing `value`,
matching `unit`, actual `samples`, `source_age_s` and a private `evidence_ref`.
The metric set must match the declared budgets. A five-minute window requires
at least 21 observations and source age no greater than 15 seconds; the existing
maximum-gap gate still applies. Values must be finite and nonnegative. A failed
baseline holds; demonstrated trial regression rolls back. Service metrics are
reported in their own units, outside `verified_change_percent`.

Illustrative contract fields, **not measured production values or approved budgets**:

```json
{
  "service_budgets": {
    "frigate": {
      "camera_fps": {"unit": "frame/s", "direction": "higher", "min": 4, "max_regression": 0.1},
      "inference_p95": {"unit": "s", "direction": "lower", "max": 2, "max_regression": 0.1}
    }
  }
}
```

Adapters must derive those observations from actual endpoint, camera or process
measurements and retain their evidence. A generic health check is not equivalent
to camera progress or latency. The later capacity-registration contract must bind
budgets and their measurement sources before actuation. This validator alone
does not admit a capacity change.

## Idle and finished peers

For a cricket comparison, `demand: false` also requires an `activity` object:

| Field | Required evidence |
| --- | --- |
| `state` | `idle` or `finished`, from the workload's queue/state authority |
| `runnable` | Integer zero; an active-process count alone is insufficient |
| `reservation_workers` | Explicit nonnegative scheduled-demand reservation, including a measured/declared zero |
| `observed_ns` | Within the phase and no more than 15 seconds before its end |
| `evidence_ref` | Nonempty private pointer to the source observation |

The reservation must remain unchanged across phases. Missing/stale/unknown state
holds the comparison; a workload seen among active callers cannot simultaneously
claim no comparable demand. Idle evidence does not cancel a scheduled reservation.
Server/device caller census, CPU/decode/storage/database routes and reservations
still require live collection before maximum-first trials.

## Read-only observation coverage

`observe-shared-workloads.py` now reports the library face pass and media-summary
pipeline separately from the coarse Knowledge Index status. They are facets of
Knowledge Index, not extra physical pools or additive throughput units. It also
reads existing Frigate service stats and Immich face detection/recognition queues.
Source fields come from the existing exporters; the observer does not deploy or
reconfigure them. Multiple distinct enricher streams are not collapsed into one
value merely because they happen to report equal numbers.

Keep these meanings intact when building window adapters:

- Face checkpoint completions are local checkpoint counts, not proof of independent
  canonical publication; their exported request p95 is historical, not window-specific.
- Summary counters represent Parquet writes in the current process and separate
  backend execution from cache reuse; they are not automatically unique-source counts.
- Frigate's detector statistic is a rolling mean in milliseconds, not p95.
- Empty Immich face queues do not prove every submitted frame was recognized.
- Missing fields stay absent. The legacy observer's 180-second freshness flag is
  activity context and does not satisfy tighter trial measurement requirements.

Server/device caller attribution, complete CPU/storage/database routes, scheduled
reservations and matched useful-output windows are still needed for a live trial.
