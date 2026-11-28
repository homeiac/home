# Workload-neutral evidence review — science journal

Date: 2026-11-28 Pacific. Scope: deterministic offline evidence, architecture
verification, playbook/skill integration and replay of already captured measurements.
No new inference, capacity allocation, native publication or production restart.

## Question and boundary

Can one shared implementation decide whether a change improves the whole finite
backfill, while each workload retains its own execution and data architecture?

The workload owns the queue, client/parser, semantic quality, canonical writer and
independent reader. Common code owns evidence consistency, deduplication, workload
aggregation and the finish-time calculation. Media remains on the existing
PostgreSQL OpenLABEL writer/checker; native nonmedia data stays in its own store.
Evidence JSON/JSONL and private archives are not another canonical data plane.

## Implementation records

| Change | Source | Result |
| --- | --- | --- |
| Pure fixed-remaining-work projection | #295, `3143ecb` | Offline JSON/cutoff CLI; evaluation excluded; missing publication/contribution or no projected reduction holds |
| Workload-neutral safety/observers | #296, `7627b49` | Same warmed-window, sample, count, idle reservation and latency/error checks for all workload names; declarative mappings and saved-response replay |
| Native output/accounting integration | #297, `fd953d0` + `bf9038b` | Existing schema/store/IDs and independently saved execution provenance; typed accounting consumed by the existing candidate review |
| Policy/skill/journal | This follow-up | Parameterized journey, owner/data boundary, measured scope, private persistence and implementation limits |

The shared source-unit accounting bridge for media capacity is still missing;
OpenLABEL revision count cannot replace it. Ordered phase/repetition and actual
lease/dispatch verification also remain pending. Offline qualification always
returns `not_admitted` and `proceed=false`. Passing a sub-review is not live admission.

## Hypotheses and observed checks

| Hypothesis | Evidence | Observed result |
| --- | --- | --- |
| Workload renaming must not weaken a safety rule | Same synthetic comparison under Cricket, speech-transcription and document-index IDs | Same eligible/hold/rollback behavior; no workload-name exception |
| Shared workload latency must combine observations correctly | Twenty fast GPU attempts plus two slow CPU attempts | p95 comes from raw distinct attempts, not average backend p95s |
| Retries/replays/corrections cannot manufacture progress | Duplicate execution/source records, cached/withheld/evaluation cases, and later revision of an old logical output | New production deduplicated; old/evaluation outputs receive zero new credit |
| Native references cannot relabel backend, purpose or origin | Independent readback plus existing execution-authority export | Backend-map reassignment, evaluation-to-production relabeling and another-run reuse rejected |
| Native data must remain native | Integer revisions, escaped/array identity paths, original schema/store and first-creation binding | Identities preserved; no canonical writes; remote/unresolved schema retrieval refused |
| Descending candidates must retain target latency and the protected goal | Explicit target-latency regression, protected-control comparison and zero-increment 5% ranking cases | Slower-within-range candidates can beat the protected control; missing target latency holds and target latency loss rolls back |
| A successful process exit must not imply promotion | Independent forward test of the updated skill on a raw photo objective | Exit 0 correctly interpreted as HOLD; allocations/data left unchanged |

Independent review identified and drove fixes for revision creation versus logical
creation, authoritative backend attribution, and originating run/purpose binding.
A declared reference alone is insufficient. Native checking validates consistency
of approved reader exports; it does not authenticate fabricated artifacts. Semantic
correctness remains the workload reviewer's job with saved rubric/cohort/results.

## Replay of the closed photo comparisons

Source: #218 `f030bf1`, `scripts/knowledge-index/library-server-timing.json`.
One fixed snapshot contains **24,305 remaining face observations**. The root chat
replayed all three exported objectives using the committed shared helper. Every
result exactly matched its stored assessment. The photo owner also independently
checked rate/ETA parity against its direct DuckDB query.

| Closed arm | Baseline projected hours | During-arm projected hours | Difference | Shared decision |
| --- | ---: | ---: | ---: | --- |
| Mac +10 CPU threads, joint | 15.59 | 15.24 | 20.96 minutes earlier | HOLD |
| Mac +6 CPU threads, joint | 15.59 | 14.79 | 47.74 minutes earlier | HOLD |
| Mac +7 CPU threads, separate calls | 12.99 | 13.79 | 47.74 minutes later | HOLD |

These are **diagnostic projections from GPU checkpoint production rates**, at the
same hypothetical remaining count. They are not verified CPU speedups or a measured
end-to-end library completion time. Production CPU contribution and independent
canonical publication verification were not measured. Startup/transfer/downstream
costs are not fabricated into these figures. Frozen CPU replays are excluded.

