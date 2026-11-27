# Waffles recognition in Immich

The prepared pet tagger deployment runs alongside Immich in `immich-pilot`, managed by the
`photo-enrichment-preview` Flux Kustomization. Its source is the
`codex/photo-enrichment-217` branch, not `master`.

Current status: manifests validated; deployment awaits the dedicated API-key
approval. The parent photo Kustomization does not yet include this directory.

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
4. Run `generate-startup.py`, the startup tests, and `kubectl kustomize` on the
   tagger directory. Add the directory to the photo stack's kustomization.
5. Commit reviewed manifests and encrypted credentials to the Flux source branch.
   Run `reconcile.sh`, then `check-status.sh` and `manage.py status`.
6. Use `reference-candidates.py --output /absolute/private/candidates` to produce
   contact sheets. Visually compare against the owner's Waffles photo. Save only
   confirmed references, plus unrelated images and other dogs as negatives, in a
   private JSON file with `references` and `negatives` arrays of asset UUIDs.
7. Run `manage.py enroll --selection /absolute/private/selection.json`.
8. Test a bounded window: `manage.py scan --since YYYY-MM-DD --until YYYY-MM-DD`.
   Inspect every newly tagged photo and keep test examples separate from training.

Scripts live under `scripts/immich-pet-tagger/`. They take credentials from an
injected `IMMICH_API_KEY` or the already-existing Kubernetes Secret, never literals.
Private manifests, IDs, thumbnails, API keys, and database dumps stay outside Git.

## Automatic scans and recovery

`AUTOMATIC_SCANS=false` prevents the upstream background loop from running,
including after a pod restart. Manual scans and enrollment remain available.
The small startup wrapper changes only background scheduling; inference and API
behavior come from the pinned upstream image. `generate-startup.py` embeds it in
the versioned ConfigMap. Revisit this wrapper when upgrading upstream.

After validation, change `AUTOMATIC_SCANS` to `true` in Git and reconcile. The
upstream poller scans once at startup and hourly thereafter. Its upload-time
cursor is on the PVC. On an empty cursor it may process the entire library, so
choose the backfill explicitly and allow enough time for CPU inference.

To stop an active manual scan, run `manage.py stop`. To disable scheduled scans,
set `AUTOMATIC_SCANS=false` in Git and reconcile. To remove the workload, remove
its Kustomize resource and reconcile; the retained PVC preserves its state.
Removing the workload does not remove tags already written to Immich.
Avoid a full database restore as routine undo: it could overwrite newer changes.

## Verification record

Deployment and reference-validation results are recorded in the accompanying
[blog post](../blog/2026-11-26-teaching-immich-to-recognize-waffles.md).
