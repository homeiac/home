# Bounded capacity registration

The `register-capacity` subcommand seals the intended experiment in a private
`capacity-trial.json` beside an existing workload session. It does not submit work,
acquire a Lease, change workers or authorize admission. The current common review
explicitly rejects `bounded-concurrency` comparisons until the phase reviewer is
implemented. A FIFO or isolation prediction cannot substitute for this contract.

Use `workload.py register-capacity --session PATH --spec PRIVATE_SPEC`. Registration
uses the current clock; it cannot be backdated from a command-line argument. Keep
real evidence outside Git. The [synthetic test fixture](../../scripts/perf/tests/test_capacity_trials.py)
demonstrates the complete JSON shape without describing actual spare capacity.

| Field | Required meaning |
| --- | --- |
| `action`, `pool` | `bounded-concurrency`, exactly one requested serving pool from the intake |
| `callers` | Census for every resource and dependency, including declared, scheduled and newly observed callers |
| `baseline_allocation` | Actual incumbent allocation plus reserved scheduled lanes, keyed by every affected workload; target workers are total workers, not an increment |
| `protected_allocation` | Floors that the baseline and every candidate preserve |
| `rollback_allocation` | Exact baseline vector; rollback cannot take lanes from a peer |
| `allocation_evidence` | Timestamp and private evidence pointer/hash for the vectors |
| `baseline_mode` | `active` or `observed_idle`; idle target has zero observed workers. Actual queue proof remains a phase-review requirement |
| `fixed_inputs` | SHA-256 digests for sources, cohort, model, prompt, extraction, quality rubric and environment |
| `constraints` | Measured rows covering every resource: metric, unit, capacity, per-extra-worker cost and the baseline/scheduled footprint reserved for every affected workload |
| `limits` | Warm-window duration ≥300 s, sampling gap ≤15 s, ≥10 durable items, progress/request/drain deadlines and peer budgets no weaker than the playbook |
| `admission_deadline_ns` | Initial admission no more than 15 s after registration; the owner still must recheck freshness and ownership at admission |
| `completion_deadline_ns` | Hard experiment bound, long enough for forward/reverse windows and drain |
| `candidates` | Strictly descending total target worker counts, starting at the derived measured ceiling and remaining above baseline |
| `repeat_order`, `selection_tolerance` | `reverse-eligible` and `0.05`; phase selection is not implemented by registration |
| `output_accounting` | `fresh-evaluation-separate-from-production`; cache reuse cannot be counted as fresh inference |
| `lease` | Planned `KubernetesLease`, owner, namespace, unique names for the physical dependency leaves, expiry and renewal interval with at least three renewal opportunities |

Census, allocation and constraint evidence needs `observed_ns`, `evidence_ref` and
`evidence_sha256`. Observations must be no older than 15 seconds and not in the
future. Registration binds the evidence hash; it does not independently establish
that the evidence file or measurement is truthful. Phase review and the owner must
check actual captures and observations before admitting work.

For each constraint, subtract all reserved resource quantities from measured
capacity and divide by the measured incremental cost per target worker. Round down
and take the tightest constraint. Add the incumbent target worker count to obtain
the total-worker ceiling. Do not subtract workers from GiB or copy worker counts
into memory measurements. Reservations for incumbent target workers are included
once in the baseline footprint. Zero remaining capacity cannot register an extra
worker sweep. An allocated/reserved caller cannot have a zero resource footprint
on a route it uses. Unknown constraints remain a blocker, not an assumed zero cost.

The receipt binds the complete intake (including topology), spec, derived ceiling
and allocation vectors, registration time and validator source digest. Creation is
exclusive with file mode `0600`. Revalidation recomputes the contract and rejects
changed scope, policy or measurements. A content digest detects accidental changes;
it is not a signature or proof of authorization. Do not edit an existing receipt.

Remaining P05/P06 work: validate phase order and matching evidence before the common
reviewer; support a real idle-target baseline; preserve active peer/service gates;
separate safe qualification from throughput ranking; require fresh evaluation
receipts and eligible reverse repetitions; fence actual dispatch with the shared
lease and observed allocations. Registration alone satisfies none of those gates.
