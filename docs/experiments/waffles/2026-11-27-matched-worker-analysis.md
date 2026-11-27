# Matched-photo per-worker analysis

Preregistered November 27, 2026, after historical processing and worker shutdown.
The owner requested completing the CPU/Metal/i5 comparison using the same photos
and DTrace-like diagnostics. Earlier production-window comparisons remain
observational and do not establish relative hardware throughput.

Use the 26 frozen owner-confirmed holdout images, exact same JPEG byte hashes,
YOLO and CLIP weight hashes, fitted classifier, crop threshold .25 and identity
threshold .90. Run one isolated process at a time per machine, six warmups excluded,
then a forward and reversed full pass. Start with two explicitly configured
PyTorch/Ultralytics threads on each CPU backend. Record actual versions, batch
sizes, thread counts, resource pressure and CPU throttling. Cold model loading is
reported separately. No face writes, queue claims, retraining or production-worker
restart. Previously approved photo bytes remain local to Mac and homelab.

First isolate cached-byte decoding/detection/embedding/classification from transport
and queue service. Profile both model threads plus the caller, and sample actual
Mac worker native stacks. Follow with same-byte transport connection-reuse tests
and Linux syscall timing where available. Privileged Mac capture needs the owner
to run the supplied bounded sudo wrapper. Preserve failed traces and warnings.
Interpret condition waits as asynchronous work until model-thread profiles resolve
them; do not equate them with idle GPU. Whole-host GPU utilization is not task GPU
utilization. Compare per-photo decisions before interpreting any speed difference.
If backend decisions change, report and investigate rather than relaxing gates.

All per-photo records, classifier contents, raw traces and media remain private.
Commit aggregate results, hashes and reproducible scripts. Trial labels are
immutable. Existing caption/indexing workloads continue; their presence must be
recorded as a resource-sharing constraint, not ignored or stopped implicitly.

## Harness failures retained before measurement

The first Mac CPU startup enabled cProfile in both model threads; CLIP startup
raised `ValueError: Another profiling tool is already active`. No timed samples
were produced. That isolated process was stopped. The replacement uses all-thread
Python stack sampling plus native sampling/eBPF/DTrace, avoiding that interference.
A second startup mistake passed the cached OpenAI TorchScript checkpoint path as
OpenCLIP's generic pretrained checkpoint. Torch's weights-only loader rejected it
on both systems. The harness was restored to upstream `pretrained='openai'` with
its existing local cache, without changing weights or permitting unsafe loading.
These failed loads and their logs remain private and excluded from timing.

The exported initial classifier and frozen historical run classifier were compared:
names, scaler, model, person identity and positive/negative counts are identical.
The JSON byte hashes differ because of serialization, not fitted model values.
The first Linux guest-agent command returned an asynchronous PID; collection was
corrected to poll `qm guest exec-status` before treating the trace as complete.

## Preregistered batching intervention

After recording the serial CPU trials, add one bounded four-in-flight variant
within the same single model process. The identical 26 inputs, two reversed
passes and classifier remain fixed. Compare its binary decisions and actual
YOLO/CLIP batch sizes with serial submission. Measure pass wall time (not the sum
of overlapping per-photo latencies). This tests the synchronous-adapter hypothesis;
it is a changed dispatch policy, not a second “hardware speed” measurement.
Two diagnostic Metal models may be resident while one waits for owner tracing;
only one timed workload should compute on Mac at once. CPU timings collected
with the other Metal model sleeping are recorded with that memory-residency caveat.

## Preregistered device-split intervention

Serial Metal showed a faster CLIP stage but a slower detection stage than Mac
CPU on the same photos. Native stacks include MPS `nonzero`/indexing synchronization
and graph execution, while Python model-thread samples include NMS and per-box
extraction. Test CPU YOLO plus Metal CLIP in one otherwise unchanged serial process.
This changes device placement only, retaining detector weights, preprocessing,
thresholds and per-photo decision checks. A speedup would support a detection-path
cost rather than attributing the entire pipeline to raw GPU arithmetic. It will
not assign exclusive milliseconds to individual synchronization calls.

## Scope amendment after observed GPU variability

