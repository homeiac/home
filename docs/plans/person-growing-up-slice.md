# Growing up album slice discussion plan

Status: proposed for discussion, no implementation. Updated November 25, 2026.
Parent: [north star and definition of done](photo-memory-platform.md). Issue: #217.

## User outcome

Ask for an album of the owner's eldest son growing up. Open a chronological,
representative collection in Immich, inspect each photo with a person-enriched
account, and refine the collection without losing corrections. The concrete
identity is held in a private fixture; the plan calls him the selected child.

Person enrichment is part of this slice, not a later enhancement. A correct face
label next to a caption saying only "a boy" does not pass. Descriptions must name
the confirmed child and other confirmed principal people when the image/action
association is supported. No exact age, birthday, relationship or location is
invented to make the story richer.

## Existing app candidates

Documentation reviewed November 25; selection requires a pinned-version check
against our deployment. No app has been installed or tested by this planning work.

| Candidate | Documented fit | What must be established for this slice |
|---|---|---|
| [Immich Photo Manager](https://github.com/drolosoft/immich-photo-manager) | MCP tools for search, people, dates and album operations through an assistant | Actual version compatibility, scoped tool access and how to supply our saved context without recaptioning |
| [Immich Memories film types](https://sam-dumont.github.io/immich-memories/docs/reference/film-types/) | Person spotlight across years and an existing-album input | Its person route requires an Immich named face; a film is a downstream output, not the album acceptance result |
| [Immich Memories preparation](https://sam-dumont.github.io/immich-memories/docs/reference/preparation/) | Banks picture facts; GPU/Full modes add captions | Whether our facts can be imported or bridged; otherwise start without another caption pass and account for required preparation separately |

Recommended initial delivery is an Immich album, with Photo Manager evaluated as
the conversational entry point. Treat a Memories film made from that album as a
consumer-compatibility proof after album/person-context acceptance. Its experimental
natural-language mode is not the sole parser or a required first-slice dependency.
Do not build a new album renderer or require a graph database for this slice.

## Proposed slices within this first journey

### A Establish identity and reference evidence

Map the confirmed local identity and aliases to stable Immich person/asset IDs.
Measure the person and era coverage each source actually has. Our face labels are
not automatically native Immich assignments. Use mapped source assets to create
the candidate pool if native recognition misses childhood photos; do not enable
bulk native face writes just to make the integration appear complete.

Build a private evaluation set of about 30–50 photos spanning available early,
middle and recent years. Include group photos, a similar-looking non-target person,
missing GPS, uncertain dates, a stale caption, and the owner's confirmed-name/photo-
board regression. The latter tests the shared enrichment behavior even when the
selected child is absent. Add exact/near copies and known missing Immich mappings.
Expected identities come from confirmed annotations; ambiguous cases are separated.
Reuse these annotations rather than asking the owner to label everything again.

Deliverable for discussion: coverage report, identity mapping proposal, private
reference-set inventory and missing-asset dispositions. No imports or face changes
occur during discovery.

### B Make person and location context usable on the reference set

Inspect existing base/local, contextual and reconciled captions, confirmed face
boxes, dates, place metadata and user edits. Choose current evidence with explicit
precedence; an older reconciliation cannot override a later confirmed name.

Refresh only missing/stale context. Prefer composition from saved text and confirmed
annotations; a blind substitution of every generic noun is unsafe. Where the saved
caption cannot associate people with actions reliably, a bounded local visual check
may be necessary. Record that exception and its cost; no whole-library vision run.
Use the existing local context path where suitable, with changed input validation,
queue admission and output contract as needed. Cloud inference is not required by
this slice and new external media flows are not implied.

Primary descriptions name confirmed principal people; supported location is
included at the right precision. Unknown people and locations remain explicit.
Store contextual text separately from the raw caption, with evidence revisions.
Use one current description consistently in detail, album review and search views.
A generic raw caption may remain under an explicitly labelled original-caption
section; it must not silently replace completed person enrichment.

Deliverable: reviewable reference photos with name-aware descriptions and visible
location/date provenance, plus evidence that unchanged vision/transcripts were reused.

### C Answer the request and build the Immich album

Resolve the ordinary-language request to the confirmed identity and full available
time range. Do not infer a birthdate from the earliest photo. Retrieve a broad
identity-grounded pool before applying editorial selection; unknown-GPS photos
remain eligible. Keep date-uncertain photos in a separate visible group.

Start with chronological ordering and balanced coverage by available year. Group
presumed copies and similar bursts, retaining links to alternatives. Do not remove
all but one repeated annual event; repetition across years can show growth. Do not
require GPS or impose an aesthetic score that drops the only useful early photo.
Distinguish the full matching set from the smaller curated selection.

Use stable Immich asset IDs to publish a dedicated private album through existing
app/API operations. Save the query, selected IDs, exclusions, policy version and
input revisions. User removals persist across refreshes. Repeating the same request
refreshes the same managed collection rather than creating duplicate albums.

Deliverable: an actual chronological album with source links, a per-year coverage
summary and a review surface explaining selected/excluded/uncertain photos.

### D Demonstrate corrections and a downstream consumer

Rename/correct a reference identity, reject a false inclusion, correct a place and
add a newly eligible photo. Verify that context, search and the managed album
converge while preserving explicit removals. Restore the fixture afterward without
changing unrelated human labels. Exercise an interrupted job/restart and a malformed
response; no duplicate inference or album assets should result.

Evaluate Immich Memories against the existing album. Verify what text/facts it
actually receives before claiming saved-description reuse. If it needs its own
facts, report which ones are new work; do not silently re-caption the archive.
A film is optional unless chosen as an additional acceptance output.

## Proposed acceptance checks

These are concrete starting thresholds for discussion, not already achieved results.

| Check | Proposed pass condition |
|---|---|
| Person-aware account | Every reviewed reference photo with an unambiguous confirmed principal identity uses that name in the primary contextual description; zero identity/action swaps |
| Retrieval coverage | Every eligible confirmed positive in the fixed reference set appears in the review pool; uncertain/excluded cases have explicit reasons |
| Curated album | Zero confirmed wrong-person inclusions in the reviewed selection; at least one suitable moment per available year when evidence exists |
| Location/date | Each asserted place/date is traceable; no guessed venue or exact age; missing GPS does not remove the photo |
| Existing-app delivery | Album opens through Immich with all selected mapped assets and reachable originals; missing mappings are reported rather than silently dropped |
| Reuse | Identical rerun adds no album/asset duplicates and makes no new caption-model calls for unchanged inputs |
| Corrections | For the bounded reference scope, automated context/search/album update within a proposed five minutes while required workers are healthy; pending/stale states remain visible |
| Recovery | One restart/interruption and one malformed-response check preserve checkpoints and edits; unrelated items continue |
| Privacy | Evaluation identities/assets remain private; any assistant/model receives only the explicitly permitted inputs |

Passing these checks demonstrates this journey on the scoped data. Broader rollout
then measures missing identity/context coverage across the child's available years
and resolves exceptions before claiming full-slice completion. A random sample
cannot establish whole-library recognition accuracy.

## Decisions to settle before implementation

1. **Where named descriptions must appear.** Recommended first contract: our photo
   details and album-review surface show the current name-aware account; Immich
   provides the album/original links. Requiring that account in Immich's native
   Description field too needs an explicit promotion/design decision because it
   is currently gated. A custom metadata record alone does not satisfy that UX.
2. **Album selection.** Recommend a complete chronological matching pool plus a
   separately curated highlights selection. Choose the highlights budget after
   seeing available years and volume rather than forcing a fixed age/milestone story.
3. **Acceptance thresholds.** Confirm the reference-set checks and five-minute
   correction target before designing the worker changes or scaling the queue.
4. **App choice and data bridge.** Evaluate Photo Manager and a direct Immich API
   adapter for the album; select Memories only for optional presentation. Verify
   how each consumes current descriptions instead of assuming Parquet/custom fields
   are automatically visible.

Discussion ends with a recorded delivery surface, selection policy and acceptance
checks. Only then begin bounded implementation and a private reference-set review;
no worker restart, bulk context backfill, native-field promotion, app installation
or new external model submission is part of this document-writing task.

The [acceptance design](photo-memory-acceptance-design.md) maps these phases to
independently scored tasks and describes the private evidence for each.
