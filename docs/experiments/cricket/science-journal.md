# Cricket highlight experiments

## November 27 2026 initial live trial contract

The album has 633 videos (245.6 minutes) and 867 photos. Existing audio analysis
matches 632 videos. The duration-stratified preparation completed 31 of 32 videos
in 115.37 seconds with four low-priority single-thread decoders; the 0.72-second
clip needed a smaller frame count. After that fix, the retry reused 31 cached
results and prepared the remaining clip in 0.74 seconds. Prepared evidence and
all per-asset records stay private.

The reviewed sample includes unrelated scenery. The classifier must be able to
return no cricket events; album membership is not evidence that an activity is
cricket. Adil's existing portrait is supplied as a suggested bowling identity
reference; the owner-provided featured-batter assumption is separate.

### Hypothesis and fixed acceptance criteria

Four Mac requests and two RTX requests are the highest currently evidenced
serving bounds. Start there, then decrease concurrency. Still-fawn's existing
CPU endpoint is not ready and remains in standby; do not start a new model just
to count it as a worker. Keep the ongoing caption/audio/life-stage workers running.

Freeze twelve first windows from distinct prepared originals, saving input and
portrait hashes before inference. Use the same inputs, prompt, and output limit
for comparisons; cached answers are never counted as new inference. Record
attempts, valid completions, elapsed seconds, source-video minutes per wall minute,
errors, raw proposals, and endpoint/resource conditions. Validate time bounds,
the correction contract, and whether sampled outputs describe the visible sport.
Exact cricket scoring is best effort and is not an accuracy gate. Invalid JSON,
out-of-window timing, systematically labeling unrelated scenery as cricket,
allocation errors, or worsening shared-workload health fail a configuration.

Run each backend independently at its high count, then lower counts. Validate the
selected setting in reverse comparison order before promotion. Drain extra work
on errors or sustained resource pressure; do not pause baseline production.
Record every failed setting and any prompt change as a new trial version.

### Observed starting resources

The media host has 12 logical CPUs, about 3.2 GiB available memory, and a one-minute
load near 39 from existing work. Source extraction is low priority and bounded;
vision inference reuses already-loaded servers. Mac reports four serving slots.
RTX is loaded and the existing caption configuration uses two parallel requests.
The initial worker policy is disabled until trials and correction-preservation
checks finish.

### Initial observations and deployment

| Version/backend | Workers | Matched windows completed | Seconds | Source minutes/minute |
| --- | ---: | ---: | ---: | ---: |
| v1 Mac | 4 | 12/12 | 418.42 | 0.392 |
| v1 Mac | 2 | 12/12 | 427.58 | 0.384 |
| v1 RTX | 2 | 0 returned | 569.20 before cancellation | 0 |

The two Mac settings are close; this is not evidence of a reproducible winner.
The RTX trial was cancelled before the 600-second request timeout after no
completion in 569 seconds. Only the cricket trial and its request subprocesses
were stopped. A two-input, one-worker recovery probe is a readiness check, not
a throughput comparison with the twelve-input trial.

Visual review of the frozen sample confirmed six unrelated-scene controls,
cricket practice footage, and one video of a projected cricket broadcast. The
initial classifier often returned neutral role=other cards and repeated unknown
events. Version v2 explicitly permits no-event responses, requests distinct
deliveries across the sequence, removes neutral non-cricket cards, and supplements
visible cricket activity with possible outcomes from timed spectator reactions.
It rejects obvious instructions/questions/negations in the reaction heuristic.
This is a new inference version; v1 timing is not treated as a v2 benchmark.
Only three of the cached video transcripts contain these reaction candidates, so
visual inference remains necessary and silent clips remain eligible.

All 32 videos and eight photos are prepared (70 windows). The private UI is live
at `/cricket` with the durable host queue initially disabled. The deployed UI
preserves existing confirmed-name and place-display fixes through a reviewed
three-way merge. The merged code passed 72 tests and 51 subtests, plus the browser
correction journey. A read-only live browser check found 633 videos/867 photos
and received a 206 response with the requested 1,024 original-video bytes.
The cricket dispatcher, photo UI, caption worker and audio-story worker were all
active after deployment; host available memory was approximately 3.1 GiB.