The initial serial Metal run measured 357–369 photos/min; its repeat measured
170–176 with nearly unchanged CLIP time but slower detection. A resource check
found ongoing llama-server workloads and 100% whole-host GPU activity after the
Waffles test had exited. Do not attribute those 100% to Waffles. The first serial
implementation ran on its main thread; the batching extension temporarily used
one ThreadPool caller even for serial runs. Restore main-thread execution for
serial controls and repeat before assigning all variability to GPU contention.
The owner has been asked to approve a bounded pause/resume of competing Mac work;
without that approval no other application is paused. The diagnostic model waiting
for sudo expired after five minutes without a timed pass. `sudo -n` confirmed a
password is required. Native `sample`, Python all-thread samples and Linux eBPF
are successful; no privileged Mac GPU attribution is claimed.

## Matched-byte results collected

The Mac is an Apple M5 Pro (18 CPU cores, 48 GB); the guest reports Intel i5-4460
at 3.20 GHz. Both runtimes have byte-identical upstream detector, embedder,
classifier and device modules, identical YOLO/CLIP weight hashes and fitted model.
Torch is 2.7.0 on ARM and 2.7.0+cpu on x86, torchvision .22.0, OpenCLIP 2.26.1,
Ultralytics 8.4.118, sklearn 1.5.2 and Pillow 10.4.0. Python patch versions differ:
3.12.14 vs 3.12.16. Actual YOLO and CLIP threads were observed as two on both;
parameter devices confirm CPU vs MPS placement. still-fawn's test container has
a two-core CPU quota. This compares configured workers, not maximum whole-chip
throughput or isolated GPU kernels.

| One model process | Photos/min, forward / reversed | Detection ms/photo | Embedding ms/photo |
| --- | --- | --- | --- |
| Mac CPU, first valid run | 309 / 332 | 73 / 67 | 111 / 105 |
| Mac CPU, repeat with actual-thread observation | 318 / 307 | 70 / 71 | 109 / 115 |
| Mac CPU, final explicit-cache verification | 430 / 335 | 53 / 66 | 77 / 102 |
| still-fawn CPU, eBPF run | 113 / 110 | 156 / 155 | 354 / 367 |
| still-fawn CPU, repeat without eBPF | 113 / 110 | 156 / 162 | 353 / 365 |
| still-fawn CPU, actual-thread observation | 112 / 112 | 157 / 154 | 357 / 363 |
| Mac Metal, original serial caller | 357 / 369 | 108 / 91 | 54 / 66 |
| Mac Metal, one ThreadPool caller | 170 / 176 | 284 / 271 | 60 / 60 |
| Mac Metal, restored main-thread repeat | 175 / 184 | 277 / 242 | 58 / 74 |
| Mac CPU YOLO + Metal CLIP, ThreadPool caller | 444 / 427 | 68 / 54 | 58 / 78 |
| Mac CPU YOLO + Metal CLIP, restored main caller | 437 / 396 | 64 / 77 | 62 / 63 |
| Mac Metal, four in flight, one model process | 220 / 498 | overlapping latency; not additive | overlapping latency; not additive |

Every valid pass accepted the same nine of thirteen Waffles holdouts and zero
of thirteen negatives. All cross-trial binary decisions agree on the same 52
pass/photo keys; identical decisions do not mean the four missed positives are
correct negatives. No new Immich face assignment or enrollment occurred.

Across all valid passes, Mac CPU is **2.7–3.9 times faster per process**
than the observed i5 range. The initial four CPU passes clustered at 307–332/min;
a final cache-path verification reached 430/335. The latter uses an explicit
OpenCLIP cache directory instead of an isolated HOME override, with the same
verified weight bytes and decisions. It also demonstrates short-run timing
variability; do not select its fastest pass as a stable operating point. Serial Metal ranges from 1.5 to 3.3 times the i5's rate under the
observed shared-machine conditions. The i5 is not matching Mac CPU compute on
identical photos. The earlier production chart hid compute differences through
queue/transport/error waits, different photos, worker counts and shared GPU use.
The old indexed-FIFO intervention remains direct evidence for queue overhead;
this follow-up does not retroactively reconstruct every earlier production window.

The Metal path is not uniformly faster than Mac CPU. It accelerates CLIP, but
its detector path can erase that gain. Native stacks of the actual Metal process
show MPS boolean indexing / `nonzero` calls entering `MPSStream::synchronize` and
`MTLCommandBuffer waitUntilCompleted`, plus graph execution. Python samples locate
YOLO time in NMS filtering and per-box extraction; the pinned detector reads box
class/confidence scalars and coordinates back into Python. Moving only YOLO to
CPU reduced detection to 54–77 ms and produced 396–444 photos/min with identical
binary decisions. This controlled placement change supports the Metal detection
path as an avoidable bottleneck in this workload. It does not exclusively time
synchronization or establish how much was caused by other GPU applications.

