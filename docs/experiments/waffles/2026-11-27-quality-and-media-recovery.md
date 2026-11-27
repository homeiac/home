# Production quality, description query, and media recovery

## Question and frozen inputs

The owner asked for a quality sample of existing results, recovery of readable
originals whose previews failed, and comparison with a description-based dog
query. The original historical run is retained unchanged: 78,900 assets,
75,722 completed, 3,178 preview failures, 772 accepted Waffles assets and 735 new
face assignments. A completed asset does not necessarily contain Waffles.

Private sample seed 24420261127 selected eight accepted assets per backend,
twelve additional lowest-confidence accepted assets, twelve low-confidence
rejections, twelve unknown rejections and 32 preview failures. Manifest SHA-256:
`1f9c6dfacd3efac13cd5bdbf9de419ed9febc1601f684cd247710269c5ecc3df`.
Only aggregate findings go into Git; photos, captions and asset identifiers stay
in private local files. No new cloud-model evaluation was performed.

## Existing-result visual quality

The 32 randomly selected accepted results plus twelve weakest accepted results
had no obvious wrong-dog assignments on visual inspection. This is not a claim
of perfect precision: rear views, obscured faces and young-dog appearance can
make identity uncertain without owner confirmation. Box overlays were inspected
against the source image rather than judging only the model's confidence.

Among twelve low-confidence rejected results, five clearly showed Waffles,
three had uncertain identity/views, and four showed other dogs or non-Waffles
content. All twelve sampled unknown rejections lacked an apparent Waffles image.
The conservative classifier therefore has visible recall failures. Its threshold
and training set have not been changed on the basis of this selected audit.

## Description query versus completed model results

Descriptions and tags were read from the existing Knowledge Index reconciliation
records, not regenerated. 75,658 of 78,900 assets had descriptions; 748 of the
772 accepted assets had descriptions. The broad exploratory query used dog,
puppy, canine, husky, shepherd, retriever variants and the name Waffles. A later
refinement removed bare Waffles because it also matched breakfast food.

| Query on 75,722 completed assets | Candidates | Model matches retained | Model matches omitted | Inference jobs avoided |
|---|---:|---:|---:|---:|
| Broad query including Waffles | 1,925 | 739 | 33 | 97.46% |
| Dog terms, excluding bare Waffles | 1,697 | 739 | 33 | 97.76% |
| Dog terms OR missing description | 3,892 | 763 | 9 | 94.86% |

The 33 omitted model matches comprise 24 assets without descriptions and nine
whose descriptions did not match dog terms. The broad full comparison is:

| | Model accepted Waffles | Model did not accept |
|---|---:|---:|
| Description query hit | 739 | 1,186 |
| No query hit | 33 | 73,764 |

These are **agreement counts**, not true-positive/false-positive ground truth.
A different dog is a correct dog-query hit but an appropriate Waffles rejection.
The model can miss Waffles too. Estimated inference savings exclude the prior
cost of generating descriptions, and are not an end-to-end timing benchmark.

A second frozen sample (seed 24420261128) reviewed 32 broad-query/model-negative
disagreements, all 33 query-negative/model-positive disagreements and 24 random
query-negative/model-negative results. Manifest SHA-256:
`8e6c89740554784f0909fc39234b788b78e264a47049f2afd1b886cade5b8543`.
Of the first 32, 26 contained visible dogs and six did not (food waffles, a
receipt and dog treats). At least nine clearly showed Waffles missed by the
classifier. All 33 omitted accepted assets showed dogs, with no obvious
wrong-dog assignment; identity uncertainty still applies to some views. None
of the 24 double-negative samples showed a visible dog. This stratified audit
does not support pooling a library-wide precision/recall estimate. The refined
query was chosen after inspection, so it is not evaluated on an untouched set.

Reproduce aggregate results with `compare-description-query.py`; the machine
readable report is [here](../../reference/waffles-description-query-comparison.json).
The first SQL coverage query timed out; separate bounded read-only scans and a
local join succeeded. The failed attempt is retained as an implementation note.

## Correcting the preview assumption

All 32 sampled failures were videos: preview and thumbnail endpoints returned
404, original download returned 403 with the scoped tagger key, but video
playback returned 200. Across the full failed set, 3,177 assets are VIDEO and
one is IMAGE. The earlier preflight proved **preview absence**, not media
unavailability. Its four-check audit was internally consistent but insufficient
as a reason to exclude readable media. Historical rows and that audit remain
intact so the correction does not erase the original result.

The pinned Immich v3.4.2 controller uses asset.view for video playback and
asset.download for originals. Playback recovers video bytes using the already
approved viewing scope; no credential privilege was added. The pinned image
contains ffmpeg 7.1.4-Jellyfin and Sharp 0.35.5. Eight real failed, dog-described
videos decoded successfully to an oriented first-frame JPEG in 0.306–0.815
seconds per probe. The frames were visually inspected; they include Waffles
and clearly different dogs. Sampling only the first frame can still miss a dog
that appears later in a video and is not full video recognition.

## Registered intervention and validation gate

A separate `waffles-media` service performs bounded media decoding, caches its
derived frames on a PVC and records each frame's source/hash. It accepts only
authenticated requests, and its NetworkPolicy permits only the queue pod.
Two concurrent conversions and a bounded waiting queue isolate this work from
inference models. Video input is capped at 128 MiB, image input at 32 MiB;
HTTP and decoder deadlines bound corrupt or unavailable media. Normal previews
keep their existing path. Missing previews use video playback or an original
image; image authorization failures remain errors rather than fabricated 404s.
The preflight v2 checks the underlying media route before considering exclusion.
Original v1 Job/audit resources are retained.

Before production recovery, a no-write canary uses eight inspected video frames
and the 26 owner-reviewed holdouts. Acceptance requires all jobs complete, at
least the existing 9/13 Waffles holdout positives, zero false positives on the
13 holdout negatives, and zero false positives on five different-dog video
controls. Recognition thresholds and classifier snapshots are unchanged.

The recovery manifest retains all 3,178 original failed assets in a separate
run: 145 dog-described first, 1,047 without descriptions next, and 1,986 other
described assets last. This requested recovery retains scope while applying
description priority; it does not silently discard the lower-priority group.
Existing successful jobs are not reprocessed. Results will be appended after
the canary and production run; implementation alone is not a passed experiment.
