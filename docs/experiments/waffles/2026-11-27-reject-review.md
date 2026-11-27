# Dog-labelled reject review: preregistered second frontier evaluation

Issue #244. Review cohort: 1,060 completed dog-labelled assets with no Waffles
match in the frozen post-recovery snapshot (794 images, 266 videos). The cohort
SHA-256 is `836fac4f17f24aae851ab45c7b6249784d279d748da9bb1a0cb8b0bb5f838615`.
Original decisions and confidence threshold remain unchanged. Nine previously
visually identified misses are diagnostic examples, not new evaluation labels.

The first single-reference Luna/Sol pilot had no false positives but recovered
none of the four local holdout misses. The revised intervention is a six-view
reference atlas selected from previously reviewed training references, covering
front, profile, back, body and age variation. No holdout asset appears in it.
Atlas SHA-256: `76500a1ef6f85dc93479d66f8bcfcd3514d844c1c60502077223b17f74b47247`.

Before viewing revised evaluation outcomes, fix these rules:

- Evaluate Luna (`gpt-6-luna`) and Sol (`gpt-6.2-sol`) independently on the existing
  owner-reviewed 13-positive/13-negative holdout. Fixed shuffle seed; batches of
  four; medium reasoning; reference atlas first. Targets receive no captions,
  local predictions or labels. Model tools and web search are disabled.
- A model may nominate production recovery candidates only after all 26 settle,
  zero high-confidence false positives, and at least one additional local holdout
  miss is recovered. Acceptance means `same_dog` plus `high` confidence.
- Confidence adjectives are not calibrated probabilities. Passing 13 negative
  controls does not prove a population false-positive rate. Proposed writes need
  subsequent independent visual review; uncertain cases remain unresolved.
- If both models qualify, use Luna for initial triage and Sol for positive or
  uncertain candidates and the nine known misses. If only Sol qualifies, use Sol.
  If neither qualifies, keep automatic frontier tagging disabled and preserve
  the failed evaluation rather than weakening the acceptance rule afterward.
- Persist intent, model/version, image/reference hashes, response, timing and token
  usage. At most two thumbnail fetch attempts. Model calls have a 240-second
  timeout; ambiguous submissions are not automatically replayed. Errors remain
  visible and do not abort unrelated review batches. All personal media and
  per-asset evidence stay outside Git.

Automatic approval review initially rejected the six-view upload because the
previous approval covered only one reference and the 26 holdouts. No model calls
were made by that rejected command. The user viewed the six-reference atlas and
explicitly approved sending it to Enterprise Luna/Sol for evaluation and the
requested reject review. Local read-only diagnosis and thumbnail caching continued
while that approval was pending. This does not enable an unbounded ongoing cloud
tagging service. Baseline workers and RTX policy remain unchanged.

The nine historical results contain five low-confidence rejections (one also
has an unknown crop) and four unknown-only rejections. A CPU replay of the actual
frozen run classifier, with unchanged image dimensions, found an absent animal
box in one case, below-threshold Waffles scores in others, and negative-class
predictions. One example passed 0.90 in the diagnostic replay although its old
result was rejected. Historical per-crop scores and input byte hashes were not
retained, so the replay is not represented as an exact reconstruction of every
original numeric decision; same dimensions do not prove identical input bytes.

## Protocol repair before production review

The first batched atlas attempt was invalid: all seven Sol batches and one Luna
batch returned an extra target, typically described as an image that did not
load. Inspection found the prompt substitution changed `TARGET_COUNT=COUNT` into
`TARGET_4=4`, and the array schema did not constrain result count. No results from
this attempt authorize writes. Preserve every original answer and submission.
Version 2 corrects the target count text and requires exact named object keys
(`target_0` through the actual last target), validates every field, and reruns both
models on the entire same frozen holdout. This is one explicit protocol repair,
not an automatic retry loop. References, image bytes, shuffle, confidence rule,
identity criteria and incremental-recovery acceptance gate remain unchanged.

## Evaluation result and production alignment failure

