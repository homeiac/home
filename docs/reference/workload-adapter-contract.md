# Shared workload evidence adapters

The workload owns execution, queues, semantic review, its canonical data and the
reader that exports that data. Shared scripts validate saved evidence and compute
the decision. Adding a workload requires an adapter and resource registration;
changing its name does not change the safety rules. No command here publishes
content, acquires compute, or starts inference.

## Architecture boundaries

| Data | Owner and authority | Shared evidence use |
| --- | --- | --- |
| Pending/running jobs, retries, corrections and claims | Existing workload queue/operational ledger | Observe demand, first completion, reservations and execution provenance |
| Media observations | Existing PostgreSQL OpenLABEL writer and revision history | Reuse `verify-media`, pinned ASAM schema, native face IDs, stable occurrence IDs and independent scene readback |
| Nonmedia outputs | Workload's existing schema and authoritative store | Freeze a native adapter and independently export its native identities/content/provenance |
| Search/UI/Parquet projections | Existing derived publication pipeline | Do not treat a derived view as a replacement authority for annotations |
| Trial JSON/JSONL, hashes and charts | Private evidence archive | Reproduce measurements; never become a second canonical content or annotation store |

Do not create placeholder face identities. An unresolved actor remains withheld or
pending under the existing media contract. A life-stage `unknown` is an abstention,
not an identity. Preserve other producers' accepted observations and correction
lineage. [Media contract](../architecture/media-workload-contract.md) ·
[Existing scene/ledger boundaries](../architecture/cricket-shared-workload-design.md)

## Capture once, replay without services

`observe-shared-workloads.py --registry REGISTRY.json` loads version-1 declarative
metric mappings. Each workload maps `heartbeat` and observation names to
`[metric_name, exact_label_selector]`. The default mappings live in
`scripts/perf/shared-workload-observers.json`. A new workload can supply another
registry without editing the observer. Selectors are exact label matches; they
are not executable PromQL. Missing, stale and conflicting observations stay
unknown, separately from measured zero. Source heartbeats retain their age.

```sh
python3 scripts/perf/observe-shared-workloads.py \
  --registry "$registry" --input "$saved_prometheus_response" --at "$cutoff_seconds"
```

`--input` makes no live query and requires an explicit cutoff. Output binds the
mapping and response hashes. Save raw capture privately; run/model/job identifiers
belong in private evidence, not metric labels. New live observations create new
captures instead of mutating the inputs of an old trial.

## One completion-time objective

Version 1 of `completion_objective` carries:

| Field | Meaning |
| --- | --- |
| `version`, `workload`, `unit` | `1`, owning production workload and one useful output unit |
| `remaining` | One fixed `amount`, `observed_ns` and private `evidence_ref`, used for both projections |
| `increment_backends` | Backend identities added by this experiment; freeze the same list in capacity registration |
| `baseline`, `trial` | Closed `start_ns`/`end_ns`, `unique_production_completed`, `verified_production_completed`, matching `backend_unique_production_completed`/`backend_verified_production_completed` maps, `evaluation_completed`, `readback_ref` and `evidence_ref` |

Maps sum to their matching totals. Use `null` for verification that was not
measured. A durable queue checkpoint is not automatically an independently read
back canonical media publication. Never add frozen evaluation completions to
production counts. Keep the remaining-work snapshot fixed while comparing rates.

```sh
python3 scripts/perf/completion_objective.py "$objective" --at-ns "$cutoff_ns"
python3 scripts/perf/workload.py project-completion \
  --objective "$objective" --at-ns "$cutoff_ns"
```

Both entry points call the same pure function. For each window it computes
`combined_rate = unique_production_completed / duration_seconds` and
`remaining_seconds = fixed_remaining_amount / combined_rate`. A negative
`projected_finish_delta_s` means an earlier projected finish. This is a projection
at the observed rate, not a guarantee about future arrivals or input difficulty.
Preparation/transfer/startup costs remain separately recorded and included in the
owner's end-to-end completion assessment when material.

The helper can show diagnostic checkpoint-based ETA while returning `hold` for
missing verification. It never infers CPU, memory-bandwidth or GPU contention from
rate/utilization alone. A structurally complete result is
`evidence_ready_not_admitted`, not promotion.

For descending candidates, set `baseline_scope: protected` to compare completion
time with the original protected control, rather than requiring each lower-worker
candidate to beat the preceding fastest candidate. This preserves the fewest-workers
within 5% rule. The default `comparison` scope uses the supplied adjacent baseline.
The reviewer binds the chosen window/count/unit to that exact comparison phase;
it does not accept an unrelated convenient control.

The existing `qualify-capacity` path consumes that exact object inside
`comparison.json`. It binds workload, windows, unit and verified totals, compares
added backend identities with registration, and checks backend maps against typed
accounting produced by the native checker. Hand-entered JSON totals or proof
hashes cannot construct that typed result. A missing objective, unverified added
backend or no projected finish-time reduction holds `candidate_review`, even when
`capacity_budget_review` passes. Peer regressions still cause rollback.