The restored main-thread Metal repeat remained slow, so the one-ThreadPool caller
change does not explain away the regression. Concurrent resource observations
showed 100% whole-host GPU use even after the diagnostic exited, pressure level 1,
about 18 GB available RAM and active llama-server processes. CPU use was low.
That establishes other GPU activity and a resource-sharing confound, not a measured
per-process GPU allocation or a thermal-throttling diagnosis. A contention A/B
requires the owner's pending approval to pause the competing computations.

### Transport intervention on the identical responses

Both hosts fetched the same 26 previews in forward and reversed order, using
fresh `requests.get` calls versus a persistent `requests.Session`. All 208 response
hashes (104 per host) match the frozen inference bytes, so payload differences
cannot explain this comparison.

| Backend | Fresh mean ms, two passes | Pooled mean ms, two passes |
| --- | --- | --- |
| Mac HTTPS gateway | 42.3 / 44.3 | 29.9 / 22.1 |
| still-fawn in-cluster HTTP | 23.9 / 23.8 | 23.0 / 17.7 |

Connection reuse reduced Mac request cost by roughly 12–22 ms in these windows.
The Mac's fresh-request disadvantage over still-fawn is about 19–20 ms/photo.
That is measurable, but insufficient by itself to explain the old near-parity.
This measured preview transport, not queue lock wait or GPU kernel time. Cached
inference timings deliberately exclude transport rather than subtracting a
network estimate from a mixed production timer.

### Trace interpretation and operational safeguards

A 20-second eBPF capture of the actual still-fawn benchmark process attached
successfully to thirteen syscall probes. Its main thread spent about 17.19 s
inside futex waits; file reads totaled about 4.1 ms. Model-thread Python samples
showed CLIP linear/attention operations executing while the caller waited.
Therefore “caller waiting” is not evidence that the CPU or GPU does no useful
work. Multiple thread-wait totals overlap and must not be added as wall time.
The untraced repeat closely reproduced throughput, limiting the observed eBPF
perturbation. The cgroup recorded about .655 s throttled time in the first run;
no memory OOM event appeared. Host and guest pressure counters were retained.

Native Mac `sample` captured the real worker at 5 ms intervals; Python 10 ms
samples captured caller, YOLO and CLIP thread stacks during measured passes.
These DTrace-like mechanisms supplied useful evidence without elevated Mac
access. The optional root DTrace/powermetrics capture is **not collected**:
`sudo -n` required a password and its waiting trial expired without timing.
Its failed attempt remains in the record. The wrapper prints start/progress,
validates the target PID and has a 25-second profiler-child deadline. It never
signals the model worker. An older initial native sample caught the waiting
trial rather than inference and is excluded from causal interpretation.

Four-in-flight batching produced actual mean batches about 1.5, versus 1.0 serial,
but its first pass slowed to 220/min and second reached 498/min. Warmup used serial
images and did not warm every new batch shape. Do not select the fast second pass
and call this a demonstrated stable win. The hybrid device-placement result was
more repeatable, but is a diagnostic finding; no production setting was changed.

## Reproduction and current completion state

Scripts are under `scripts/immich-pet-tagger/per-worker/`. `prepare.py` freezes
approved bytes; `preflight.py` checks host and guest; `run.py` launches one named
CPU or MPS trial; `trace-linux.py` captures actual-process eBPF and handles async
guest-exec collection. `network.py` tests fresh/pooled requests. `observe.py` uses
the installed worker runtime's psutil dependency. `audit-runtime.py` compares source
and package identities; `report.py` rejects incomplete/duplicate samples or changed
hashes. `publish-report.py` exports aggregates and explicit unresolved conditions.
Raw media, model state and traces remain private. No production baseline restarted;
all completed diagnostic processes exited. The production fleet remains off.

The [aggregate evidence](../../reference/waffles-matched-worker-analysis.json)
contains every successful trial, including slow repeats. The matched-photo CPU,
Metal and transport comparisons are done. **The shared-GPU contention A/B remains
pending owner approval**, so no claim attributes a precise fraction of historical
latency to contention. New results should extend this journal, not remove the
failed attempts or slow passes.

The final harness supplies `cache_dir` directly to OpenCLIP and preserves HOME.
Its additional 52-photo Mac CPU verification is included in the table and aggregate.
There are twelve valid trials (624 photo/pass observations from 26 unique photos).
