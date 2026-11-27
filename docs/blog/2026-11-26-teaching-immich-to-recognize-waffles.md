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

## From Docker Compose to Kubernetes

The upstream [v1.10.0 Compose file](https://github.com/tedornitier/immich-pet-tagger/blob/v1.10.0/docker-compose.yml)
is the starting point: one container joins Immich's Docker network, publishes
port 8000 on the host's loopback port 2287, and bind-mounts `./data` at `/data`.
Moving that into this cluster required explicit decisions about state, access,
resource sharing, and what happens when Kubernetes restarts the process.
The application still runs from the published upstream image; there is no custom
image build or fork of its recognition code.

| Compose setup | Kubernetes deployment |
| --- | --- |
| Floating `:cpu` image tag | Versioned CPU image pinned by SHA256 digest |
| External `immich_default` Docker network | Immich's in-cluster Service DNS name |
| Loopback host port | ClusterIP Service and private Traefik IngressRoute |
| Local `./data` bind mount | 5 GiB ReadWriteOnce persistent volume claim |
| API key in the environment configuration | SOPS-encrypted Secret, injected with `secretKeyRef` |
| `restart: unless-stopped` | Deployment controller plus startup, readiness, and liveness probes |
| Background poller starts with the application | ConfigMap-mounted wrapper with an explicit enrollment gate |

### Preserve state and keep one writer

The PVC holds references, negative examples, model downloads, embedding caches,
and the automatic scanner's cursor. Losing it would lose the tagger's local
learning state even though recognition metadata already written to Immich would
remain there. The claim has Flux pruning disabled so removing the workload from
Git does not automatically remove the claim. That protection is not a backup.

This uses the cluster's `local-path` storage, so the deployment is pinned to
`k3s-vm-still-fawn`. It is a single-node stateful service, not a highly available
one. A single replica and `Recreate` update strategy avoid overlapping old and
new application instances during a rollout. ReadWriteOnce alone would not stop
two pods on the same node from accessing the volume. Updates cause a brief outage
and can interrupt an active manual backfill, so deployments should be planned
around long scans.

The upstream [Dockerfile](https://github.com/tedornitier/immich-pet-tagger/blob/v1.10.0/Dockerfile)
already sets its home, cache paths, and working directory under `/data` to support
a read-only root filesystem. We used that existing support, mounting the PVC
there and providing a separate 256 MiB `emptyDir` at `/tmp`. The Compose file's
additional `/root/.cache` volume was not carried over. Kubernetes runs the process
as UID/GID 1000 with `fsGroup: 1000` for volume access, drops all Linux capabilities,
blocks privilege escalation, and disables the service-account token mount.

### Separate internal connectivity from browser access

`IMMICH_URL` points to `immich-server.immich-pilot.svc.cluster.local:2283`, while
`IMMICH_EXTERNAL_URL` uses Immich's existing HTTPS address for browser links.
The tagger itself gets a Service on port 8000 and an IngressRoute at
`pets.app.home.panderosystems.com`, using the existing wildcard TLS certificate
and private-network middleware. No host port or new public endpoint is needed.
This boundary matters because the upstream administration UI has no login.

The dedicated API key becomes a Kubernetes Secret through Flux's SOPS decryption;
the Deployment references its `api-key` field. Only ciphertext enters Git.
The application needs Immich API access, not Kubernetes API access, which is why
it gets no service-account credential.

### Bound resource use and control startup

The pod requests 250 millicores and 1 GiB of memory, with limits of two CPU cores
and 4 GiB. One model worker, two image-fetch workers, and two OpenMP/MKL threads
keep inference concurrency bounded on a shared node. The existing `/health`
endpoint drives all three probes; the startup probe allows roughly five minutes
before failure. That endpoint confirms HTTP responsiveness, not classifier
accuracy or successful scan progress. Those need separate checks.

One application-specific adjustment was necessary for the rollout. The upstream
FastAPI lifespan starts its polling loop immediately; increasing `POLL_INTERVAL`
would only delay subsequent scans. Our small `startup.py` wrapper imports the
upstream application and substitutes an idle loop when `AUTOMATIC_SCANS` is not
`true`. Enrollment, the UI, and manual scans remain available. With the flag
enabled, the original poller runs unchanged.

The wrapper is mounted from a versioned ConfigMap and selected as the container
command. It depends on an upstream Python entry point, so it needs review when
upgrading the image. Its three tests cover disabled, enabled, and invalid flag
values. A generator keeps the ConfigMap synchronized with the readable script.

Finally, Kustomize includes the workload, startup ConfigMap, and encrypted Secret
in the photo stack. Changes reach the cluster through its existing Flux source.
Validation checks the rendered stack, pinned image, security settings, wrapper
parity, and secret recovery; a server-side dry run checks Kubernetes acceptance.
Live checks then verify the pod and private HTTPS endpoint. This makes the
deployment reproducible, while keeping recognition quality a separate validation
step.

### Give the scan its own dashboard

A dedicated [Waffles Grafana dashboard](https://grafana.app.home.panderosystems.com/d/immich-waffles/waffles-immich-pet-tagger)
initially used the Knowledge Index dashboard's overview layout: scan state, fetched assets,
new assignments, failures, elapsed time, and report freshness first, followed by
the recognition flow and resource charts. A separate read-only metrics Deployment
collects aggregate API status. It needs neither the Immich credential nor access
to the training volume, and deploying it does not restart the active backfill.
Its ServiceMonitor and dashboard ConfigMap follow the same Flux workflow.

That first dashboard made the upstream measurement boundaries explicit. Fetched assets
are not completed assets, and crop outcomes cannot be summed into a photo count.
There is no completion percentage or ETA without a distinct processed-asset
counter. The pinned API also substitutes an empty review list for live
low-confidence counts during a manual scan, so that panel waits for completion.
Freshness guards prevent old successful samples from looking like current health.
The distributed version below replaces those upstream counters with durable,
unique completed jobs, making backend distribution and completion measurable.

## Scaling beyond one container

Simply increasing the original Deployment's replica count would create several
independent scanners sharing mutable local state. It would not distribute a
single backfill reliably. We reused the existing photo-enrichment PostgreSQL
claim pattern and the native Mac worker pattern instead.

An isolated `waffles` schema lives in the existing `photo_enrichment` database.
It stores each run's classifier snapshot and one job per asset. Workers claim
jobs with `FOR UPDATE SKIP LOCKED`, renew a 90-second lease every 15 seconds,
and receive a fresh fencing token with every claim. The expensive inference runs
outside the database transaction. Results from an expired or replaced claim
cannot commit; completed work survives a pod or Mac restart.

The workers run the pinned upstream detection and embedding code and the same
fitted classifier parameters. A single coordinator writes accepted results to
Immich. It checks existing Waffles faces first, then creates missing assignments
and applies `Pets/Review`. API failures are retried without repeating inference.
Workers receive only a queue token and a restricted thumbnail proxy; they do not
receive the Immich API key or PostgreSQL password.

The initial pool has three backends:

| Backend | Runtime | Bound |
| --- | --- | --- |
| Mac | Native Python LaunchAgent, Apple Metal | One inference worker; AC-only sleep assertion |
| still-fawn | Kubernetes CPU worker | Two CPU cores, 3 GiB memory |
| PVE | Kubernetes CPU worker | One CPU core, 1536 MiB memory |

Each Kubernetes worker has its own retained model-cache PVC. The original PVC
continues to hold the reference selection; PostgreSQL holds authoritative job
progress. Existing PostgreSQL backups use `pg_dumpall`, so they include the new
schema. This adds restart recovery without pretending that local-path storage
or the existing single PostgreSQL instance is highly available.

RTX is deliberately left out. Its existing workloads remain unchanged, and the
three-backend measurements give no reason to add GPU contention yet. VPA objects
collect CPU and memory recommendations for the Kubernetes workers in `Off`,
`RequestsOnly` mode. The dashboard displays those recommendations; VPA does not
automatically evict or resize workers during the backfill.

The old automatic scanner is disabled in Git. The coordinator discovers new
uploads hourly using an owner-filtered creation-time search, a durable cursor,
and a five-minute overlap. It deduplicates against production jobs and advances
the cursor only after every search page succeeds. New uploads get a separate
run so they do not silently change the historical run's denominator.

### Before and after, measured on the same photos

We froze a 96-photo sample spanning the library chronology, warmed the models,
and ran still-fawn alone, then the three backends twice, then still-fawn alone
again. The second pass reverses the photo order. Every pass repeats inference
and benchmark mode never writes recognition metadata to Immich.

| Profile | Pass 1 | Pass 2 | Combined throughput |
| --- | ---: | ---: | ---: |
| Before: still-fawn alone | 56.253 s | 53.060 s | 105.4 photos/min |
| After: Mac + PVE + still-fawn | 18.525 s | 16.927 s | 324.9 photos/min |

That is a **3.08x throughput increase**. Mac completed 109 of the 192 distributed
jobs, still-fawn 62, and PVE 21. All 96 Waffles/non-Waffles decisions agreed across
the four passes. These timings end at the last committed result, excluding the
observer's polling delay. They compare this queue adapter on one backend versus
three; they are not a benchmark against Docker Compose. They also do not measure
the additional cost of production Immich writes or establish library-wide accuracy.
The [aggregate measurement file](../reference/waffles-backend-benchmark.json)
contains no photo IDs or thumbnails.

### Show how much work each backend actually did

The dedicated dashboard now shows processed, remaining, percentage, failed jobs,
ETA, and report age first, followed by each backend's processed count and share.
Its node graph connects PostgreSQL to Mac, PVE, and still-fawn, then to committed
results. Nodes show processed photos and mean seconds per photo. Edge hover shows
recent photos per minute; worker hover includes in-flight jobs. Time series show
each backend's throughput, latency, and completed work, alongside the before/after
measurements and VPA recommendations.

"Processed" means a durable completed result, including a photo without Waffles.
It does not mean that the photo was tagged as Waffles. Backend totals sum to the
completed total for the selected run. This is the important difference from
counting fetched photos or adding crop outcomes from the original scanner.

### Adding native hosts without moving their other workloads

fun-bedbug and chief-horse were also available outside Kubernetes. Live checks
showed why "available" needs a resource check: fun-bedbug had about 2 GiB spare
but was already at 64°C; chief-horse had 933 MiB spare while running a 6 GiB Home
Assistant VM. The inference process uses about 1.1 GiB before extra headroom.

The native deployment uses an isolated Python environment and an unprivileged
systemd service. It caps fun-bedbug at half a CPU core, chief-horse at one core,
and both at 1536 MiB with process swapping disabled. No Home Assistant or K3s VM
allocation changes. Startup requires 1800 MiB available memory and a CPU package
temperature below 65°C. While running, a drop below 512 MiB available or a rise
to 68°C stops new claims, unloads the models and returns the service to standby.
A timer rechecks capacity. The dashboard includes both native backends, even when
they have completed zero jobs or remain on standby. Chief-horse's memory guard
kept it from loading a model during initial deployment.

### Evaluate the expensive fallback before enabling it

The owner suggested Luna or Sol for tricky photos, as in the earlier enrichment
pipeline. After explicit approval for the evaluation images, we used that same
Enterprise Codex CLI path with tools and web search disabled. Each request saw
the supplied Waffles reference and one blinded test photo. The 26-photo set had
13 confirmed Waffles photos and 13 non-Waffles controls; none were training inputs.

Only `same_dog` with `high` confidence counted as acceptance. Luna accepted zero
Waffles photos at that confidence; Sol accepted two. Both rejected all 13
non-Waffles controls. Crucially, neither recovered any of the four photos missed
by the local classifier. The correct fallback criterion is incremental recovery
without false positives, not standalone recall or confident wording.

Automatic cloud escalation therefore remains disabled. We did not relax the
confidence rule after seeing the answers, and the evaluation did not write any
Immich tags. This tests the single-reference prompt we ran, not every possible
reference set or prompting strategy. Aggregate results are in the
[frontier evaluation record](../reference/waffles-frontier-evaluation.json);
photos and individual model answers stay outside Git.

## Teaching it what Waffles is—and what Waffles is not

Search results are candidates, not training labels. Numbered contact sheets let
me compare each candidate with the supplied photograph before enrolling it.
References should span different angles, lighting, distances, and dates. Near
duplicates from one moment make the training set look bigger than it really is.

Negative examples matter just as much. Other dogs are especially valuable here;
unrelated rooms, people, and scenery help reject background matches. Private asset
IDs, training selections, and photo thumbnails remain outside the repository.

I use a 0.90 confidence threshold and disable the whole-image fallback by
setting its threshold above 1.0. The pinned code compares that value with a
probability, so a photo without an animal detection cannot pass. This can miss
some real Waffles photos, but it makes early review easier to trust. It is not a
claim of measured accuracy.

## Controlled rollout

Before enrollment, the setup script creates an Immich database backup. During
enrollment, automatic scanning stayed disabled through a small startup wrapper,
including after restarts.
Manual enrollment and bounded scans still work. The wrapper has tests that verify
the disabled, enabled, and invalid-configuration cases.

A small test window comes first. Photos used to teach the classifier should not
also be counted as evidence of its accuracy. Newly added tags get a `Pets/Review`
marker so they can be inspected in Immich. Only after that review should the
background scanner and historical backfill be enabled.

## Results

The dedicated credential was approved, encrypted, and deployed through Flux.
The running Immich version, Flux source branch, available CPU capacity, and pinned
image have been verified. Kubernetes accepted the workload, storage, service, route, and startup
ConfigMap in a server-side dry run. All three startup-gate tests passed. The
539 MiB database archive was fully read by `pg_restore` without connecting to a
database; this validates archive readability, not a complete disaster-recovery test.

The pod is healthy, the private HTTPS endpoint responds successfully, and all
23 reviewed Waffles references were tagged without an API failure. The deployed
classifier has 42 negative examples. Across the read-only checks, it recognized
10 of 13 Waffles photos and rejected all 13 clear non-Waffles examples, including
three different-looking dogs. Three real Waffles photos were missed: two fell
below the confidence threshold, and one lacked an animal detection. This is a
small, selected spot check, not a library-wide accuracy guarantee.

The most instructive moment was a labeling mistake during review. Three photos
showed a much darker, muddy-looking dog. The model confidently said Waffles. I
asked the owner, who confirmed that it was Waffles. Those images stayed out of
training and became useful examples of recognition across a dramatic appearance
change. A model's result is only a false positive when the ground-truth label is
actually correct.

A separate one-day scan fetched 12 assets and added six Waffles tags, all checked
visually. Its remaining counters were three low-confidence crops, two unknown
crops, one already-tagged match, and one unavailable thumbnail, with zero API
failures. These counters mix assets and detected crops, so they should not be
summed as mutually exclusive photo counts. The conservative behavior leaves
some photos for review instead of forcing a label.

With those initial checks complete, hourly scanning was enabled through Git. The upstream
upload-time cursor starts at the current UTC day's midnight when absent; older
photos need a separate manual historical scan. The scan panel exposes progress
and can stop that backfill without deleting existing recognition metadata.

On November 26, 2026, the owner explicitly approved the full historical backfill.
It was initially started for January 1, 1900 through November 26, 2026 using the committed
`manage.py scan` command. This is a background scan, not a claim that the historical
library has finished processing. The deployment retains the same two-core CPU
limit, 4 GiB memory limit, and conservative recognition thresholds. During the
distributed cutover, that original scan was stopped and its 78,900-asset scope
was frozen into the PostgreSQL historical run. Existing tags are preserved and
checked before creating any new face assignment.

The same 26 reviewed holdouts were then checked on every backend. Each accepted
9 of 13 Waffles photos and rejected all 13 non-Waffles photos. One previously
accepted photo now falls just below the 0.90 threshold. A fresh evaluation inside
the original upstream CPU pod also misses that photo; the frozen classifier
scores its two crops about 0.872 and 0.892. This is not a Mac-versus-CPU disagreement.
The earlier and current fitted parameters differ slightly, so the earlier 10/13
spot check must not be presented as the current result. The threshold remains
0.90; we did not tune it on the holdout to make the score look better.

The reusable commands, permissions, operating controls, and recovery procedure are
in the [runbook](../runbooks/immich-pet-tagger.md).
