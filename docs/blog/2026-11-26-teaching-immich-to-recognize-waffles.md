# Teaching Immich to recognize Waffles

Most of the dogs in my photo library are Waffles. A few are other dogs. That makes
this sound like an easy classification problem, but it also creates the easiest
way to get a convincing wrong result: label every dog Waffles.

The goal is to find Waffles by name in Immich while leaving the other dogs alone.
I supplied a reference photo: a tan dog with upright ears, a pale chest and muzzle,
and darker markings around the face. The photo is a visual reference, not a reason
to assume that every similar dog is the same animal.

## The add-on

[immich-pet-tagger](https://github.com/tedornitier/immich-pet-tagger) runs alongside
Immich. YOLO finds animals, CLIP turns their crops into visual embeddings, and a
small local classifier compares those embeddings with selected examples. Matches
appear in Immich's People section. Photos and inference stay on the homelab.

This deployment targets Immich v3.4.2 and pins the tagger's v1.10.0 CPU image by
digest. The published image was checked for an AMD64 manifest before it was added
to Kubernetes. CPU is a deliberate starting point: the homelab GPU already serves
other workloads, and model quality needs to be established before optimizing speed.

## Keeping the setup in Git

The photo stack uses its own Flux source branch. Adding manifests only to master
would not add the tagger to that stack. The deployment belongs in
`gitops/clusters/homelab/apps/photo-enrichment/immich-pet-tagger/` and is included
by the photo stack's Kustomization.

The manifests describe one replica, retained persistent storage, resource limits,
health probes, a service, and a private Traefik route using the existing wildcard
certificate. The process runs without root or a Kubernetes service-account token,
and its root filesystem is read-only. The upstream UI has no built-in login, so
access stays restricted to the existing private network boundary.

The Immich API key is a dedicated credential, encrypted with SOPS before entering
Git. Its permissions cover reading photos and adding recognition metadata. It
cannot delete photos, people, or faces. This also means the add-on's destructive
reset operations are intentionally unavailable with this key.

## Teaching it what Waffles is—and what Waffles is not

Search results are candidates, not training labels. Numbered contact sheets let
me compare each candidate with the supplied photograph before enrolling it.
References should span different angles, lighting, distances, and dates. Near
duplicates from one moment make the training set look bigger than it really is.

Negative examples matter just as much. Other dogs are especially valuable here;
unrelated rooms, people, and scenery help reject background matches. Private asset
IDs, training selections, and photo thumbnails remain outside the repository.

I start with a 0.90 confidence threshold and disable the whole-image fallback by
setting its threshold above 1.0. The pinned code compares that value with a
probability, so a photo without an animal detection cannot pass. This can miss
some real Waffles photos, but it makes early review easier to trust. It is not a
claim of measured accuracy.

## Controlled rollout

Before enrollment, the setup script creates an Immich database backup. Automatic
scanning stays disabled through a small startup wrapper, including after restarts.
Manual enrollment and bounded scans still work. The wrapper has tests that verify
the disabled, enabled, and invalid-configuration cases.

A small test window comes first. Photos used to teach the classifier should not
also be counted as evidence of its accuracy. Newly added tags get a `Pets/Review`
marker so they can be inspected in Immich. Only after that review should the
background scanner and historical backfill be enabled.

## Results

Setup is awaiting approval of the dedicated API credential. The running Immich
version, Flux source branch, available CPU capacity, and pinned image have been
verified. Kubernetes accepted the workload, storage, service, route, and startup
ConfigMap in a server-side dry run. All three startup-gate tests passed. The
539 MiB database archive was fully read by `pg_restore` without connecting to a
database; this validates archive readability, not a complete disaster-recovery test.

Visual review selected 23 Waffles references and 42 negative examples. Another
10 likely Waffles photos and 13 negatives were reserved for testing. These are
selection counts, not deployed enrollment counts or accuracy results. No library
tags have been added by this setup yet. The tagger directory is not included in
the live parent Kustomization until its dedicated secret is ready.

The reusable commands, permissions, operating controls, and recovery procedure are
in the [runbook](../runbooks/immich-pet-tagger.md).