V2 evaluated all 26: Luna 9/13 positives and 0/13 false positives, recovering
3/4 local misses; Sol 11/13 positives and 0/13 false positives, recovering 4/4.
Both initially passed. Prioritized Sol review of the original nine returned seven
high-confidence matches and two uncertain (railing occlusion and flower-obscured
profile). No metadata was written.

During bulk Luna triage, a known miss was returned as `no_dog/high`. Local visual
inspection of all four actual inputs showed that the model's descriptions were
associated with the wrong targets despite valid object keys. This invalidates
Luna's batched decisions for production; it is more than a simple schema error.
The review parent was terminated, with original submission markers and outputs
preserved. Production baseline workers were untouched. Any interrupted model
submission is ambiguous and will not be silently replayed.

Corrective protocol v3 sends exactly ONE target plus the approved reference atlas
per request. It evaluates Sol on the full unchanged 26 holdouts before production,
with the same identity/confidence and incremental recovery gate. If it passes,
Sol reviews all 1,060 rejects directly; none are excluded by the unreliable Luna
triage. Bounded concurrency may rise to 12 independent calls without changing
image payloads or quality criteria. This explicitly supersedes two-stage routing
after observed negative quality evidence. Independent visual verification remains
mandatory before writes. This is a new, recorded protocol trial, not retries until
an individual image receives a desired answer.

## Settled single-target experiment

Sol v3 completed the unchanged 26-photo evaluation: 11/13 Waffles accepted,
0/13 negative controls accepted, and all four local-classifier misses recovered.
This passed the preregistered gate. Thirteen negatives are a small control set,
not a measured population false-positive rate. The complete frozen reject cohort
then received 1,060 independent single-target requests with no request failures.

| Sol decision | Count | Disposition |
| --- | ---: | --- |
| Same dog, high confidence | 261 | Independent visual review of every nomination |
| Same dog, medium confidence | 210 | No automatic assignment |
| Different dog | 272 | No assignment; model judgment, not ground truth |
| No dog | 121 | No assignment; model judgment, not ground truth |
| Uncertain | 196 | Unresolved |

Independent assistant visual review accepted 164 of the 261 high-confidence
nominations and deferred 97. Small, blurred, rear-facing or obstructed dogs often
did not expose enough individual markings. Those 97 are **not** measured false
positives. These are assistant-reviewed recoveries, not new owner-confirmed
training labels. Neither the 210 medium-confidence matches nor the remaining
rejects should be described as proven negatives.

All 164 accepted target bytes were checked for animal boxes. The first 109 used
the idle Kubernetes CPU detector; repeated kubelet-exec HTTP 502 errors prevented
further diagnostics there. The remaining 55 used the already-installed Mac
detector with one CPU process and two threads. No baseline worker was stopped or
reconfigured. Thirty-nine had no animal box; another 23 had ambiguous separate
boxes. Those 62 received explicit face placement, followed by visual inspection
of every resulting face crop. The other 102 had unambiguous local detections.
Image hashes bind the review, detection and placement to the same bytes.

The original nine received seven high-confidence and two medium-confidence
same-dog judgments. The seven also passed independent visual review. The view
behind a railing and the flower-obscured profile remain below the assignment
gate. The historical classifier threshold and negative class were not changed.

## Persistence and verification

Before writes, full Immich and queue-schema backups were taken and parsed with
`pg_restore`: 566,318,997 and 9,975,571 bytes respectively. The immutable recovery
plan contains 1,060 jobs: 164 classified assignments and 896 completed review
decisions with no assignment. Run `waffles-reviewed-recovery-20261127` retains
model answers, visual decisions, exact-byte hashes, placement provenance and
the evaluated protocol in private PostgreSQL. Historical classifier rows remain
unchanged. Categorical confidence is recorded explicitly; no numeric classifier
probability was invented (`probability: null`).

The existing single writer handles idempotent face assignment and the review tag,
with bounded retries. Private per-asset evidence stays outside Git; only aggregate
reports and reproducible tooling are committed. An initial readback helper omitted
the coordinator's default Immich URL and therefore produced verification errors;
the helper was corrected before accepting any readback as evidence. The writes
themselves used the established coordinator endpoint.