```sh
python3 scripts/perf/workload.py qualify-capacity \
  --session "$run/session.json" --registration "$run/capacity-trial.json" \
  --comparison "$run/comparison.json" --at-ns "$cutoff_ns" \
  --references "$run/native-observations.jsonl" --readback "$run/native-readback.jsonl"
```

This command remains offline and returns `not_admitted`, `proceed=false` until
the existing ordered-phase, repetition, fresh-evaluation and actual lease/dispatch
gates are implemented. The current media checker does not itself supply the
source-unit/backend accounting bridge; missing that bridge holds capacity review.
It cannot be replaced by counting scene revisions as new source completions.
[Capacity contract](capacity-trial-registration.md)

## Native output verification

At `start --output-kind other --native-adapter FILE`, freeze a version-1 adapter:

- `workload`, `unit`, `output_kind: native`, and `adapter_source_sha256`.
- `canonical_store` and `execution_provenance` each declare existing `system`,
  `namespace`, and architecture `contract_ref` authorities.
- `payload_schema` plus its canonical-JSON `schema_sha256`; bundle schema refs
  locally so replay cannot fetch a changed remote schema.
- `identity_paths` JSON Pointers for native `source_id`, `source_version`,
  `output_id`, and `revision`. Integer revisions remain integers.
- `logical_first_commit_path` and `backend_path` point to authoritative logical source/version/output
  creation and original backend provenance in the native readback bundle.
- Optional `amount_path` binds source minutes or another measured amount to saved
  native data. Without it, each logical output amount is one.

`native-observations.jsonl` references those identities, `workload`, originating
`run_id`, `purpose` (`production`/`evaluation`), `backend`, `unit`, `amount`,
`writer_id`, and canonical-JSON `content_sha256`. The independent readback provides
the matching payload, authority/schema, `reader_id`, logical `first_committed_ns`
and `observed_ns`.

The reader also exports saved `execution_provenance` from the declared existing
execution authority: the identities, workload, originating run, purpose, backend,
content hash, `recorded_ns`, and source artifact `evidence_ref`/`evidence_sha256`.
These are readback evidence fields, not new performance fields to insert into
arbitrary business payloads. Native timestamps may be normalized in the reader
export with the source query/conversion pinned; do not alter native ID types. Reuse native execution receipts or ledger lineage.
If that authority was not recorded, keep verification missing; do not manufacture
it after the trial.

```sh
python3 scripts/perf/workload.py verify-native --session "$run/session.json" \
  --references "$run/native-observations.jsonl" --readback "$run/native-readback.jsonl" \
  --at-ns "$cutoff_ns" --window "$window_seconds"
```

Native checking preserves IDs, validates the workload's schema, digest and saved
identity paths, checks originating run/purpose and first logical commit, and
deduplicates retries/revisions. A new revision of an old logical output gets no
new-production credit. Changing only a reference's purpose or run cannot reclassify
an evaluation or another run's output. A native adapter cannot replace the media
OpenLABEL checker. `other` without a frozen native adapter and readback is a hold.

This verifies consistency of approved exports, not the honesty of arbitrary
fabricated files. Bind exporter source, queries, native authority and artifact
hashes in the private experiment manifest; preserve independent readback and review.

## Output summaries and attribution

`workload.py summarize-outputs` accepts the adapter's saved JSONL attempt envelope
and an explicit window/workload/unit/profile. Each attempt supplies hashed job,
source-version and execution IDs; backend; `inference_mode`; retained stage/action
and model-called flags; purpose; disposition; finish time and duration. A complete
production output also supplies amount, first logical commit and verification ref.

Without native verification, the summary leaves verified amounts **null**. Passing
`--session`, `--references`, `--readback` and `--at-ns` executes native checking and
binds each verified attempt's source/version, backend, amount and creation time.
Claimed hash lists or relabelled backends are refused. Native IDs are hashed only
in evidence; the canonical records are unchanged.

The summarizer deduplicates attempts and logical outputs, excludes replay/cache/
withheld work from new production, and computes workload p95 from distinct raw
production attempts across backends. It never averages backend p95s. Its decision
is `summary_only_not_qualification`; sampling, quality and authority checks remain
part of qualification. Record input/difficulty buckets in workload-owned captures
when needed; a changed job mix must not be mislabeled as contention.

## Services and semantic quality

Services use measured SLOs instead of fabricated durable outputs. Register
`measurement_kinds: service` on their routes. A service-only `start` freezes
`--service-objective FILE` containing the existing `metric` and `contract_ref`;
review requires the same contract, real unit/sample/freshness/absolute/relative
budgets, and reports service-objective change separately from verified outputs.
An indexer cannot escape publication by selecting service output kind.

The shared reviewer currently consumes the adapter's `quality_ok`/`slo_ok` results;
it does not authenticate a semantic review or reconstruct a rubric. The adapter
owner must link the actual reviewed cohort, rubric, evaluator version and saved
scores. The adapter owns semantic quality: frozen expected cases/rubric, production parser
and validators, reviewed correctness and abstentions, and a saved independent
review. Invalid responses count as failed cases; safety stops retain partial
denominators. The common scripts do not invent semantic correctness. Lack of a
workload-owned verifier or reviewed-quality evidence is a hold, not a universal
fallback to OpenLABEL or an assumed pass.
