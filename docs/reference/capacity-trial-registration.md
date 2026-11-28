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
| `peer_baseline_sha256` | Digest of the original protected baseline phase, sealed before the first candidate and retained for every comparison |
| `baseline_mode` | `active` or `observed_idle`; idle target has zero observed workers. Actual queue proof remains a phase-review requirement |
| `fixed_inputs` | SHA-256 digests for sources, cohort, model, prompt, extraction, quality rubric and environment |
| `constraints` | Measured rows covering every resource: metric, unit, capacity, per-extra-worker cost and the baseline/scheduled footprint reserved for every affected workload |
| `limits` | Warm-window duration ≥300 s, sampling gap ≤15 s, ≥10 durable items, progress/request/drain/warm-up deadlines and peer budgets no weaker than the playbook |
| `admission_deadline_ns` | Initial admission no more than 15 s after registration; the owner still must recheck freshness and ownership at admission |
| `completion_deadline_ns` | Hard experiment bound, long enough for forward/reverse windows and drain |
| `candidates` | Strictly descending total target worker counts, starting at the derived measured ceiling and remaining above baseline |
| `repeat_order`, `selection_tolerance` | `reverse-eligible` and `0.05`; phase selection is not implemented by registration |
| `increment_backends` | Freeze identities of added backends (or an empty list for in-place tuning); missing binding cannot qualify a completion objective |
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
and allocation vectors, registration time and a deterministic digest covering the
registration, capacity qualification, shared reviewer, service budgets, completion objective, native verification and output summarization sources. Creation is
exclusive with file mode `0600`. Revalidation recomputes the contract and rejects
changed scope, policy or measurements. A content digest detects accidental changes;
it is not a signature or proof of authorization. Do not edit an existing receipt.

## Offline candidate qualification

`capacity_qualification.qualify` validates a registration against a candidate's
fixed inputs, environment, observed allocation vectors and registered throughput
and service budgets before applying the shared reviewer. Its top-level decision
is always `not_admitted`. `capacity_budget_review` preserves the capacity/peer result. `candidate_review`
also consumes the single machine-readable `completion_objective`; passing peer
budgets alone cannot qualify verified useful gain. The public `review` command still refuses live capacity review. The separate
`qualify-capacity` command exposes these offline checks and always returns
`not_admitted`, `proceed=false` while complete phase and execution validation is pending.

The comparison carries `capacity_registration_sha256`, the original sealed
`peer_baseline` phase, the exact `fixed_inputs`
and `output_accounting`, the [completion objective/native accounting](workload-adapter-contract.md), `min_gain=0` and a `max_peer_loss` no weaker than registered.
Service budgets must match the registered `service_budgets` exactly. Each phase's
`allocation` maps every affected workload to its observed total workers. Peer
vectors cannot change. The first candidate is admitted at the derived maximum
after a fresh baseline, within the initial admission deadline. The observed
`admitted_ns`, `warmup_start_ns` and `warmup_end_ns` precede the measured `start_ns`;
warm-up is bounded separately by `warmup_deadline_s`. A warm-up longer than fifteen
seconds does not invalidate a timely admission, and cannot count as a warmed
measurement window. Later candidates and their
baseline allocations must be registered and fall within the experiment bound.

For an observed-idle target, retain real zero baseline output and fresh empty-queue
evidence with the protected reservation. Its new caller appearance is allowed;
other caller changes still hold. The trial needs positive useful output, matching
`completed_items` and `fresh_inference_items` at least as large as the registered
minimum, frozen cohort/unit, quality/SLO qualification and no terminal errors.
An active target needs comparable fresh completions in both windows. Cached
results cannot satisfy these fields; independent receipts will verify them in the
remaining integration. Every peer retains the existing progress, latency, error,
quality and service-budget gates, including tighter registered limits.

Every candidate also passes a second shared review against the same hash-bound
original protected baseline. Combine that verdict with the current comparison
using `rollback` before `hold` before `eligible`. This prevents acceptable pairwise
losses from compounding across a sweep (for example, peer output 100 → 90 → 81).
Retain the original baseline's real target evidence; never invent completions for
an idle target or apply the initial-admission deadline again to this second review.

Lower target throughput alone need not violate a capacity safety budget. It does
hold the completion objective when the fixed remaining job would not finish earlier.
Missing independent production readback or missing added-backend contribution also
holds the candidate. Native accounting is constructed by actual checking, not read
from claimed JSON totals. It binds source creation, originating run/purpose, backend
and the frozen session. Media still needs its own verified source-unit accounting
bridge; scene-revision count is not that bridge.
`rank_repeatable` ranks already-qualified samples by the lower rate across at least
two repetitions, then chooses the fewest workers within 5% of the fastest such
rate. The zero-extra-worker control may participate and wins the same 5% rule. Units and fixed inputs must match. Its result is `ranking_only`, not an
admission decision. It does not prove that repetition receipts are independent or
in the required order; do not use hand-entered rates to promote an allocation.

Remaining P05/P06 work: validate phase order and previous-receipt chains; require
independent fresh evaluation readback and eligible reverse repetitions; validate
allocation/lease execution evidence; connect these checks to CLI review and fence
actual supervisor dispatch. Registration or offline qualification alone does not
satisfy those gates.
