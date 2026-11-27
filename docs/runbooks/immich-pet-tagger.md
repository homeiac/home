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

## Verification record

Deployment and reference-validation results are recorded in the accompanying
[blog post](../blog/2026-11-26-teaching-immich-to-recognize-waffles.md).