The zero-CPU control also varied, so one before/during pair cannot establish
hardware causation. CPU prompt/generation timing can identify a slow stage; it
does not prove CPU-versus-unified-memory contention or identify a GPU co-tenant.
The determining script returns insufficient evidence instead of inferring that
parallel work is inherently bad. The selected finite-evidence configuration remains
four Mac Metal workers, three RTX workers and zero production CPU lanes.

The corrected chart explicitly labels RTX GPU **before/during added Mac CPU**.
Its 18.59→20.39 faces/min was an improvement; rejection applied to the added
Mac CPU arm's combined latency, not to RTX. The photo owner's served report is
version 89, panels 299/300; the root previously independently rendered-verified
version-88 comparison/final-selection content. No new rendered verification of
panels 299/300 is claimed here.

## Reproduction and verification

```sh
python3 scripts/perf/completion_objective.py "$objective" --at-ns "$cutoff_ns"
python3 scripts/perf/workload.py qualify-capacity \
  --session "$session" --registration "$registration" \
  --comparison "$comparison" --at-ns "$cutoff_ns"

PATH="/path/to/postgresql-16/bin:$PATH" \
PYTHON=/path/to/test-python \
ASAM_OPENLABEL_1_0_SCHEMA=/private/path/openlabel-1.0.0.json \
  bash scripts/perf/verify-cricket-publication.sh
```

The final `bf9038b` integrated suite passed **321 tests and 43 subtests in 25.15 seconds**, with no skips, using
Python 3.14, pytest 9.2, jsonschema 4.26, psycopg 3, OpenTelemetry SDK 1.45.2 and
PostgreSQL 16. PostgreSQL is disposable/local; no production database was written.
After the policy fingerprint also included the CLI, 73 capacity tests passed.
The split observer/safety change passed its 37 directly independent tests.

Coverage run: 42 targeted tests, **100% statement coverage across 245 statements**
in `completion_objective.py`, `native_output.py`, and `workload_measurements.py`.
This is not a claim of 100% coverage for the entire repository or every branch.
Scoped Ruff passes with pre-existing legacy C408/EXE001 rules excluded. The
skill-creator validator accepts the updated skill. A pytest-asyncio default fixture
scope deprecation warning is informational.

The independent skill forward test used a raw objective without a supplied answer.
It reported a diagnostic ~21-minute improvement but HOLD for missing baseline/trial
readback and no verified new CPU contribution. It retained native OpenLABEL/data
ownership and distinguished `not_admitted` from a successful CLI exit. No live
query or mutation was performed in that test.

## Completion checklist and limits

- [x] Shared safety rules apply to arbitrary workload IDs.
- [x] New observers plug in through versioned mappings; offline replay is deterministic.
- [x] One finish-time function is used by reports and candidate qualification.
- [x] Raw attempts aggregate/deduplicate with profile, run, mode and reuse attribution.
- [x] Native identity/schema/store/execution authority stays workload-owned.
- [x] Media keeps its existing native-ID/OpenLABEL publication gate.
- [x] Invalid/abstained/partial quality evidence remains explicit and workload-reviewed.
- [x] Core tests, independent architecture review and skill forward test completed.
- [ ] Live automatic capacity admission is not implemented by this change.
- [ ] Media source-unit/backend accounting bridge remains required for capacity promotion.
- [x] No new production CPU benefit or global optimum is claimed.

Raw closed CPU evidence remains in its sealed private archive documented in the
[CPU journal](cricket-cpu-tuning-20261127.md). Additional snapshot/query/API/replay
receipts are retained separately so the sealed archive is not rewritten. The separate report archive is
`~/Library/Application Support/photo-memory-acceptance/cpu-tuning/2026-11-28-report`:
eight files / 14,517 bytes, every source/copy reread hash and private permission
verified. Manifest SHA-256:
`a84108ac4d8154edd3bfed9e75d5a8ec7d6307bfdb3fa1f8cf981e17927a8742`.
It includes the fixed remaining snapshot, direct query/API proof, exact root replay,
validation/coverage and independent skill-forward evidence. The sealed older CPU
archive was not modified.

Final documentation checks resolved 43 local links and rendered all six changed
Mermaid diagrams successfully. The default renderer lacked its cached Chrome;
validation reused the already installed Chrome in an isolated headless render,
without installation or user-profile changes. The updated skill passed its
frontmatter/reference workflow validation and independent read-only forward test.

Final committed-code validation is also persisted separately under
`~/Library/Application Support/photo-memory-acceptance/cpu-tuning/2026-11-28-final-validation`:
three files / 1,904 bytes, with source/copy reread hashes and private permissions
verified. Manifest SHA-256:
`e82d521cda61419cb09ffa7d3f67ab783e2156410b99abc8f3c0f9f332cedc56`.
This retains the final 321-test receipt without rewriting the earlier report archive.
