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

The live PostgreSQL concurrency test (`test-queue.mjs --postgres` inside the queue
pod) was run before publishing the classifier. Do not rerun it while workers are
claiming jobs: it inserts short-lived synthetic jobs with the real worker names.

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
