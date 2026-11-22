# Luna submission worker

## Text-only summary reconciliation

The `reconciliation` policy mode uses existing local and Luna captions plus saved
metadata. It does not upload images or video. Results are model-generated and
unresolved contradictions are marked `needs_visual_review`.

Policy v2 makes review risk-based: minor visual differences and unidentified
background people are omitted or generalized (`risk_level=low`, no review flag).
Only a critical contradiction about a main person's identity or important life,
family or work event, which cannot safely be omitted, can require human review.
User-confirmed aliases are private metadata, not uncertain identities. Register
them with `aliases --aliases-file /private/path.json` containing `canonical_name`
and `aliases`; these personal values must remain outside Git.

`refresh-policy` versions pending work and previously flagged v1 results for v2
assessment. Completed history and skipped requests are preserved. Workers claim
only their supported prompt version, so old processes cannot process new-policy
jobs. Re-run the refresh after old in-flight requests drain. DuckDB shows one
current input revision per file and requests review only for `risk_level=critical`.

Piglet's shared ledger has separate `reconciliations` tables. The original caption
jobs, captions and Immich descriptions are preserved. The original campaign and
reconciliation share the $250 estimated-cost ceiling. The reconciliation ledger
also enforces an independent cap, global slots and per-runner slots. Malformed,
missing or timed-out responses are marked `skipped`; other items continue. A skipped
item is never automatically resubmitted. Reported usage is charged to the estimate
even when the answer is invalid; missing usage retains its $1 reservation. Rate
limits, authentication failures and usage exceeding the reservation still block
new submissions. Budget ceilings continue to include skipped-item holds.

Each exact input revision has a stable fingerprint. Multiple runners claim different
rows transactionally. Only completed batches are published, atomically, into private
`/local-3TB-backup/photo-enrichment/summary-reconciliation/batches/*.parquet`.
The DuckDB file beside that directory contains a `reconciled_summaries` view:

```sql
SELECT path, local_summary, luna_summary, reconciled_summary,
       conflicts, needs_visual_review
FROM reconciled_summaries
WHERE state = 'ok';
```

Open `/local-3TB-backup/photo-enrichment/summary-reconciliation/reconciliation.duckdb`
read-only. Source text is retained beside the new column. `current_inputs.parquet`
selects the newest explicitly seeded input revision, so a pending revision does not
silently return an older answer. No catalog rebuild runs during these queries.
The graph work remains out of scope.

Use `manage-reconciliation.py` with inventory-verified `--piglet root@…` and
`--runner root@…`. `inspect`, `probe`, `health`, `status` and `verify` report
aggregates; `review` deliberately displays three private examples for quality checks.
`install` backs up and updates existing runner code without copying credentials.
`configure` sets the independent ledger limits; `seed --limit 10` creates the pilot
and `seed --limit 0` selects all eligible pairs. Seeding does not submit requests.
Git policy chooses which runners may execute. `start --mac-slots 20` starts the
existing still-fawn service and a detached Mac worker; their local locks prevent
duplicates. Still-fawn's timer resumes after reboot. The detached Mac worker lasts
for this run; still-fawn continues if the Mac stops.

For the earlier global stop caused by an isolated bad answer, run
`skip-unresolved --expected-unresolved 1` before `start --mac-slots 20`. This
administrator-only operation backs up the SQLite ledger, records an audit entry,
marks the isolated unresolved item `skipped`, and republishes its existing batch.
It preserves the result, input fingerprint and cost hold. It clears only an
isolated-response block, never an authentication, rate-limit or budget block.
New bad responses record a specific failure category and, when available, bounded
raw answer text in the private ledger for later diagnosis; logs contain no captions.

`review-disagreements.py --host root@…` creates a temporary offline HTML page with
two original-photo previews, the three summary columns and unresolved conflicts.
Private page contents stay outside Git and no photos are submitted to a model.

Tests: `python -m unittest discover -s scripts/knowledge-index/luna-backfill -p 'test_*.py'`.

Piglet owns the work queue, the $250 estimated-cost ledger and the Luna Parquet dataset. The Git policy chooses the host that submits to Enterprise Codex. The Mac and still-fawn use the same worker code.

## Prepare still-fawn

From the pinned Git revision, run `CB_HOST=root@<piglet> python3 install.py --prepare-only`. Then run `python3 install-still-fawn.py --runner <still-fawn IP> --piglet <piglet IP>` using the repository inventory. The installer verifies the pinned Codex release digest, creates an unprivileged Linux account, tests its restricted SSH connection to Piglet and enables the systemd timer. The runner SSH key and Codex sign-in live under `/var/lib/ki-luna` on still-fawn. The Piglet SSH account can invoke only the ledger bridge from the still-fawn address.

Sign in interactively on still-fawn under the service account by running `sudo -u ki-luna -H /opt/knowledge-index/luna-backfill/bin/codex login --device-auth`. Complete the browser step with the intended Enterprise workspace. The timer checks login status before executing the worker.

## Cut over

Push `enabled: false` in `policy.json` and wait for the existing Mac batch to finish. Verify there are zero sent and reserved leases on Piglet before unloading the Mac launch agent. Push `runner: still-fawn` and `enabled: true`, then start the service or let the timer pick up the change. Verify the runner metric reports still-fawn and that the persisted caption count advances. The Mac worker loaded before runner selection was added defaults to the Mac and must be unloaded before enabling still-fawn.

The service allocates no GPU on still-fawn. It submits to Enterprise Codex with the saved context and writes through the same Piglet ledger.

## Reuse Immich context

The Piglet timer refreshes a private snapshot every 30 minutes from Immich's saved external-library metadata. It matches source path and file size and omits ambiguous duplicate rows. City, state, country and visible named people are caption hints. Saved confirmed annotations are still included. Existing Wikimedia landmark cache entries can add more specific references. A cache miss proceeds with the available context, so it cannot hold up caption submissions. Install the exporter with `install-immich-context.sh` from the committed checkout.

## Measure a concurrency change

Set `parallel`, `batch_size`, and `frame_slots` in the Git policy. The worker reads each new commit between batches. The shared ledger supports up to 48 reservations per batch and the worker allows up to 20 concurrent tasks. The $250 budget includes reserved work and every settled request.

Read the service journal with `journalctl -u knowledge-index-luna.service -o cat --since <trial-start>` on still-fawn and pass it to `python3 scripts/knowledge-index/luna-backfill/measure.py`. It reports media mix, saved throughput, estimated cost per caption and preparation and model-response latency for each tier. On Nov 21, 4, 8 and 20 slots delivered approximately 31, 53 and 66 saves/min. At 20, frame preparation and time waiting for it took longer than the median model request. The samples had different photo/video mixes. Keep the current placement while Piglet preparation limits throughput.

The follow-up held request concurrency at 20. Four frame slots and 24-job batches saved 62.6/min. Six frame slots and 24-job batches saved 55.9/min. Four frame slots and 48-job batches saved 69.3/min. At a common 85% photo and 15% video mix, estimated cost was $0.000583 per caption with 24 jobs and $0.000581 with 48. Bonsai saved 112 and 128 photos in equal four-minute windows before and during the 48-job trial. These are sequential production samples. The production policy uses 20 request slots, four frame slots, and 48-job batches.
