# Cricket analysis telemetry

This opt-in adapter joins the existing [shared-workload journey](../guides/shared-workload-agent.md).
It records real SDK spans in a private durable journal and exports immutable
captures accepted by the common reviewer. It does not change worker counts.
Analysis success is not publication: the verified counter stays zero until the
publication receipt adapter is connected. A capture alone cannot qualify a trial.

Install `scripts/knowledge-index/cricket/requirements-telemetry.txt` into the
worker environment. From the repository root, create a fresh private session:

```bash
python3 scripts/perf/workload.py start \
  --session /private/run-directory/session.json \
  --workload cricket-indexer --run-id UNIQUE_COMPARISON_ID --output-kind media \
  --resource mac-m5/bonsai-slots \
  --stage ingest --stage load-evidence --stage analyze \
  --stage classify --stage reconcile --stage publish --stage verify --live
```

Declare every pool used by this worker with another `--resource`. Add the matching
`resource` field to each backend in its private policy. Pass
`--telemetry-session /private/run-directory/session.json` to the existing cricket
worker command. Keep the existing authoritative ledger/evidence/state paths.
The session must reside on the actual worker host. No deployment or trial is
authorized merely by this intake; use the playbook's prerequisites and owner.

The adapter fences changes to the session, actual host, model, source allowlist,
analysis version, endpoint and configured ceiling. Desired worker counts may vary
within the same comparison, but allocation authorization belongs to the supervisor.
Use a new session directory for changed fixed inputs or a new repetition. Do not
reuse the earlier P01 intake, which lacks the required `analyze` stage.

From `scripts/knowledge-index` on that same host, close a capture into a new path:

```bash
python3 -m cricket.telemetry \
  --session /private/run-directory/session.json \
  --output /private/run-directory/closed-baseline
```

Run `scripts/perf/workload.py review --session
/private/run-directory/closed-baseline/session.json` from the repository root.
Read its decision; exit status zero does not imply eligibility. Missing media
readback and peer observations should produce a hold at this implementation stage.

The exporter includes only completed spans received by the cutoff and writes the
watermark last before publishing the directory. Captures refuse overwrites.
The journal survives restart. An exporter failure leaves a persistent failure
marker and blocks captures; repair storage and start a fresh session rather than
deleting the marker to make incomplete evidence look complete. Model error text,
prompts and credentials are excluded. Private source IDs remain trace attributes,
never metric labels. Remote request latency is not reported as GPU compute time.
