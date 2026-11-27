# Waffles recognition in Immich

The pet tagger runs alongside Immich in `immich-pilot`, managed by the
`photo-enrichment-preview` Flux Kustomization. Its source is the
`codex/photo-enrichment-217` branch, not `master`.

Waffles has 23 references and 42 negative examples. The current execution path is
a PostgreSQL queue with Mac (Metal), PVE (CPU), and still-fawn (CPU) workers.
RTX is excluded unless measurements establish a need for it. The original
single-pod historical scan was stopped during this cutover; its stopped status
does not describe the distributed run. Use `distributed.py status` and Grafana.

## Deployment

- URL: <https://pets.app.home.panderosystems.com>
- Upstream: <https://github.com/tedornitier/immich-pet-tagger>
- Image: `v1.10.0-cpu`, pinned to the verified multi-platform SHA256 digest.
- Scheduling: still-fawn, CPU only, at most two cores and 4 GiB RAM.
- State: retained 5 GiB local-path PVC at `/data`, including references and models.
- Access: existing Traefik wildcard certificate and private-network middleware.
  The upstream UI has no login; every permitted network client can administer it.
- Secret: dedicated owner API key stored only in `credentials.sops.yaml` ciphertext.
- Review marker: `Pets/Review` on photos with tags added by this tool.
- Defaults: confidence 0.90 for animal crops; fallback 1.01 disables tagging when
  no animal is detected. This deliberately sacrifices some recall.

The dedicated key has `asset.read`, `asset.view`, `person.create`, `person.read`,
`person.update`, `person.reassign`, `face.create`, `face.read`, `user.read`,
`tag.create`, and `tag.asset`. It cannot delete assets, people, or faces. Upstream
reset/delete actions that need deletion permissions will fail; do not use them.

## Setup and verification

1. Run `backup.sh /absolute/private/backup-directory` before adding metadata.
   It creates a custom-format database dump and verifies its table of contents.
2. Create the dedicated key in the owner's signed-in Immich settings with the
   permissions above; keep it in a private file outside the checkout.
3. Run `prepare-secret.py /absolute/private/key-file`. Never stage that input file.
4. Run `generate-startup.py` and `validate.py`. The latter checks the startup gate,
   full stack rendering, the image digest, and SOPS recovery without printing secrets.
   Add the directory to the photo stack's kustomization.
5. Commit reviewed manifests and encrypted credentials to the Flux source branch.
   Run `reconcile.sh`, then `check-status.sh` and `manage.py status`.
6. Use `reference-candidates.py --output /absolute/private/candidates` to produce
   contact sheets. Visually compare against the owner's Waffles photo. Save only
   confirmed references, plus unrelated images and other dogs as negatives, in a
   private JSON file with `references` and `negatives` arrays of asset UUIDs.
7. Run `manage.py enroll --selection /absolute/private/selection.json`.
8. Test a bounded window: `manage.py scan --since YYYY-MM-DD --until YYYY-MM-DD`.
   Inspect every newly tagged photo and keep test examples separate from training.
   Before writing any test tags, use `evaluate.py /private/heldout.json --output
   /private/results.log`. The input has `positive` and `negative` arrays of asset
   UUIDs. This calls the upstream classifier inside the deployed container without
   writing face assignments and rejects exact training/test overlap.

Scripts live under `scripts/immich-pet-tagger/`. They take credentials from an
injected `IMMICH_API_KEY` or the already-existing Kubernetes Secret, never literals.
Private manifests, IDs, thumbnails, API keys, and database dumps stay outside Git.

## Original UI and scan gate

Set `AUTOMATIC_SCANS=false` to prevent the upstream background loop from running,
including after a pod restart. Manual scans and enrollment remain available.
The small startup wrapper changes only background scheduling; inference and API
behavior come from the pinned upstream image. `generate-startup.py` embeds it in
the versioned ConfigMap. Revisit this wrapper when upgrading upstream.

The distributed deployment uses `AUTOMATIC_SCANS=false`. Do not start a manual
UI scan alongside the PostgreSQL writer. The UI and retained PVC are still the
source of reference enrollment; fitted classifier parameters are exported to the
queue. Pause and drain all runs, export updated parameters, and restart workers
when changing training examples. Running workers keep an immutable classifier
in memory; changing UI references alone does not update them.

