# Adil cricket highlights implementation plan

Date: 2026-11-27

Status: Implementation started; tracked in [#250](https://github.com/homeiac/home/issues/250)

For the remaining integration with the current shared AI playbook, use the
[implementation plan](cricket-shared-workload-implementation.md),
[design](../architecture/cricket-shared-workload-design.md), and
[completion/verification checklist](cricket-shared-workload-checklist.md).
The checklist distinguishes source, merge, local-test and live-verification status;
the feature sequence and historical observations below remain product context.

Published PRs: [ledger #251](https://github.com/homeiac/home/pull/251),
[playback API #252](https://github.com/homeiac/home/pull/252), and
[correction UI #253](https://github.com/homeiac/home/pull/253),
[inventory #254](https://github.com/homeiac/home/pull/254),
[evidence #255](https://github.com/homeiac/home/pull/255),
[inference #256](https://github.com/homeiac/home/pull/256), and
[reconciliation #257](https://github.com/homeiac/home/pull/257),
[pilot operations #258](https://github.com/homeiac/home/pull/258), and
[corrected search #259](https://github.com/homeiac/home/pull/259), and
[live tuning #260](https://github.com/homeiac/home/pull/260), and
[clip export #261](https://github.com/homeiac/home/pull/261). These are stacked
review branches; publication of a PR does not imply production deployment.

The private review/search UI is deployed. A follow-up isolates the evidence and
worker tuning discovered during the live pilot; optional clip export is a
separate small PR. The experiment journal records failed classifier variants,
both comparison orders, and the selected four-worker Mac configuration.

The full album queue is enabled after 32 pilot videos and four photos completed
without worker errors, plus live playback/export and synthetic correction checks.
The initial backfill completed all 633 videos and 867 photos with zero worker errors. Outcome
accuracy remains unmeasured. The external Entire review gate could not run because
organization credit was exhausted; the stacked PRs remain open.

Live inventory on November 27: **1,500 original assets: 633 videos and 867 photos**
in “All cricket videos.” Videos total approximately 245.6 minutes; the longest is
6.8 minutes. All originals matched the media host. The newer audio-story pipeline
already has results for 632 videos (168 speech, 381 no speech, 80 uncertain speech,
3 no audio); reuse these before extracting audio again. The earlier optional
caption-transcription helper is not the only available audio source.

Build a best-effort cricket highlight browser for the existing album of 1,500+ photos and videos. Make likely highlights easy to find, play, and correct. Accuracy can improve later; corrections must work from the first usable version and survive every subsequent backfill.

## Agreed behavior

- Separate Adil batting from Adil bowling in photos and videos.
- Within this album, assume the featured batter is Adil unless corrected. Store this as a user-provided album rule, not a face recognition result. Do not automatically identify every visible player or the non-striker as Adil. Bowling identity needs its own evidence or correction.
- Find batting fours, sixes, and Adil getting out. Find wickets taken while Adil bowls as a separate category. Keep run-outs during his bowling distinguishable from wickets credited to him.
- Include likely results and ambiguous boundaries. Favor discovering useful moments over requiring certainty; no mandatory review before a suggestion becomes visible.
- For a video highlight, start 10 seconds before the start of the delivery/run-up, clamped to the beginning of the file. Include the outcome and reactions afterward. Allow manual adjustment of both ends.
- Find multiple deliveries and highlights in a long video. Photos receive role/activity labels; a still image alone should not be treated as proof of a delivery's result.
- Let the user change person, role, outcome, and timing; dismiss a false positive; add a missed moment; and undo a correction.
- Preserve original media. A highlight is initially an editable interval referencing the original; exporting a separate clip is optional.

## Existing components and integration boundary

The implementation was inspected in `.claude/worktrees/photo-memory-album-231` at commit `7256a36`, the life-stage and visible-action change associated with PR #231. Resolve these paths against the current target branch before coding; this planning checkout does not contain all of those modules at its root.

| Existing component | Reuse or required extension |
| --- | --- |
| `scripts/knowledge-index/enrichers/media_summary.py` | Reuse media probing and frame extraction. Existing summaries sample up to eight frames across a video, which is insufficient as the sole input for delivery timing in long videos. |
| `media_summary.py::transcript` | Currently returns joined, truncated text. Add a separate timestamped transcript path for cricket without changing existing caption output. |
| `scripts/knowledge-index/video-tuning/README.md` | The November 24 tuning notes report that faster-whisper was absent for that trial. Check the actual execution environment before enabling transcription; do not assume existing transcripts are available. |
| `scripts/knowledge-index/memory-acceptance/library_backfill.py` and `library_worker.py` | Reuse checkpoint and worker conventions, but give cricket work its own queue and versioned results. |
| `scripts/knowledge-index/memory-acceptance/action_gate.py` | Existing named-action publishing requires a reviewed claim or agreement across model families and confirmed regions. Keep that contract intact. Cricket suggestions use a separate, explicitly best-effort status. |
| `scripts/knowledge-index/photo_enrichment/server.py` and `memory-acceptance/library_review.py` | Extend the existing private review application and navigation. Add timed video playback and correction controls rather than creating a separate public service. |

OpenMemory was queried through the existing repository helper, but its local endpoint was unavailable. No prior memory-based solution is assumed by this plan. Live inventory and audio availability are recorded above. The album also contains unrelated scenery: album membership alone does not prove cricket activity. Model accuracy remains best effort.

## User experience

Open the cricket album's highlight view and filter by Batting, Bowling, Fours, Sixes, Adil out, or Bowling wickets. Show likely events by default, with a small Suggested, Corrected, or Confirmed status and a short explanation such as “six heard after the shot.” Provide an additional boundary-unclear filter.

Each video card opens an inline player at the proposed start, stops at the proposed end, and offers Play full video. Put Correct beside the event label. The editor offers person, batting/bowling role, outcome, and start/end controls, including “use current playback position.” Save updates the card and filters immediately and persists across refresh. Dismiss is a single action with Undo. Add highlight uses the current video and playback position without requiring the user to find an asset ID or edit JSON.

Corrections apply to the selected event by default. A separate explicit control may change the album's default batter; an individual identity correction must not silently change every clip. Correcting a cricket identity must not relabel native Immich faces.

## Data and correction contract

Use the existing private state location for a dedicated cricket SQLite ledger, with migrations and backups. Publish effective results into the knowledge index only after the correction path is working. Keep personal media, transcripts, evidence frames, runtime IDs, and credentials outside Git; tests use synthetic fixtures.

Store these concepts separately:

| Record | Required information |
| --- | --- |
| Album scope | Owner, source album ID, default batter person ID, assumption provenance, rule revision. |
| Source asset | Stable original asset ID, media type, duration, content/version fingerprint, discovery status. |
| Event | Persistent event ID, asset ID, observed delivery interval, role, actor, outcome, delivery/run-up start, outcome end, proposed clip bounds. Photos have no fabricated video timestamps. |
| Model proposal | Event ID, model/prompt/version, evidence timestamps, transcript excerpts or frame references, identity basis, confidence category and reasons, analysis run ID. |
| User revision | Event ID, changed fields, accept/dismiss/restore action, previous revision, actor and time. Corrections are durable records, not edits to model output. |
| Job | Asset and analysis version, stage, queued/running/complete/error state, checkpoint, retries, last error. |

Represent role and outcome independently. Initial outcomes: `four`, `six`, `boundary_unclear`, `dismissal`, `run_out`, `other`, `unknown`. The role and selected actor determine whether a dismissal appears under Adil out or Bowling wickets. Keep wicket credit explicit (`bowler`, `run_out`, `unknown`) so an uncertain team dismissal can still be surfaced without asserting credit.

The effective view overlays user revisions on the latest compatible proposal, field by field. A corrected field, explicitly cleared field, manually added event, or dismissal suppression always takes precedence. An unreviewed model suggestion must never be displayed as user-confirmed.

Assign event IDs in the ledger, not by hashing mutable labels or exact timestamps. On rerun, match proposals using source identity and overlapping delivery intervals. Reuse a matching event ID and retain all revisions. If a reviewed event splits, merges, or has ambiguous matches, preserve the reviewed event and flag reconciliation instead of migrating its corrections automatically. Keep unmatched reviewed/manual events visible and suppressed events suppressed. A changed source fingerprint requires remapping before old time ranges can be reused.

For automatic bounds, use `start = max(0, runup_start - 10)` and `end = min(duration, outcome_end + 5)` as initial defaults. If only release time is found, mark timing approximate and use 15 seconds of pre-roll as a configurable fallback. Enforce `0 <= start < end <= duration`; manual edits override defaults. Do not merge separate deliveries just because their highlight padding overlaps.

## Small PR sequence

Each PR should introduce one reviewable behavior with focused tests, reference its tracking issue, and remain deployable with the cricket feature disabled. Numbers below are planning sequence numbers, not existing GitHub PRs. Avoid a simultaneous model change, UI rewrite, and full-library rollout.

### PR 1 Add the cricket ledger and effective correction model

**Scope:** Add schema/migrations, persistent event IDs, proposal storage, revision storage, and the effective-result query under a proposed `scripts/knowledge-index/cricket/` module. Define the album-scoped identity rule and enums. Include backup/restore helpers before any migration of existing state.

**Acceptance:** Synthetic events can be corrected, dismissed, restored, and manually added. Tests prove field-level precedence, explicit clearing, revision conflict detection, valid time bounds, transaction rollback, and restart persistence. No media analysis or publication yet.

### PR 2 Add correction and playback endpoints

**Depends on:** PR 1.

**Scope:** Extend the existing private review server with list/detail/create/revise/dismiss/undo operations and original-video playback by authorized asset ID. Reuse existing authentication and owner checks. Support byte ranges or an existing authorized stream so long videos seek correctly. Reject arbitrary file paths and use revision checks to avoid silently overwriting a concurrent correction.

**Acceptance:** API tests cover owner isolation, request validation, stale revisions, and byte-range seeking. A seeded event plays at its saved interval. State readback reflects a correction after server restart.

### PR 3 Make highlights easy to correct in the review UI

**Depends on:** PR 2.

**Scope:** Add the cricket view, filters, player, label editor, start/end controls, Dismiss/Undo, and Add highlight. Use manually seeded private pilot events; inference is not required for this PR.

**Acceptance:** A browser journey changes four to six, changes Adil to another person, adjusts timing, dismisses/restores an event, and adds a missed moment. Refresh preserves every change; filters update without reprocessing. Playback respects the interval and offers access to the full original. Failed saves remain visibly unsaved.

### PR 4 Discover the album and classify batting versus bowling

**Depends on:** PRs 1–3.

**Scope:** Add a reusable discovery/processing command with album scope, dry-run, limit, and resume options. Resolve the existing cricket album and report actual photo/video counts. Reuse existing captions and people context where available, then propose role labels for photos and video intervals. Apply the default-batter rule only to the featured batting subject in this album. Record uncertain bowling identity separately.

**Acceptance:** Inventory deduplicates by original asset and preserves corrections on rerun. Fixtures cover helmeted batting, a visible non-striker, another bowler, mixed roles in a long video, and a non-cricket item. Likely labels appear in the correction UI without changing native face labels or existing verified actions.

### PR 5 Extract timestamped audio and visual evidence

**Depends on:** PR 4.

**Scope:** Add cached speech segments with start/end times and overlapping visual windows across the entire video. Use bounded coarse sampling followed by denser inspection of candidate delivery windows. Audio can nominate candidate windows but must not be the only path, so silent wickets are still eligible. Record source-relative timestamps and cache by source fingerprint and extraction version.

**Acceptance:** A long synthetic fixture retains evidence near its beginning, middle, and end. Tests cover chunk-offset conversion, overlap deduplication, missing audio, transcription unavailable/failed, and interrupted extraction. Silent video remains processable. Verify the selected transcription runtime on the actual worker; report unavailable audio explicitly instead of silently treating it as a successful empty transcript.

### PR 6 Propose cricket outcomes and highlight intervals

**Depends on:** PR 5.

**Scope:** Combine visual sequence and timestamped speech into likely fours, sixes, boundaries of unclear value, batting dismissals, bowling wickets, and run-outs. Include reactions and umpire signals where available. Stopping running, an appeal, celebration, or a shouted number is supporting evidence; preserve uncertainty when the outcome or actor is unclear. Distinguish “go for six” from a reaction after the shot when possible. Apply the pre-roll and aftermath defaults.

**Acceptance:** Fixtures cover multiple wickets in one video, four versus six, an unsuccessful appeal, a batting partner dismissed, a run-out during Adil's bowling, a clip ending before the outcome, and uncertain identity. Generated intervals are playable and bounded. No dual-model agreement or fixed accuracy threshold blocks likely suggestions. Run a first private sample through the UI and record obvious failure patterns.

### PR 7 Make repeated analysis preserve reviewed moments

**Depends on:** PR 6.

**Scope:** Implement proposal-to-event reconciliation, duplicate suppression across windows, checkpointed retries, and explicit reanalysis by version. Keep manual events and corrections independent of job resets. Export an effective-results snapshot for downstream readers.

**Acceptance:** Analyze, correct, restart, and reanalyze the same fixture with shifted timestamps and changed labels. The correction survives, a dismissed event stays hidden, and duplicate candidates do not create duplicate cards. Split/merge ambiguity leaves reviewed moments intact. Failed jobs can resume without restarting successful assets or duplicating revisions.

### PR 8 Validate a pilot and enable the album backfill

**Depends on:** PR 7.

**Scope:** Process 30–50 representative videos plus a few photos, then roll out to the album with resumable jobs, bounded model/decode concurrency, and lower priority than the ongoing life-stage-action backfill. Include short and long videos, batting and bowling, noisy and silent clips, helmets, ordinary deliveries, and known highlights. Use existing worker capacity mechanisms; any Kubernetes deployment/configuration changes go through Flux.

**Acceptance:** Report pilot counts, processing time per source-video minute, suggestions found, reviewed false positives, known missed highlights, and how long common corrections take. Sample ordinary deliveries as well as suggestions to expose misses. Accuracy numbers are diagnostic, not a release threshold. Release requires usable playback, successful corrections and undo, preserved corrections after rerun, bounded resource use, and recoverable jobs. Resume the remaining album without requiring manual approval of each suggestion.

**Operations:** Add aggregate queued/completed/failed counts, source-video minutes processed, evidence availability, outcome counts, and throughput to existing observability. Do not put names, transcripts, or asset paths in metric labels. Provide pause/resume/retry/status commands and a ledger backup/restore runbook. Reverting the worker/UI configuration must leave stored corrections intact.

### PR 9 Publish corrected highlight search results

**Depends on:** PR 8.

**Scope:** Feed effective results into the existing knowledge index and expose saved filters for the requested categories. Keep a direct link to the exact highlight in the review app and a link to the original asset. If native Immich albums are desired, populate owner-scoped albums with original asset IDs; retain time ranges in the highlight view. Make publication idempotent and propagate corrections, removals, and restored events.

**Acceptance:** Correcting four to six removes it from Fours and adds it to Sixes; dismissing the only qualifying event removes that asset from the corresponding managed collection. An asset with another qualifying event remains. Publication uses only this feature's managed memberships and does not rewrite unrelated albums or verified captions. UI updates are immediate; downstream changes converge on the next publish cycle with visible status and retries.

### PR 10 Add optional clip export

**Depends on:** PR 9. Optional follow-up; browsing and correction are already useful without it.

**Scope:** Export a selected effective interval as a separate playable file on demand. Key the export cache by source version and effective interval revision. Use a trim/re-encode path when accurate boundaries require it; retain audio and video synchronization. Store provenance back to the original and revision.

**Acceptance:** Export matches the corrected interval, handles file boundaries, and plays with audio. Changing timing marks previous derived exports stale and creates a new version when requested. Originals remain untouched; exports are not automatically re-ingested into the source album or analyzed as new originals.

## Rollout and completion criteria

### Live tuning requirement

Use the [shared-indexer tuning playbook](../runbooks/shared-indexer-tuning.md).
Account for cricket and knowledge indexing together, plus life-stage, Immich ML,
dog identification and other active consumers of the same physical resources.
Reinventory at each trial boundary; expired telemetry does not establish spare
capacity. A trial must pass each affected workload's progress and service budgets.
Never add unlike completion units or promote a cricket speedup that starves peers.

Once the approach is finalized, start live tuning at the highest concurrency
justified by measured backend slots, available memory, and decode capacity, then
reduce workers to find the best sustained throughput. Do not start at one and
increase gradually. Persist per-backend desired concurrency, hard bounds, and
pause/drain settings; apply changes without redeployment or losing in-flight work.
Keep baseline production workers running while extra capacity is tested.

Before trials, record the hypothesis, fixed private input hashes, resource state,
candidate worker counts, and pass/fail criteria. Measure source-video minutes per
minute, completion rate, latency, retries, memory pressure, and interference with
the existing backfill. Step down when throughput plateaus or contention grows;
immediately drain extra work on allocation failures or sustained resource pressure.
Confirm the selected configuration on matched inputs in reversed trial order and
record aggregate results and unsuccessful trials in an experiment journal. The
selected count is the fastest reproducibly useful setting, not simply the highest.

### Milestones

The first usable milestone is PR 3: the user can create and correct highlights against original videos. PR 6 adds automatic suggestions. PR 8 completes the album-scale best-effort pass. PR 9 makes corrected results discoverable through the knowledge index; PR 10 adds convenience exports.

Before starting implementation, verify the latest merged versions of the cited modules, resolve the intended album and Adil's person ID from the connected library, and inspect the current worker/runtime configuration. Ask for clarification only if album/person resolution is genuinely ambiguous. Do not require a fresh accuracy preference: best effort with easy correction is already agreed.

Completion means the requested categories are browsable, long videos offer individual timed highlights, common mistakes can be fixed without technical steps, and those fixes survive reruns and downstream publication. Model perfection, automatic ball tracking, model fine-tuning from corrections, broadcast-quality scoring, and full-library reprocessing are outside the initial scope.


## OpenLABEL alignment and native face follow-up

The existing life-stage architecture is authoritative: ASAM OpenLABEL 1.0.0,
asset-scoped face occurrence IDs, separate person IDs, typed action-role relations,
and append-only PostgreSQL scene revisions. See the established
[photo-memory ontology architecture](https://github.com/homeiac/home/blob/codex/photo-memory-album-231/docs/architecture/photo-memory-ontology.md).
The cricket SQLite ledger is the resumable work queue and correction import
source. Frame-upload JSON is an operational checkpoint, not a competing annotation
schema. Publish through the existing `openlabel_album.persist` and
`validate_scenes` writer/validator; never maintain a separate face identity store.

- PR #264: age at recording, date-conflict guards, and visible age context.
- PR #265: versioned reanalysis, retaining all corrections and existing leases.
- PR #266: sampled coordinates, bounded same-video continuity, dated jersey clues.
- Native faces: submit sampled frames as archived Immich assets; store the native
  face UUID for every returned detection, whether named, unnamed, or ungrouped.
  Frame provenance includes original asset, source fingerprint and timestamp.
  An empty result before detection completion is pending, not proof of no faces.
- OpenLABEL adapter: reuse the life-stage face binder, stable occurrence IDs,
  schema validator, and revision writer. Add a versioned cricket vocabulary for
  batting/bowling and outcomes. Preserve per-event suggestion/confirmation,
  source evidence, exact source seconds, and human overrides. Frame geometry uses
  oriented pixels and explicitly identifies the sampled frame coordinate space.
  Only a verified face-to-player association creates an actor-to-face relation;
  the album batting assumption remains a separate, correctable assertion.

Full face backfill and publication require the native-frame pilot and schema
validation to pass. Every detected face must round-trip with its actual Immich ID;
no generated UUID may be presented as a native detection. Faces missed by the
native detector need better frames or a reviewed manual face box, not fabricated
recognition. Preserve a reason on detections without a supported action, as the
life-stage renderer already does.
