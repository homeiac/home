# Teaching Immich to recognize Waffles

Most of the dogs in my photo library are Waffles. A few are other dogs. That makes
this sound like an easy classification problem, but it also creates the easiest
way to get a convincing wrong result: label every dog Waffles.

The goal is to find Waffles by name in Immich while leaving the other dogs alone.
I supplied a reference photo: a tan dog with upright ears, a pale chest and muzzle,
and darker markings around the face. The photo is a visual reference, not a reason
to assume that every similar dog is the same animal.

The completed study identified **999 unique Waffles assets: 879 photos and 120
videos**. The original 78,900-asset inventory reached 78,895 processed assets;
five damaged source assets remain unresolved. All Waffles workers are now off,
with results, references and the dashboard retained. Recognition recall remains incomplete. The subsequent matched-photo and
pause/resume experiments below explain the observed Mac-versus-i5 performance gap. The final
results and lessons below distinguish those open questions from completed work.

## The add-on

[immich-pet-tagger](https://github.com/tedornitier/immich-pet-tagger) runs alongside
Immich. YOLO finds animals, CLIP turns their crops into visual embeddings, and a
small local classifier compares those embeddings with selected examples. Matches
appear in Immich's People section. The main classifier runs on the homelab; the
later, explicitly approved reject review used Enterprise Sol with selected images.

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

### Treating tuning as an experiment

"Try more workers" is a hypothesis, not a result. Our first preregistered sweep
paused production to measure isolated concurrency. That was the wrong operating
condition for the owner's requirement: a baseline worker must keep processing on
every available node. We interrupted the sweep, restored production, and retained
its [partial results and failures](../experiments/waffles/2026-11-26-live-tuning-results.md).
The final combined comparison did not run. We do not present a provisional peak
as sustained production performance.

The replacement design separates permanent baseline services from extra-worker
services. PostgreSQL grants independent fenced claims to each pool. Baseline
workers prioritize production; extras can process a frozen benchmark without
writing faces. Extra-process count, CPU affinity and CPU/Metal selection are live
settings. Changing them drains only extra workers. We preserved the existing
Kubernetes pod templates and Mac LaunchAgent so deployment itself need not restart
baseline models. This is additional work beyond translating Docker Compose YAML:
resource ownership and control-plane semantics must preserve useful work.

The Mac was already using its Apple GPU through PyTorch MPS/Metal. Linux workers
use CPU; the RTX remains unused. A capacity sample showed 4.1% CPU utilization
while Apple GPU utilization was 100%, including other applications. Idle CPU alone
does not prove inference is underutilizing the machine. At the owner's request,
the new experiment explicitly compares CPU-only extras with Metal extras while
the baseline remains on Metal. Grafana attributes completed photos to both backend
and actual compute device, and shows CPU, GPU, memory pressure and system swap.

still-fawn's original two-core limit was a conservative starting budget, not its
hardware limit. Its host and Kubernetes VM expose four CPUs. The extra pod has a
separate three-CPU ceiling and six GiB memory ceiling, with live one-, two- or
three-lane CPU affinity. This permits measured increases without restarting the
baseline; shared ceilings are not dedicated additional cores. VPA remains in
recommendation mode and existing workload health is part of the experiment gate.

The [replacement protocol](../experiments/waffles/2026-11-26-continuous-production.md)
freezes the same 122 photos and classifier. It requires at least 9/13 reviewed
Waffles matches, zero of 13 false positives, identical binary decisions, one
attempt per job and no unplanned process exits. An append-only journal preserves
settings, timestamps, throughput, latency, resource samples and unsuccessful trials.
Production progress is recorded separately from repeated benchmark photos.
Private photos and asset identifiers stay outside Git.

The first continuous CPU sweep produced two valid one-extra-process Mac passes
at 120.3 and 190.9 photos/minute. Three extra processes encountered sustained Mac
memory pressure, so larger configurations were skipped. still-fawn's two extra
processes measured 100.6/94.4 photos/minute with two CPU lanes and 108.4/101.2
with three. Every valid pass retained 9/13 Waffles matches, zero false positives
and identical binary decisions. Mac memory pressure interrupted the remaining
one-lane trial and the combined comparison's startup. The
[results](../experiments/waffles/2026-11-26-continuous-production-results.md)
remain explicitly incomplete; the provisional settings are not a demonstrated
combined production gain. Extra capacity was drained, and baselines continued.

A separate [one-model thread protocol](../experiments/waffles/2026-11-26-cpu-threads.md)
tests 2, 4, 8 and 16 CPU threads in both orders. Inspection found that pinned
Ultralytics resets PyTorch's detector thread pool despite `OMP_NUM_THREADS=2`.
The new Mac CPU adapter controls that selector explicitly and reports its actual
thread count. This changes only extra workers; previous process-sweep rates must
not be relabeled as verified two-thread measurements.

The thread phase then encountered sustained Mac memory pressure while starting
its first two-thread extra worker, before a measured trial. Its
[separate journal and report](../experiments/waffles/2026-11-26-cpu-threads-results.md)
retain that first rejection. It produced no thread-count winner or CPU-versus-Metal
speedup; Mac extra capacity was restored to zero while
the original Metal baseline continued.

We separately adopted still-fawn's two CPU extras using its two quality-valid
three-lane passes as evidence. A bounded production observation kept every
admitted baseline advancing, with host temperatures at 38–43°C and at least
1706 MiB available memory. This is an operational adoption, documented in the
[journal](../experiments/waffles/README.md#production-adoption-after-the-interrupted-comparison),
not a completed combined benchmark. still-fawn then entered production with one
baseline and two extra workers.

The owner challenged the Mac reduction. The journal showed that warning pressure
had cancelled trials without a demonstrated crash or quality failure. Rancher
Desktop was allocated 24 GiB while its guest used about 4.93 GiB excluding
reclaimable memory. At the owner's request, we reduced its allocation to 8 GiB,
verified recovery of 14 healthy local Kubernetes workloads and Dagger, and kept
Waffles baseline identities unchanged. This reduces the VM allocation by 16 GiB;
it does not mean the Mac immediately gains 16 GiB of free physical memory.

The owner then explicitly authorized starting jobs despite warning pressure. A
new preregistered session records warning level 2 while allowing work to continue.
Critical pressure, crashes and recognition failures still stop the trial. The old
rejections remain in the journal; they were policy decisions, not proof of an
optimal one-worker Mac configuration.

The amended run completed quality-valid two- and four-thread passes at 83.9 and
66.0 photos/minute respectively. Before repetitions completed, the owner requested
three total Mac production workers. We stopped the automatic sweep and adopted
one unchanged Metal baseline plus two CPU workers using the validated two-thread
setting. This is an explicit operational choice, not a benchmark-selected optimum.

### Trace the waiting before blaming the hardware

The subsequent diagnosis left those jobs running. A native stack sample found
70.3% of the Metal worker's main-thread samples in HTTPS reads. Small queue GETs
had medians of 18.1 ms from the Mac and 12.2 ms inside still-fawn, but read-only
candidate-selection queries took 478–646 ms, scanning and sorting roughly 61,000
jobs to select one. Source inspection showed that claims hold a per-backend
advisory lock, serializing Mac workers through that work.

Recent production processing stages averaged 0.38 seconds on Mac Metal versus
0.68 on still-fawn CPU, while committed-result intervals were 0.99 versus 1.28
seconds. These are different real photos, not a matched hardware benchmark, but
the trace and query plans explain why faster model execution gets diluted by queue
waiting. The [diagnosis](../experiments/waffles/2026-11-26-pipeline-diagnosis.md)
records the limits of those measurements. We did not change the query, index,
lock or transport during a diagnosis-only request.

### Make the ready queue cheap to consume

After the owner authorized the fix, schema v5 added a partial ordered index on
`(run_id, ordinal, asset_id)` for pending jobs with attempts remaining. Claims
resolve the small eligible-run list first, then take the first ready photo using
`SKIP LOCKED`. Independent baseline and extra pools now have independent claim
locks. Expired leases return through a bounded recovery task every 15 seconds;
fencing and the four-attempt limit remain intact. Delayed retries do not block
ready photos, and parallel completion order is naturally different from claim order.

This is work the original single-process Docker application did not need: a shared
queue has to make dispatch cheap enough that additional Kubernetes and native Mac
workers spend their time on photos. The migration is versioned in Flux, with a
verified private PostgreSQL backup before deployment. An 80,000-row scratch test
checks indexed selection along with concurrency, FIFO ordering, retries, and stale
claims. The baseline pod identities and Mac supervisor were preserved during the
queue rollout, although the API restart briefly interrupted dispatch.

The diagnostics are also reproducible. `bottleneck-report.py capture` saves an
immutable JSON snapshot and Markdown report; `compare` presents before and after.
It separates measured SQL selection time and control-request latency from the
estimated difference between processing time and completion intervals. Native
Mac stack sampling is available with `--sample-mac`. The
[FIFO capacity journal](../experiments/waffles/2026-11-26-fifo-capacity.md) records
the migration and subsequent CPU/Metal concurrency trials.

With worker counts unchanged, the stable before/after captures show Mac production
at 68.0 then 250.7 committed photos/minute, and still-fawn at 61.7 then 144.0.
The Mac baseline's completion interval fell from 2.60 to 0.72 seconds; its estimated
nonprocessing residual fell from 2.22 to 0.27 seconds. Candidate selection fell from
1,600–1,662 ms to 0.286 ms. These production windows contain different photos, so
these are observed operational changes, not a controlled hardware speedup claim.
The [generated comparison](../experiments/waffles/2026-11-26-fifo-before-after.md)
retains the measurements and caveats.

### Production is the floor, not the leftover capacity

The next CPU sweep preserved all 122 binary decisions in both passes at two,
four and eight extras. Eight extras achieved 390.0 and 499.2 photos/minute on the
canary. But diverting the extras into tests made the historical dashboard look
slow again. The owner stopped that protocol: increase production capacity first,
then experiment above it, and reduce only when results are negative.

Eight CPU extras and the permanent Metal process were returned to production.
A live observation then recorded 571 committed Mac photos in 60.6 seconds—565.3
photos/minute—while still-fawn committed 162. No Mac process crashed and the
permanent baseline identities stayed unchanged. The dashboard's five-minute
window lagged the immediate production gain.

The replacement `production-capacity.py` keeps every tested process on real
backfill work, raises the target before measuring, and retains capacity on a
measurement interruption. Two throughput windows, process stability and critical
memory pressure determine whether a step is accepted or reduced. Warning pressure
does not stop work. The old canary-diversion controller is retired, while its
results remain in the journal. This operational sweep changes concurrency only;
it does not pretend to provide new labeled accuracy results at every higher count.

### Auditing an apparent throughput cliff

The dashboard briefly showed a simultaneous backend throughput drop around
21:44 Pacific. The science journal and PostgreSQL counts contradicted a processing
collapse: Mac completed 99 photos between 21:43:30 and 21:44:30. Prometheus still
held both retired and replacement queue exporters, and the original query added
their slopes even though both represented the same durable database totals.
Deduplicating each backend's totals before calculating the five-minute derivative
corrected Mac's earlier 166.4 photos/minute display to 59.3; the later value was
82.8. The [audit](../experiments/waffles/2026-11-26-throughput-exporter-audit.md)
retains both versions. PostgreSQL-timed benchmark results were unaffected. Actual
rollout interruptions and lease recovery remain visible in the corrected history.

### Keeping asset failures local

An unavailable source asset must not become a global stop condition. During the
backfill, three existing videos returned 404 for their preview thumbnails while
their asset metadata was available. We retained them as failed assets and kept
the workers moving. Thumbnail/inference has four total attempts with a 30-second
delay. Face/tag application has a separate four-attempt bound and 60-second delay;
it reuses the classification and rechecks existing faces. Grafana exposes failure
reasons such as `thumbnail_http_404` and `apply_http_404`. Missing input is never
quietly counted as a successful non-Waffles decision. Memory and recognition
quality safeguards are separate from these per-asset failures.

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

## Trace the worker, including the time it does no useful work

An old i5 staying competitive with a much newer GPU-backed Mac warranted tracing
the actual production processes. After the indexed-FIFO fix, the Metal worker's
main thread still spent 24.85% of sampled wall time in TLS handshakes and 39.71%
in HTTPS reads. Those reads include waiting for the remote application; they do
not prove the network link is saturated. The adapter also submits one photo at
a time, preventing the upstream batch queues from gathering concurrent photos.
Fast inference hardware cannot accelerate time spent establishing connections,
waiting for responses, or waiting for the next input.

A later simultaneous throughput drop had a different, directly observed cause.
Between 23:27 and 23:31 Pacific, exhausted preview 404s rose from 80 to 333 while
all 16 Mac and four still-fawn processes remained active. An eBPF trace of the
real still-fawn worker caught three five-second error-backoff sleeps in twenty
seconds. The queue coordinator had spare CPU and no measured throttling in that
interval. Missing previews were tying up inference capacity through retries and
sleep, even though successful-photo processing times looked healthy.

The resulting intervention is a separate, bounded preview scanner ahead of
inference. Confirmed missing previews should leave the runnable queue with an
audit record, without deleting photos or interfering with claimed jobs. This
belongs in the Kubernetes adaptation just as much as persistent storage and
resource limits: API validation and retry delays should not occupy expensive
inference workers. The [science record](../experiments/waffles/2026-11-26-live-worker-traces.md)
retains the measurements, failed tracing attempts, and before/after plan. It also
records what was not measured: the privileged Mac capture emitted no per-process
GPU fields, so its 97% whole-host GPU activity cannot be attributed to Waffles.

The scanner was then deployed as its own GitOps Job with a separate ConfigMap,
so the queue and inference pods stayed up. Its first verified result excluded
52 pending jobs after 208 confirmed 404 checks while retaining the original job
records and a separate PostgreSQL audit. Mac stayed at sixteen processes and
still-fawn at four. Those exclusions are verified; a throughput speedup is not
yet established because the live library contains different work in each window.

## Reuse descriptions before paying for another full inference pass

The completed scan made a missed optimization measurable. A query over the
existing Knowledge Index descriptions selected 1,697 dog candidates from 75,722
processed assets and retained 739 of the model's 772 Waffles matches. Including
assets with no description raised the candidate set to 3,892 and retained 763
matches: 94.86% fewer inference jobs, at the cost of nine known model matches.
This is a comparison with model output, not a guarantee of true recall. A visual
audit also found clear Waffles photos the classifier itself had missed. Bare
"Waffles" was removed from the candidate query because it selected food photos.

The preview failures exposed another mistaken assumption. Every one of 32 sampled
failed videos played successfully despite returning 404 for both thumbnail sizes.
The corrected adapter recovers an oriented first frame through a separate bounded
decoder using the existing viewing permission. This adds a PVC-backed derived
image cache, backpressure, deadlines and an audit trail to the Kubernetes design.
Historical failure records are preserved, and recovery runs separately with
dog-described assets first. A first-frame classifier can still miss a dog appearing
later in the video. The [follow-up science record](../experiments/waffles/2026-11-27-quality-and-media-recovery.md)
separates measured quality, query/model agreement and recovery results.

The final seven failures also showed why HTTP status alone is insufficient.
Six generated motion-photo clips returned HTTP 200 but failed video decoding.
Two original photos still contained intact embedded video at different offsets;
validated first frames let those two classification jobs finish. Four had no
recognizable embedded stream. The remaining PNG had a readable header but broken
compressed pixels. A tolerant decoder produced a damaged image, so it failed the
quality gate. The [residual recovery journal](../experiments/waffles/2026-11-27-residual-media-recovery.md)
records the successful retries, rejected reconstruction, and source-copy checks.

## Evaluate the fallback, then verify what it proposes

Descriptions also exposed classifier false negatives: nine visibly plausible
Waffles photos among dog-labelled rejects. Five had a low-confidence rejection
and four had only negative-class predictions. A CPU replay found detection gaps,
weak identity scores and one result that now passed; without historical byte
hashes and per-crop scores, it could not explain every original numeric decision.

The fallback experiment used six approved Waffles reference views and 26 frozen
holdouts, including 13 other-dog controls. Batched Luna/Sol calls looked promising
on evaluation, but production visual inspection caught descriptions associated
with the wrong input photos. Valid JSON keys did not ensure correct image
association. We stopped that trial, preserved its results and evaluated a new
one-target-per-request Sol protocol. It accepted 11/13 Waffles holdouts, none of
the 13 controls, and recovered all four local-classifier misses in the holdout.
That small test justified a visually checked review, not unattended tagging.

Sol then reviewed all 1,060 dog-labelled rejects, nominating 261 at high confidence.
Independent visual checks accepted 164 and deferred 97. Every accepted image
received a checked tag box; 62 needed explicit placement and inspection of the
resulting crop because local animal detection was absent or ambiguous. After
verified database backups, the existing PostgreSQL coordinator applied those
recoveries with its idempotent writer and bounded retries. Model answers and
visual decisions remain separate from the original classifier history, and
categorical confidence is never disguised as a numeric classifier probability.

Immich readback verified all 164 additions: 130 images and 34 videos, with no
duplicate or missing assignments. The known total rose from 833 to **997 unique
Waffles assets**. Seven of the original nine were recovered; the railing-obscured
and flower-obscured views remain untagged. The original thumbnail fix's 61 Waffles
videos are already in the 833 baseline and are not counted again. Medium-confidence
and deferred cases remain unresolved, so this does not establish complete recall.
The [experiment journal](../experiments/waffles/2026-11-27-reject-review.md) keeps
the failed batch trial, unchanged quality gates, final counts and readback evidence.

The owner then reviewed the railing and flower views and confirmed both were
Waffles. A separate owner-confirmation run tagged and verified those two assets,
one photo and one video. The known total is now **999: 879 photos and 120 videos**,
and all nine sampled misses are recovered. The journal preserves the original
uncertain model decisions alongside this new owner evidence; neither the model
threshold nor the evaluation labels were changed.


## Before the matched-photo follow-up: what remained open

At this point, the per-worker analysis was **incomplete**. The i5's competitiveness could not be
explained solely from total backend throughput, and the eventual Mac lead does
not settle that question. A backend combines several processes: the final active
configuration had one Metal and fifteen CPU workers on the Mac, versus four CPU
workers on still-fawn. Calling the Mac line “GPU throughput” would be misleading.
Dividing each total by its configured worker count would also mix idle time,
retries, different photos and changing effective concurrency.

The closest available comparison follows the actual baseline worker on each
machine, before and after the queue intervention:

| Production capture | Mac Metal processing / completion interval | still-fawn CPU processing / completion interval |
| --- | --- | --- |
| Before indexed FIFO | 0.378 / 2.598 s | 0.679 / 2.786 s |
| After indexed FIFO | 0.449 / 0.724 s | 0.820 / 0.948 s |

Here, “processing” includes thumbnail download, preprocessing and inference;
“completion interval” includes pipeline effects and the independent writer.
These are different production photos, not isolated inference measurements.
In the first capture, Mac processing was about 1.8 times faster while completed
results arrived at nearly the same pace. That supports a concrete explanation
for **part** of the apparent parity: queue and dispatch overhead consumed much
of the wall time outside useful processing. The indexed selection and independent
claim locks substantially reduced that overhead on both machines. The
[before/after report](../experiments/waffles/2026-11-26-fifo-before-after.md)
preserves the raw aggregate timings and their definitions.

There is also evidence of waiting after that fix. Actual Metal main-thread samples
spent 24.85% in TLS handshakes, 39.71% in HTTPS reads and 30.68% in condition waits.
Source inspection found a new HTTP client connection per request and a synchronous
one-photo adapter that prevents useful cross-photo batching. still-fawn reaches
the queue over in-cluster HTTP; the Mac uses HTTPS through the gateway. These
observations identify plausible contributors, but **we did not measure their
individual causal effects through controlled changes**. Condition waits can include
asynchronous model execution. HTTPS reads include server work. Neither stack
samples nor the small control-request latency difference establish network
bandwidth saturation.

Resource attribution is unfinished too. The privileged capture reported heavy
thermal pressure and roughly 97% whole-host GPU activity, but emitted no per-task
GPU fields and overlapped another GPU workload. It cannot tell us Waffles' GPU
occupancy or how much thermal/shared-resource contention affected its speed.
Later preview failures introduced yet another delay: a live still-fawn trace
caught fifteen seconds of error-backoff sleep in a twenty-second window.
A comparison across that interval would measure error handling as much as compute.

The Mac ultimately committed 571 photos in 60.6 seconds with nine processes,
versus 162 for still-fawn in that window. That is useful capacity evidence, not a
per-worker hardware verdict. The defensible lesson is that the original chart
mixed hardware, transport, queue design, concurrency and work selection. We
removed a measured queue bottleneck; **we have not fully explained the remaining
per-worker competitiveness of still-fawn**.

A completed follow-up needs the same immutable photo bytes and classifier on each
backend, separate Mac CPU and Metal workers, recorded actual worker counts, and
stage timings for claim, fetch, decode, detection, embedding and result commit.
It should compare connection reuse and batching as separate interventions, repeat
runs in reversed order, verify unchanged identity decisions, and attribute GPU
and thermal behavior to the worker. The repeatable bottleneck calculator and
live-trace scripts are starting points; they do not replace that experiment.
Workers remain shut down until such a follow-up is deliberately started.

## Final results and lessons to carry forward

| Result | Verified outcome |
| --- | --- |
| Original inventory processing | 78,895 of 78,900; five damaged assets unresolved |
| Waffles identified before reject review | 833, including 61 recovered through the thumbnail/video fix |
| Evaluated Sol plus independent visual review | 164 additional assets |
| Explicit owner confirmation | Two additional assets; all nine sampled misses recovered |
| Final known Waffles collection | **999: 879 photos and 120 videos** |
| Operating state | All Waffles inference workers and new-upload discovery off; database, UI and dashboard retained |

These numbers describe known assignments, not complete recognition recall. The
remaining ambiguous dog-labelled cases were left unresolved, and video recovery
used a first frame that may not contain a dog visible later. The 13 negative
holdouts are useful controls, not proof of population-wide precision.

Several lessons changed the implementation:

- **Use existing descriptions to prioritize work early.** The retrospective query
  selected a much smaller candidate set while retaining most known matches.
  Include missing descriptions and audit exclusions; text filtering is not a
  guarantee that every dog photo survives.
- **A missing preview does not mean missing media.** Probe readable source media,
  validate decoding, and bound retries. Separate recovery and preflight work from
  inference so failures do not consume every worker through repeated sleeps.
- **Measure real progress by backend and by worker.** Preserve processed counts,
  in-flight work, device/pool identity and timing definitions. Verify chart math
  against committed database rows before interpreting spikes or drops.
- **Make live tuning part of the design.** During backfill, raise production
  capacity before experimenting above it; retain a running baseline and reduce
  only on negative evidence. Record actual process counts, memory pressure,
  failures and interrupted trials. Completion is a separate reason to stop the
  fleet, as we did here through Flux and disabled native services.
- **Evaluate the exact fallback protocol.** A batched model can return valid JSON
  while assigning descriptions to the wrong image. Single-target evaluation,
  independent visual review, checked tag placement and owner confirmation all
  contributed evidence that model confidence alone could not supply.
- **Keep a scientific record, including failed ideas.** Immutable input hashes,
  preserved historical results, backups, bounded retries and API readback made
  corrections auditable. Record an unresolved explanation as unresolved rather
  than turning a plausible bottleneck into a hardware conclusion.

The [final review journal](../experiments/waffles/2026-11-27-reject-review.md)
links the assignment and shutdown verification. The reusable scripts and GitOps
configuration preserve the ability to resume without keeping idle model workers
resident in memory.


## Follow-up: the same photos on each worker

We then ran the comparison the production charts could not provide: the exact
same 26 frozen images and fitted classifier, with matching image and weight hashes,
on one Mac CPU process, one Mac Metal process and one still-fawn CPU process.
Both CPU backends used two observed model threads; still-fawn's test container
had a two-core quota. Six warmups were excluded and every trial ran the full
sample forwards and backwards. Source modules and model-library versions match
across ARM and x86, with platform-specific PyTorch builds. This measures configured
workers, rather than whole-chip peak performance.

| Single process | Observed photos/min across repeated passes |
| --- | ---: |
| Mac CPU | **307–430**, initial repeats clustered at 307–332 |
| still-fawn i5 CPU | **110–113** |
| Mac Metal, serial | **170–369**, substantially variable |
| Mac CPU detector + Metal CLIP | **396–444** |

All successful variants made identical binary decisions: nine of thirteen Waffles
holdouts accepted and no false positives among thirteen controls. These are frozen
classifier decisions, not a claim that the remaining four positives are negatives.
The comparison wrote no Immich metadata; the known collection remains 999 assets.

The CPU result answers one part clearly: **the Mac CPU is about 2.7–3.9 times
faster per process than the observed i5 range on the same work**. The final
cache-path verification also varied within the Mac, so its fastest pass is not
a claimed sustained operating point. Its apparent competitiveness in the
old charts was not evidence of equal compute speed. Those charts combined queue
waiting, different photos, concurrency, preview failures and resource sharing.
The previous queue-index intervention directly measured one of those bottlenecks.

There is also a specific reason “GPU enabled” did not guarantee a large Mac win.
Metal made CLIP faster, but its detection stage could be slower than Mac CPU.
Native sampling of the actual worker found MPS indexing/`nonzero` paths entering
GPU synchronization and command-buffer waits. Python samples placed work in NMS
filtering and box extraction. Moving only the unchanged detector to CPU, keeping
CLIP on Metal, repeatedly reduced detection cost and reached 396–444 photos/min.
That is evidence for choosing devices per stage rather than assuming every stage
benefits from the same accelerator.

Network overhead is now measured on matching response bytes too. Fresh preview
requests averaged 42–44 ms on the Mac versus about 24 ms inside still-fawn.
Reusing a connection brought the Mac to 22–30 ms. This is a useful improvement,
but roughly 19 ms of extra transport cannot by itself explain the earlier parity.
The cached inference comparison removes that transport entirely.

At this stage, one causal question remained open. A later Metal repeat dropped from 357–369 to
170–184 photos/min, mainly through slower detection. Other llama-server workloads
were active, and whole-host GPU activity remained at 100% after Waffles exited.
That shows competing activity, but does not assign a precise share of GPU time
or prove a thermal bottleneck. A short pause/resume A/B of that other work requires
the owner's approval; the approved experiment follows below. The journal keeps every slow pass; it does
not replace the range with the fastest number. Four-photo batching also produced
an uneven 220/498 photos/min result, so it is not adopted as a proven speedup.

The tracing lesson is equally concrete: a caller sleeping does not mean its model
threads are idle. Linux eBPF caught the test caller in futex waits while all-thread
samples showed CLIP performing computation. Native Mac stacks and Linux eBPF
succeeded; the optional sudo DTrace/power capture was not collected because it
required a password. No privileged GPU-attribution result is claimed.

The [matched-worker science journal](../experiments/waffles/2026-11-27-matched-worker-analysis.md)
records hashes, stage timings, device-placement and connection-reuse interventions,
failed harness starts, tracing limits and repeatable scripts. The matched-photo
comparison was measured; attribution of the shared-GPU variability still required
the bounded contention experiment. Production Waffles workers remained shut down.


## The contention test: pause, measure, resume, measure again

The owner approved a short pause of the competing Mac inference server. We ran
three phases with the same frozen photos, model weights, classifier and two-thread
settings: other work running, that exact `llama-server` process paused, then the
same process resumed. Each phase tested one serial Metal process, one CPU process
and the CPU-detector/Metal-CLIP hybrid. Each table entry pools two complete passes.

| One Waffles process | Other work running | Other work paused | Other work resumed |
| --- | ---: | ---: | ---: |
| Metal detection + Metal CLIP | **346/min** | **627/min** | **375/min** |
| Mac CPU | 501/min | 519/min | 388/min |
| CPU detection + Metal CLIP | **483/min** | **767/min** | **476/min** |

Pausing the competitor increased Metal throughput by 81% versus the immediately
preceding phase, and the slowdown returned after resumption. The hybrid gained
59% and likewise returned close to its original rate. The CPU control improved
only about 4% during the pause relative to the preceding phase, although its
resumed result also varied. That supports a substantial GPU-sharing effect while
preserving evidence of ordinary shared-host scheduling variability.

The stage timings explain where the time went. Metal detection fell from 104 to
61 ms/photo while CLIP fell from 62 to 26 ms. In the hybrid, CPU detection changed
only from 47 to 41 ms while Metal CLIP fell from 68 to 28 ms. Host GPU activity
between diagnostic jobs fell from 99% to 0% when the competitor paused, then
returned to 97–98% after it resumed. Its CPU time stayed flat while stopped and
advanced afterward. These observations complement the native MPS synchronization
stacks; they do not depend on mistaking whole-host utilization for Waffles' usage.

The competing process was paused for **39 seconds**, retaining its loaded model.
An independent 90-second watchdog and a `finally` block protected resumption.
The original process identity was preserved, its health endpoint returned HTTP
200, and CPU progress was verified afterward. No service was restarted. All
recognition decisions agreed across the nine new Mac trials: nine of thirteen
positive controls accepted, zero of thirteen negative controls accepted. The
small quality set still does not establish population precision.

This completes the missing causal check. The i5 looked competitive because the
comparison included dispatch and error waits, changing concurrency, and a Mac
GPU already serving another model. On the same cached work, Mac CPU was already
substantially faster; freeing the shared GPU raised the Mac much further. The
small synchronous detector/post-processing path also incurs Metal synchronization
costs, which is why placing detection on CPU and CLIP on Metal was the fastest
repeatable option in this particular test. GPU support is not the same as having
exclusive GPU capacity or an efficient accelerator path for every stage.

This is one controlled pause/resume cycle on a live shared host, not a precise
reconstruction of every historical graph point. Pausing the other process removes
both its CPU work and its GPU submissions; the CPU control helps distinguish the
effects but does not supply exclusive GPU kernel timings or thermal attribution.
The [completed experiment journal](../experiments/waffles/2026-11-27-matched-worker-analysis.md)
retains all phases and their limits. The competing server is running again, and
the production Waffles fleet remains off.