### Role failure, revised evidence, and high-to-low confirmation

V2 completed twelve windows at four Mac workers in 283.95 seconds, but visual
inspection showed systematic weak bowling labels on visible batters. Its lower
worker trial was therefore abandoned with partial results retained. A v3 contact
sheet test overlapped the tail of that drain and is a functional test only; its
60.66-second timing is excluded from concurrency comparisons. Contact sheets
alone did not fix the role problem.

V4 supplies the existing caption as evidence and can repair an actionless,
uncertain role using an unambiguous caption hint. It marks this explicitly as
`existing_scene_caption` with possible confidence. It never invents a result or
delivery timestamp from a caption, and never uses the batting assumption to
identify a bowler. The cache contains 152 batting-role hints, one bowling-role
hint, and 479 videos without an unambiguous hint. These are diagnostic candidate
counts, not verified cricket or identity counts.

Freeze a new four-original set (three cricket clips and an unrelated control),
including its caption context, portrait, and prepared-frame hashes. All four runs
below use these same inputs and v4 prompt/response limits, without answer-cache
reuse. The three cricket examples became batting suggestions and the unrelated
control produced no card. There are no ground-truth outcome labels or measured
recall figures; exact outcomes and bowling identity still need best-effort review.

| Order | Mac workers | Valid windows | Seconds | Source minutes/minute |
| --- | ---: | ---: | ---: | ---: |
| Initial high | 4 | 4/4 | 60.80 | 1.505 |
| Initial lower | 2 | 4/4 | 79.55 | 1.151 |
| Reverse lower | 2 | 4/4 | 103.21 | 0.887 |
| Reverse high | 4 | 4/4 | 50.66 | 1.807 |

Keep four Mac workers: they won both matched comparisons. This is a small sample
under a changing shared workload, not a universal throughput claim. RTX's
one-worker recovery also failed its first request at the 600-second bound and
was drained. Leave RTX at zero cricket workers and CPU in standby; no shared
model server or baseline backfill was stopped.

The full video preparation used eight low-priority decoders: 598 new successes,
32 reused successes, and three short-clip failures in 905.31 seconds. Allowing
missing end frames, while retaining actual successful timestamps, recovered all
three in 2.90 seconds and reused the other 630. All 633 videos are now prepared.
Photos follow at the same bounded decode maximum. Source files remain unchanged.

The production pilot contains 35 duration-stratified/reaction/bowling-candidate
videos plus eight photos. It uses four Mac workers, a persisted explicit scope,
and correction-preserving leases. Full album dispatch follows the pilot check.
The final merged app passed 80 combined tests and 51 subtests, and its browser
journey includes corrected-interval MP4 export and a 206 download response.

### Preparation completion and transactional storage stall

Photo decoding prepared 817 new photos, reused eight, and failed on 42 HEIC
originals in 105.02 seconds. The remaining 42 use Immich's existing authenticated
previews, with explicit derived-preview provenance and source-stat checks.
All 633 videos and 867 photos now have evidence and browser previews.

The pilot's heartbeat stopped while a worker thread waited in ZFS
`zil_commit_impl -> zfs_fsync -> fdatasync`. Pool health was clean. The repository
USE helper reported high CPU and run queue, no OOM or hardware errors, but exited
before completing storage checks; its generic final health message is not proof
of a healthy workload. Follow-up kernel waits and mount checks isolated the
transactional commit stall. The host's ext4 NVMe filesystem had 167 GiB free.

Paused cricket, backed up its ledger online, briefly quiesced the review API,
and moved only the ledger and worker checkpoints to NVMe. Retained old state,
units, and consistent backups. Stable paths use symlinks; the new SSD worker has
the corresponding write allowance. Baseline caption/audio services were not
stopped. New requests and heartbeat resumed, with 30 videos completed and zero
worker errors at the first follow-up. Corrected search now opens a read-only
ledger instead of attempting schema/WAL writes from the export service.