To stop an active manual scan, run `manage.py stop`. To disable scheduled scans,
set `AUTOMATIC_SCANS=false` in Git and reconcile. To remove the workload, remove
its Kustomize resource and reconcile; the retained PVC preserves its state.
Removing the workload does not remove tags already written to Immich.
Avoid a full database restore as routine undo: it could overwrite newer changes.

## Dedicated Grafana dashboard

Open [Waffles · Immich Pet Tagger](https://grafana.app.home.panderosystems.com/d/immich-waffles/waffles-immich-pet-tagger).
The overview follows the Knowledge Index dashboard: processed, remaining,
completion percentage, failed jobs, estimated remaining time, and freshness.
The second row shows processed counts and shares for Mac, PVE, and still-fawn.
The node graph connects PostgreSQL to those workers and then committed results.
Nodes display completed assets and average seconds/asset; hover edges for recent
assets/minute and workers for in-flight jobs. Backend counts sum to the run's
processed total. Select a benchmark run to inspect its distribution separately.

The retained `immich-pet-tagger-metrics` is a separate, read-only Deployment. It polls four
status endpoints every 15 seconds and exposes aggregate gauges to a ServiceMonitor.
It has no Immich API key, Kubernetes token, or access to the tagger's PVC. Adding
or updating this collector does not restart the tagger or its active backfill.
Its Python runtime uses the same pinned image already verified for the tagger;
it imports only the standard library, not the inference stack.

The dashboard now uses `waffles_*` metrics from the coordinator's ServiceMonitor,
not the old scan counters. Each `(run, asset)` has one durable status, so completed
photos, percentages, and backend contributions are well-defined. Processing
includes non-Waffles results; face assignments are a separate metric. Throughput
is the five-minute slope of completed-job gauges. Average processing time covers
thumbnail fetch, detection and classification, excluding queue wait and API
writes. ETA uses recent committed throughput and can change as photo mix changes.
Metrics older than 60 seconds are hidden. Failed jobs remain separate from the
processed percentage, even after a run reaches its terminal state.

To change or validate the dashboard:

```bash
python3 scripts/immich-pet-tagger/generate-dashboard.py
python3 scripts/immich-pet-tagger/test-metrics.py
python3 scripts/immich-pet-tagger/validate.py
python3 scripts/immich-pet-tagger/check-dashboard.py --queries-only
# After committing, pushing and reconciling through Flux:
python3 scripts/immich-pet-tagger/check-dashboard.py
```

The final check compares generated manifests, the live ConfigMap, Grafana's
actually served panels, and all PromQL expressions against live Prometheus.

## PostgreSQL and worker operation

`waffles` is an isolated schema in the existing `photo_enrichment` database at
`postgres-postgresql.database.svc.cluster.local`. It is not Immich's application
database. Bootstrap follows the existing photo-enrichment scoped-role pattern;
runtime uses `waffles_worker`, never the PostgreSQL administrator role. Password
and coordinator tokens are encrypted in `queue-credentials.sops.yaml`.

Jobs use `FOR UPDATE SKIP LOCKED`, 90-second leases, 15-second heartbeats, and a
new UUID fencing token on every claim. Inference happens outside transactions.
Expired results cannot commit. After four failed attempts, a job is marked failed.
One coordinator applies classified results to Immich and retries API failures
without repeating inference. It checks existing Waffles faces before creating
one, protecting against duplicates after an uncertain write or process restart.
Neither a queue restart nor a worker restart loses committed progress.

Workers receive a restricted queue token and thumbnail proxy, not the Immich API
key or PostgreSQL credentials. The coordinator alone holds those credentials.
PVE and still-fawn each run one worker with a local model-cache PVC. PVE is bounded
to one CPU and 1536 MiB; still-fawn to two CPU and 3 GiB. The native Mac LaunchAgent
uses the same pinned upstream release, Apple Metal, and one inference worker.
`caffeinate -s` prevents sleep on AC while it runs. Battery sleep or disconnection
is handled by lease expiry. Existing Mac/RTX caption workers remain unchanged.

```bash
# Native Mac worker; setup and settings are versioned, local tokens are private.
python3 scripts/immich-pet-tagger/install-mac.py prepare
python3 scripts/immich-pet-tagger/install-mac.py start
python3 scripts/immich-pet-tagger/distributed.py status --compact
python3 scripts/immich-pet-tagger/distributed.py state historical-waffles paused
python3 scripts/immich-pet-tagger/distributed.py state historical-waffles running
```

Pause stops new claims and new API application; already-leased inference may
finish into the queue. Drain in-flight jobs before changing the classifier.
To fully stop processing, also pause `new-uploads` and stop the Mac agent if needed.
Do not delete queue rows to retry failures: retain the audit trail and investigate
the worker or thumbnail failure first.

Upload discovery runs hourly with a durable creation-time cursor and five-minute
overlap. It filters the authenticated owner's assets, excludes trashed assets,
and deduplicates against all production jobs. The cursor advances only after all
pages succeed. New jobs go into `new-uploads`; historical work keeps its original
78,900-asset scope. A partial crawl is safe to retry. Discovery is enabled with:

```bash
python3 scripts/immich-pet-tagger/distributed.py discovery --since 2026-11-26T00:00:00Z
```

The existing PostgreSQL backup covers the shared database and therefore the new
schema. Keep the original tagger reference PVC backed up separately; worker cache
PVCs can be rebuilt. Full restores can overwrite newer work and are not routine
undo operations.

## VPA and measured scaling

VPA objects for both Kubernetes workers and the original UI run in recommendation
mode (`Off`, `RequestsOnly`). The existing observer exports their target CPU and
memory requests. VPA does not resize or evict workers automatically; apply reviewed
requests through Git. The Mac is not a Kubernetes pod and has no VPA.

The matched benchmark uses 96 chronological sample photos, warm models, ABBA
profile order, and reversed inputs on the second pass. Each pass redoes inference
and writes no Immich metadata. Before is this adapter on still-fawn alone; after
is Mac + PVE + still-fawn. It is not a benchmark against upstream Docker Compose.
The two before passes averaged 105.4 photos/minute; the two after passes averaged
324.9 photos/minute, a 3.08x gain. All 96 decisions agreed across passes.
The current 26-photo holdout found 9/13 Waffles and rejected 13/13 non-Waffles on
each backend. An additional CPU check reproduced the one-photo difference from
the earlier evaluation; the 0.90 threshold was kept unchanged.
See [aggregate measurements](../reference/waffles-backend-benchmark.json).

```bash
node scripts/immich-pet-tagger/test-queue.mjs
node scripts/immich-pet-tagger/test-discovery.mjs
python3 scripts/immich-pet-tagger/benchmark.py /private/benchmark.json
python3 scripts/immich-pet-tagger/check-backend-accuracy.py /private/holdout.json /private/inventory.json
python3 scripts/immich-pet-tagger/benchmark-report.py --holdout /private/holdout.json
```

The current `test-postgres.py` runs the local queue implementation against unique
scratch tables and a separate advisory-lock namespace. It verifies concurrent
caps, fencing and baseline progress without changing production jobs or runs.

## Live tuning and experimental evidence

Immich thumbnail errors are per-asset failures. Thumbnail/inference receives at
most four total attempts, with 30 seconds before retry. Face/tag application has
its own four-attempt bound and 60-second retry delay, without repeating inference.
Exhausted jobs remain `failed` and
workers immediately continue other eligible assets; these warnings never pause
the run or experiment. `thumbnail_http_404` identifies a missing preview rather
than a negative Waffles classification. Grafana shows failures by reason. The
bounded retry path is tested against isolated PostgreSQL tables, including stale
failure acknowledgements and continuing to the next job. Memory and quality
safeguards remain separate from source-asset availability errors. `apply_http_404`
identifies a failed write-stage request. If a face was added before a review-tag
failure, its count is retained and subsequent attempts recheck existing faces;
the asset is not counted as fully processed until the whole write stage succeeds.

One permanent baseline process remains on every admitted backend: Mac uses
Apple Metal; PVE, still-fawn and fun-bedbug use CPU. Chief-horse remains desired
but guarded standby until memory headroom and its quality test permit admission.
RTX remains unused. Baseline Kubernetes templates and the Mac LaunchAgent are
preserved when deploying or tuning the separate extra-worker services.

PostgreSQL stores extra capacity, compute device and CPU affinity. Supervisors
poll every three seconds; decreases finish the current photo before unloading.
Switching CPU/Metal drains only extra processes. Each pool has independent fenced
claims; baseline processes prioritize production while extras can run benchmarks.
Zero extra slots never stops the baseline. `tune WORKER N` means total desired
processes, including the permanent one; N must be at least one.

```bash
python3 scripts/immich-pet-tagger/distributed.py tuning
python3 scripts/immich-pet-tagger/distributed.py burst mac 3 --device cpu --mode benchmark --note 'CPU comparison'
python3 scripts/immich-pet-tagger/distributed.py burst mac 3 --device mps --mode benchmark --note 'Metal comparison'
python3 scripts/immich-pet-tagger/distributed.py burst still-fawn 2 --cpu-cores 3 --note 'Additional CPU lanes'
python3 scripts/immich-pet-tagger/distributed.py burst mac 0 --note 'Drain extras; keep baseline'
python3 scripts/immich-pet-tagger/test-postgres.py
bash scripts/immich-pet-tagger/check-distributed.sh
```

Safety bounds allow Mac 0–15 extras, still-fawn 0–3 and PVE 0–1. They are not
measured optima. Mac model loading is staggered. Under the owner-approved policy,
warning pressure (level 2) is recorded and work continues; critical pressure
(level 4), unknown pressure or a failed probe refuses/drains extra capacity.
`mac_burst_guard.py` is installed only for the native Mac extra-worker service.
still-fawn's extra pod has a separate 3-CPU/6-GiB ceiling; its baseline retains
2 CPU/3 GiB. Those shared ceilings do not create five physical cores on its
four-core host. Low CPU requests and nice priority favor existing workloads.
Linux extra-worker affinity can change live across 1–3 CPU lanes without restarting
the baseline. VPA stays in recommendation mode. Native-host capacity guards remain.

Mac CPU extras also accept `--threads 2|4|8|16` (any integer 1–16 is allowed).
This drains and replaces only the extra process, then reports its effective
PyTorch setting. Baseline Metal and Linux model-thread behavior stay unchanged.
The adapter explicitly configures pinned Ultralytics because its device selector
otherwise overrides `OMP_NUM_THREADS`. Thread settings above the default apply
only to Mac CPU extras; switching back to Metal restores the default automatically.
See the [thread experiment](../experiments/waffles/2026-11-26-cpu-threads.md).
The amended run uses `thread-experiment.py PRIVATE_DIRECTORY --allow-memory-warning`.
The older continuous-process runner retains its original warning-stop protocol.

Observed production policy after the November 26 experiments: Mac, PVE and
fun-bedbug each retain one baseline; still-fawn retains its baseline plus two
CPU extras using three affinity lanes. Mac extras were initially drained by the
warning guard; after reducing Rancher Desktop from 24 GiB to 8 GiB, the owner
authorized another thread sweep with warnings observed. After two quality-valid
single passes, the owner requested three Mac production workers: one Metal baseline
plus two CPU extras at two threads each. The sweep was interrupted; no optimal
thread count is claimed. Chief-horse remains guarded standby. The
[adoption record](../experiments/waffles/README.md#production-adoption-after-the-interrupted-comparison)
distinguishes independently validated still-fawn capacity from the incomplete
combined comparison. `wait-production-progress.py` verifies that all admitted
baselines advance after a queue rollout before starting new measurements.

The [continuous-production protocol](../experiments/waffles/2026-11-26-continuous-production.md)
compares CPU and Metal on the same 122 photos, with the 26 reviewed holdouts.
`continuous-experiment.py PRIVATE_DIRECTORY` records settings, hashes, resource
samples, production deltas, quality and every failure in an append-only journal.
It never pauses production or changes baseline supervisors. Cleanup pauses only
owned benchmark runs and restores extra-pool policy. On machine failure, drain
extras with `burst WORKER 0`; production baseline workers remain independent.

The earlier [isolated experiment](../experiments/waffles/2026-11-26-live-tuning-results.md)
was interrupted when the continuous-baseline requirement was added. Its final
combined comparison never ran; preliminary results are not a final speedup claim.

## Native hosts outside Kubernetes

`install-native.py` manages `waffles-worker.service` and its capacity recheck timer
on inventory-verified fun-bedbug and chief-horse. It verifies pinned upstream and
uv archives, installs an isolated Python 3.12.14 CPU environment, and uses a
dedicated unprivileged account. Only its queue token is installed on the host.
The OpenCV wheel is replaced with the same-version headless build so graphics
packages need not be added to the hypervisor.

fun-bedbug is capped at 50% of one CPU; chief-horse at 100%. Both have 1536 MiB
memory limits, no process swap, low scheduling priority, and a read-only system
filesystem. Models start only with at least 1800 MiB available and CPU temperature
below 65°C. Running workers unload models if available memory falls below 512 MiB
or CPU temperature reaches 68°C. Missing thermal telemetry prevents startup.
Chief-horse initially remains on standby with only 933 MiB available; the Home
Assistant VM allocation is unchanged. Standby is not a failed classification.

```bash
bash scripts/immich-pet-tagger/inspect-native-hosts.sh
python3 scripts/immich-pet-tagger/install-native.py fun-bedbug prepare
python3 scripts/immich-pet-tagger/install-native.py fun-bedbug start
python3 scripts/immich-pet-tagger/install-native.py fun-bedbug status
python3 scripts/immich-pet-tagger/check-backend-accuracy.py /private/holdout.json /private/inventory.json --workers fun-bedbug
# Admit a backend only after its holdout completes without false positives:
python3 scripts/immich-pet-tagger/distributed.py workers historical-waffles mac pve still-fawn fun-bedbug
python3 scripts/immich-pet-tagger/distributed.py workers new-uploads mac pve still-fawn fun-bedbug
```

The same commands accept `chief-horse`. Do not lower guards to force startup on
a busy host. When headroom becomes available, validate it before adding it to a
production run's worker list. These native services are IaC-managed by the
versioned installer, not Flux resources or Kubernetes nodes.

## Luna/Sol fallback evaluation

Cloud fallback remains **disabled**. The approved 26-photo pilot used the supplied
reference photo, Enterprise Codex, blinded test targets, and a strict high-confidence
same-dog acceptance rule. Luna accepted 0/13 positives and Sol 2/13; neither added
a false positive, but neither recovered any of the four local misses. See
[aggregate results](../reference/waffles-frontier-evaluation.json).

`evaluate-frontier.py` performs bounded, read-only evaluations. It persists a
submission marker before calling the model and does not automatically resubmit
an uncertain failure. Inputs and answers remain in the private output directory.
`compare-frontier.py` measures incremental recovery against the CPU holdout. It
does not enable a production route. Any future evaluation must preserve the
training/holdout separation and the approved photo-sharing scope.

## Verification record

Deployment and reference-validation results are recorded in the accompanying
[blog post](../blog/2026-11-26-teaching-immich-to-recognize-waffles.md).

## Repeatable bottleneck report and FIFO capacity sweep

The single diagnostic entry point is read-only and writes immutable JSON plus a
Markdown explanation. It calculates baseline processing time, completion spacing,
and estimated residual overhead; captures the deployed candidate query plan and
small control-GET timing; and optionally records native Mac stack samples. It does
not label the residual as network latency or treat different production photos as
a matched hardware benchmark.

```bash
python3 scripts/immich-pet-tagger/bottleneck-report.py capture before --directory /private/tmp/waffles-bottleneck
# After a change, allow at least three stable production minutes:
python3 scripts/immich-pet-tagger/bottleneck-report.py capture after --directory /private/tmp/waffles-bottleneck --settle-seconds 180 --sample-mac
python3 scripts/immich-pet-tagger/bottleneck-report.py compare /private/tmp/waffles-bottleneck/before.json /private/tmp/waffles-bottleneck/after.json
```

The schema-v5 queue uses a partial `(run_id, ordinal, asset_id)` index for ready
jobs, separate baseline/extra claim locks, and a bounded expired-lease recovery
batch every 15 seconds. Ready FIFO skips delayed retries and locked jobs; parallel
completion order can differ. A worker with an expired lease remains fenced.

`mac-capacity-experiment.py PRIVATE_DIRECTORY` runs the registered repeated
CPU/Metal concurrency sweep, journals every trial, and adopts the fastest
quality-valid setting only after a two-minute production observation. One Mac
Metal baseline and all other admitted baseline workers continue; memory warnings
are observed, critical pressure rejects that configuration. On failure the
controller restores the pre-experiment Mac extra policy. The protocol and journal
are under `docs/experiments/waffles/2026-11-26-fifo-capacity*`.

### Standing production-first policy

Keep the highest accepted production capacity working. Raise capacity first, then
measure real backfill work. Do not lower or divert the production floor to make
room for a benchmark. Reduce only after negative throughput, stability, critical
pressure, or quality evidence; memory warnings are observations.

`production-capacity.py --levels 12 15` implements this policy for Mac CPU extras
using the unchanged two-thread model configuration. It records two production
windows at each level, preserves capacity on interruption or diagnostic failure,
and journals any evidence-based rollback. The previous canary-diversion controller
is retired. `production-rate.py --seconds 60` reads committed per-backend rates
without changing any work. The Grafana throughput graph uses a five-minute window,
so it responds more slowly than this one-minute database count.

### Diagnose actual production workers

`diagnose-throughput-drop.py --output /private/tmp/waffles-throughput-drop.json`
correlates twenty minutes of completed jobs, exhausted preview failures, actual
ready processes and coordinator CPU/throttling. It is read-only and prints start
and completion. Check failed attempts as well as completed-photo timing: each
worker currently sleeps five seconds after an error, so bursts of unavailable
previews depress every backend without reducing process counts.

`diagnose-mac.py PRIVATE_DIRECTORY`, `trace-live-network.py PRIVATE_DIRECTORY` and
`trace-live-linux.py PRIVATE_DIRECTORY` sample existing workers without new
inference jobs. The owner can run `sudo bash scripts/immich-pet-tagger/trace-live-mac-sudo.sh`
for a visible, bounded privileged capture. Only profiler children are terminated
at its deadline. `summarize-live-traces.py PRIVATE_DIRECTORY --output SUMMARY.json`
parses native wall stacks, network deltas, Linux syscall waits and power samples.
Keep raw captures private; record aggregate findings and failed captures in the
[science journal](../experiments/waffles/2026-11-26-live-worker-traces.md).

### Historical missing-preview scanner

The separate GitOps Job `waffles-preview-preflight-v1` checks pending historical
previews ahead of inference. Four GET responses of 404, separated by thirty
seconds, mark a still-pending job failed. `waffles.preview_checks` retains the
evidence and separate HTTP-attempt counts. It never deletes photos or job records;
claimed jobs and racing inference attempts are fenced. Other HTTP/transport errors
get at most four checks and remain unresolved for normal worker handling. A 200
response cancels the response body without decoding an image.

Run `python3 scripts/immich-pet-tagger/check-preview-preflight.py --journal` to
inspect progress, verify exclusion invariants, and append aggregate rates and
ready-worker counts to the science journal. Logs print startup and fifteen-second
progress. The Job resumes from PostgreSQL after a pod failure, has a three-hour
deadline, and is capped at four requests concurrently and twenty per second.
It enrolls the pending historical backlog at startup; hourly upload discovery
continues separately. Scanner code and its generated manifest are isolated from
the queue/worker ConfigMap, so deploying it does not restart inference.

### Evaluate and review dog-described classifier rejects

Use the frozen private study directory described in the
[reject-review journal](../experiments/waffles/2026-11-27-reject-review.md).
Personal media and per-asset decisions must stay outside Git. The completed
study has explicit owner approval for its six reference views and review cohort;
that approval does not establish an ongoing cloud upload service.

The reusable workflow is:

1. `frontier-review.py eval PRIVATE_DIRECTORY --model sol --stage v3-single`
2. `gate-reject-review.py PRIVATE_DIRECTORY --stage v3-single --models sol --output PUBLIC_AGGREGATE.json`
3. `frontier-review.py review PRIVATE_DIRECTORY --model sol --stage v3-single --workers 12`
4. Use `visual-review-candidates.py` to inspect and record each nomination, then
   `detect-reviewed-candidates.py` (or the installed CPU fallback
   `detect-reviewed-local.py`), `review-animal-boxes.py` and
   `render-reviewed-crops.py` for ambiguous placement. Every accepted box must
   refer to the reviewed bytes; manual crops require a recorded visual check.
5. `prepare-reviewed-recovery.py PRIVATE_DIRECTORY` previews and freezes the
   plan. Only after visual decisions, exact-byte box checks and verified backups
   exist, use the same command with `--apply` to enqueue the approved recovery.
6. `verify-reviewed-recovery.py PRIVATE_DIRECTORY --output PUBLIC_AGGREGATE.json`
   checks actual Immich faces. Wait for all jobs to complete and confirm no
   missing or duplicate assignments before reporting the final total.

Run these Python scripts from `scripts/immich-pet-tagger/` or provide that prefix.
These operations preserve native worker capacity and classifier thresholds.
The model runner stores submission intent before each call, bounds concurrency
and deadlines, and does not retry ambiguous submissions automatically. Resuming
settled work reuses its frozen records. Batched production review is disabled
because visually detected cross-target misassociation invalidated that trial.