Reports: [evaluation](../../reference/waffles-reject-review-single-evaluation.json),
[all trial aggregates](../../reference/waffles-reject-review-results.json), and
[actual assignment readback](../../reference/waffles-reviewed-recovery.json).
The older batched trial remains in the record with `production_valid: false`;
production batched review and its second-stage cohort builder now fail closed.

At 17:48:02 UTC, the recovery run was complete: all 1,060 jobs settled, with
164 new face assignments. Immich API readback found exactly one Waffles face
on each accepted asset, zero duplicates and zero missing/readback failures.
The additions comprise 130 images and 34 videos. Seven of the original nine
were verified in that readback. The union with the previous 833 is now **997
unique Waffles assets: 878 images and 119 videos**. This recovery is separate
from the earlier thumbnail fix, which had recovered 61 Waffles videos already
included in the 833 baseline. No native worker baseline changed.

The broad frozen dog-term cohort now accounts for 976 of those 997 confirmed
assignments (812 previous plus 164 recoveries); 21 are outside it. This remains
query agreement against known assignments, not proof of collection-wide recall.
The untouched 896 review rows remain available for future evidence or owner
review. Do not silently treat their `complete` processing status as a confirmed
negative identity label.

## Owner confirmation of the final two original misses

On November 27, the owner viewed the exact railing-obscured and flower-obscured
images and confirmed: "both are Waffles. tag them and update the science journal".
That is new identity evidence, rather than a change to the model acceptance gate.
The two original medium-confidence Sol decisions and the historical classifier
rejects remain intact. Neither image was added to training or evaluation sets.

`apply-owner-confirmations.py` validates the private confirmation manifest,
image hashes and normalized tag boxes, snapshots prior queue decisions and face
state, and submits a separate idempotent run to the existing single writer.
The existing verified full backup remains available. No model call or native
worker change was needed. The manifest and before/after per-asset records stay
private; the [aggregate readback](../../reference/waffles-owner-confirmed-recovery.json)
is committed.

At 17:53:21 UTC (09:53 Pacific), `waffles-owner-confirmed-20261127` was complete.
Immich readback verified exactly one Waffles face on each asset: **two new
assignments, one photo and one video, zero duplicates**. All nine originally
sampled misses are now recovered: seven through Sol plus independent visual
review and two through explicit owner confirmation. The known collection total
is **999 unique Waffles assets: 879 photos and 120 videos**. The combined reject
recovery added 166 assets beyond the 833 baseline. The broad frozen dog-term
cohort now accounts for 978 known assignments, with 21 outside it.

This resolves the original nine; it does not resolve every ambiguous image in
the larger cohort. Of the original 896 rows with no assignment after model
review, 894 have no recovery from this study. Their processing status still does
not establish a negative identity label or complete population recall.

## Worker shutdown after completion

The owner subsequently requested shutdown of all Waffles workers. This explicit
post-completion instruction supersedes the continuous-baseline policy used while
the historical queue was active. At 18:03:23 UTC (10:03 Pacific), verification
found no unfinished production/in-flight jobs and no Waffles Mac worker processes.
Both Mac launch agents are disabled and unloaded; fun-bedbug and chief-horse
Waffles services and timers are disabled and stopped. Flux applied zero replicas
for the two Kubernetes baseline deployments, two burst deployments and media
decoder; their pods are gone. RTX remained unused.

Discovery was disabled under the same PostgreSQL advisory lock used by the
discovery loop, retaining its cursor and prior settings snapshot. Empty running
queues were paused, while completed history, unresolved cases, all 999 known
assignments, database state and PVCs were retained. Queue metrics, Grafana and
the enrollment UI remain available; automatic UI scans were already disabled.
New uploads will not receive Waffles tags until processing is deliberately resumed.

Local `.maas` DNS resolution failed for the two native hosts. The shutdown script
used each host's unique recorded inventory address with its FQDN host-key alias;
SSH key checking was preserved. Verification initially caught a native service
still stopping and was repeated successfully after shutdown completed. No
caption/indexing worker or host was shut down. See the
[aggregate shutdown verification](../../reference/waffles-worker-shutdown.json)
and the runbook's repeatable shutdown/resume procedure.
