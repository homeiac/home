# Waffles recognition in Immich

The pet tagger runs alongside Immich in `immich-pilot`, managed by the
`photo-enrichment-preview` Flux Kustomization. Its source is the
`codex/photo-enrichment-217` branch, not `master`.

Current status: deployed and healthy. Waffles has 23 references and 42 negative
examples. Automatic scans run hourly with the validated confidence settings.

The owner-approved historical backfill was started on November 26, 2026 for
`1900-01-01` through `2026-11-26`. Check `manage.py status` for live progress;
do not start a duplicate scan while that one is running. The manual scan runs
inside the service and continues after the operator's terminal closes.

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

## Automatic scans and recovery

Set `AUTOMATIC_SCANS=false` to prevent the upstream background loop from running,
including after a pod restart. Manual scans and enrollment remain available.
The small startup wrapper changes only background scheduling; inference and API
behavior come from the pinned upstream image. `generate-startup.py` embeds it in
the versioned ConfigMap. Revisit this wrapper when upgrading upstream.

The validated deployment uses `AUTOMATIC_SCANS=true`. Change it in Git and reconcile. The
upstream poller scans once at startup and hourly thereafter. Its upload-time
cursor is on the PVC. The pinned version initializes an absent cursor to the
current UTC day's midnight; it does not automatically backfill older uploads.
Use an explicit manual date window for historical photos and allow enough time
for CPU inference. Manual scans use photo-taken dates and do not advance the
automatic upload-time cursor.

To stop an active manual scan, run `manage.py stop`. To disable scheduled scans,
set `AUTOMATIC_SCANS=false` in Git and reconcile. To remove the workload, remove
its Kustomize resource and reconcile; the retained PVC preserves its state.
Removing the workload does not remove tags already written to Immich.
Avoid a full database restore as routine undo: it could overwrite newer changes.

## Dedicated Grafana dashboard

Open [Waffles · Immich Pet Tagger](https://grafana.app.home.panderosystems.com/d/immich-waffles/waffles-immich-pet-tagger).
The overview follows the Knowledge Index dashboard's status-first layout. It
shows the manual scan state, fetched assets, new assignments, failures, elapsed
time, and telemetry freshness. Lower panels cover the recognition flow, outcomes,
CPU and memory limits, throttling, restarts, storage, and training example counts.

`immich-pet-tagger-metrics` is a separate, read-only Deployment. It polls four
status endpoints every 15 seconds and exposes aggregate gauges to a ServiceMonitor.
It has no Immich API key, Kubernetes token, or access to the tagger's PVC. Adding
or updating this collector does not restart the tagger or its active backfill.
Its Python runtime uses the same pinned image already verified for the tagger;
it imports only the standard library, not the inference stack.

The manual scan and latest-cycle panels intentionally stay separate: upstream
poll status includes both manual and automatic scans, so adding their counts
would double-count work. Per-scan gauges reset between runs. The tag-write pace
uses a gauge slope with a scan-start change guard, not a counter rate.

Do not sum outcomes to infer processed photos: they mix crops and assets. The
API does not expose a unique completed-asset count, so this dashboard does not
calculate completion percentage or ETA. The current photo date is the date of
the latest started asset, not a completed-through watermark. Low-confidence
review assets are shown only after a completed manual scan because upstream
v1.10.0 replaces the live count with an unpopulated review list while running.
Missing measurements stay unavailable, and live scan metrics are hidden when
collection fails or the last successful collection is over 60 seconds old.
Volume charts show the backing filesystem reported by kubelet: this local-path
driver reports filesystem-wide usage/capacity, not the tagger directory's size
or an enforced 5 GiB quota.

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

## Verification record

Deployment and reference-validation results are recorded in the accompanying
[blog post](../blog/2026-11-26-teaching-immich-to-recognize-waffles.md).
