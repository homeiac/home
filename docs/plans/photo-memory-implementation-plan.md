# Photo memory implementation plan

**First milestone:** ask for a growing-up album, open it in Immich and read descriptions that name confirmed people. The same identity rules apply across the library. Start with the reviewed photos, earn a reference pass, then measure the full declared scope. This plan tracks the work after the [acceptance design](photo-memory-acceptance-design.md) in PR #218. Issue #217 tracks the underlying enrichment work.

Track the stories and their status in [epic #228](https://github.com/homeiac/home/issues/228).

## Before changing implementation

1. Pick one story, one observed gap and the smallest result a reviewer can see. **Update this plan and the active issue first, before editing implementation.** Record the evidence, the next PR's scope, the acceptance field or observable result, and what is deferred. Put the plan revision in its own commit before the code, even when both belong to the same PR.
2. If evidence changes the approach mid-PR, pause code changes. Record the new finding, amend the active plan and issue, and then resume. A passing existing path needs only evidence. An unrelated discovery goes into the backlog. Investigate further now only when it would change the current acceptance decision.
3. Give each implementation PR one observable behavior or one missing measurement. Include its story, expected result and redacted after-result. Split again if a PR crosses two independently testable changes. A private evidence run can close a gap without a code PR.
4. At review, update the story and this plan with the result and next small step. Close a product story when its named gates pass for the stated scope. Label measurement-only closure explicitly. A merge, an empty queue or a synthetic pass alone cannot close a product story.
5. Every stage must complete **Grafana and live tuning** before sign-off. Read back the live dashboard for the stage, locate the bottleneck with measured queue, timing, throughput and resource evidence, record the change or evidence for keeping the settings, then verify under comparable load on the deployed revision. Record accuracy, errors, retries and duplicate work alongside speed.

## Current decision

| Revision | Evidence | Next action and exit | Deferred |
|---|---|---|---|
| 1 · November 25 | The checker passes synthetic tests. The November 25 audit found current names in only a subset of completed captions. Live journey acceptance is outstanding. | Start S1. Freeze the reference baseline and collect the first identity and accounting observations. Exit with an inspectable report and one evidence-based next task. | Worker changes, bulk enrichment, new app installs and downstream journey design. |
| 2 · November 25 | Seven synthetic checker tests pass. No live reference bundle is attached to S1. | Freeze a private, year-stratified set from existing human annotations, including group and negative controls. Read back the same assets and run canonical and alias lookups through the current app. Record identity and accounting results and a reproducible private report. | Product fixes, identity edits, new inference and rollout. |
| 3 · November 25 | S1 measured 40 live reference photos. Both canonical identity lookups returned faces and the group control matched. The equivalent alias returned zero. All 40 detail records opened and year/source counts matched. Of 33 target positives, 32 lacked a current contextual caption and one awaits semantic review. | S1 measurement complete. Start S2 with one failing behavior: make a confirmed alias work in the named-face filter. Recheck equivalent lookup results and preserve unrelated people and unconfirmed suggestions. | Caption generation, general text search, album writes and broader rollout. |

The private S1 reference run recorded two failed gates and six blocked gates. Identity failed `alias_query_matches`; the new-confirmation and false-attribution checks still need observations. Accounting failed `asset_dispositions` and `unresolved_required_assets`. Readback and source counts cover all 40 cases. The run measured the existing app API. Browser/album delivery, semantic accuracy and journey completion remain open. See [measurement story #229](https://github.com/homeiac/home/issues/229).

### Active change for S2

Revision 4, November 25. The live named-face endpoint returned matches for a saved label and zero for its confirmed alias. Resolve named filters against the existing private reconciliation alias registry, then match all stored spellings before counting and paginating. Verify equality of totals and ordered face IDs across spellings, with an unrelated name as a control. Preserve the existing behavior for installations without a registry. Caption work follows this lookup.

Revision 5. The isolated PostgreSQL and snapshot tests passed. The GUI rollout stopped before preparing a release because it looked up source paths from an idle caption worker. Limit that lookup to inspection and cutover, the two modes that use those paths. Re-run the GUI-only release and verify the endpoint.

Revision 6. The live named filter now returns the same total and ordered face IDs for all three confirmed spellings at the first, middle and last pages. An unrelated known label retained its count and an unknown label returned zero. Thirty integration tests passed. The next gap is the primary photo description when a current context caption is unavailable.

Revision 7. On 32 of 33 subject-positive reference items the reader lacked a current contextual caption. For the first visible change, show a factual primary sentence naming the people with current user-confirmed faces when enriched prose is missing. Keep the raw local caption available separately and distinguish this interim account from completed scene enrichment. Exercise the photo detail and gallery cards, a renamed face and an unconfirmed control. Location and person/action inference remain separate checks.

Revision 8. All 40 live reference details showed their confirmed names, and the original captions matched the frozen digests. Thirty-nine used the interim account; one used an existing contextual caption. Browser readback confirmed the painted-board control shows the same primary text on the card and in details, a pending notice and the original caption. Thirty-one integration tests passed. Person/action grounding and the place/date source checks remain open.

Revision 9. Existing exact-file Immich records contain place labels for eight reference photos. Show saved location evidence and its precision on photo details, alongside the existing source of the capture date. Prefer current explicit group locations; expose competing group claims for review. Use recorded coordinates or an unknown location when place evidence is absent. No external lookups are needed. Separately, six face boxes in the private reference set carry competing names across the two systems. Inspect their annotation history and hold person/action sign-off on those cases until the owner resolves them.

Revision 10. Live readback matched the 40 frozen dates and their sources. Eight photos had an Immich city, two had only coordinates, and 30 had unknown location. The browser showed the city, precision and date source. Thirty-two integration tests passed. The private same-face audit found 143 of 6,383 subject-positive candidate photos have a competing named assignment. All six reference conflicts had a local label saved in a 100-label action. Those six are awaiting owner adjudication; their existing labels and original captions are preserved. Do not treat a spelling match in generated prose as an independent identity check.

Revision 11. The owner confirmed the Immich assignments for the six reviewed crops. Apply exactly those six corrections through the existing revision-checked face review API. Preserve other faces on the same photos and re-evaluate the original 40 items under a new private baseline. Recheck descriptions and subject membership. The wider disagreement cohort needs independent evidence.

Revision 12. The review API committed all six owner decisions atomically. Live readback verified the corrected face and unchanged other face assignments on each photo. Five photos left the subject's reference pool; one group photo still qualifies through another confirmed face. The fixed 40-photo set now has 28 positives. All 40 current confirmed-name sets matched the independent revised answer key and original captions were preserved. The broader audit still has 137 disputed photos. The new reference run leaves identity blocked on the new-identity and unconfirmed-attribution checks, and accounting open on scene enrichment.

Revision 13. The owner authorized the remaining 137 conflicting face assignments to take their Immich names. Freeze that cohort, validate the current Immich source and local face revisions, apply and read back the edits. Build a private growing-up album from the corrected identity. Keep a full candidate inventory, disclose missing mappings and select dated highlights across the available years. Reuse existing Immich assets and saved metadata. Verify the private album by reading it back and repeat the selection without duplicating membership. Continue to score scene quality separately.

Revision 14. The post-edit audit found zero remaining comparable conflicts. Library inventory exposed some Immich-confirmed originals in formats outside the local face scanner's image list. Include those originals when the exact external library mapping is verified. Report unmatched local records separately. Select at most one dated photo per calendar quarter, prefer agreement between sources and a saved local description, and use a stable tie-breaker. Dates with no capture evidence stay in the inventory for review.

Revision 15. The private album opens with 89 highlights. Its native timeline places 22 in a different quarter than the saved capture date. Keep source metadata intact, verify the exact album membership and original access, and show the selected photos in capture-date order on the private review page. Mark the date differences there. Changing shared asset dates is a separate decision.

Revision 16. Start the broader life-stage run with the existing exact-mapped subject inventory and an explicit birth year. Reuse reviewed album results before issuing vision requests. Keep one resumable local result per asset and subject, and record ambiguous face locations and date provenance. The confirmed age map takes precedence over model guesses. Stage other family members when their intended labels and birth-year evidence are available. Keep private inputs and outcomes outside Git.

Revision 17. Extend album descriptions to cover each confirmed person in a group photo. Give vision an anonymous numbered region for each resolved face and map names back after inference. Use the owner’s descriptions where available. Verify that different actions stay attached to the right people and that an unclear or overlapping target produces no confident action. Validate on a small private group-photo set while the existing life-stage work continues.

Revision 18. Keep the age and action passes independent. The numbered group-photo test and the single-face retry both attached incorrect actions to some subjects. Benchmark a separate action reviewer on this failure set. Require a second matching action attribution or direct review before publishing a named role. Preserve the owner-reviewed captions and report the release check on the private review page.

Revision 19. Require each vision reviewer to return a small set of normalized action claims with an actor region, visible object or recipient region, and a short evidence note. Compare reviewers against the checked failure set before applying a matching claim to new photos. Score wrong actors and invented movement separately from missed actions. Keep low-coverage results in review and continue age processing independently.

Revision 20. Store Immich person IDs alongside reviewed age and action facts using exact asset and uniquely matched face regions. Read names from the person registry when rendering descriptions, including names mentioned as recipients. Retain local names where the ID is unresolved and expose that disposition. Exercise a simulated rename on all affected captions and keep the underlying observations intact.

Revision 21. The deployed Knowledge Index dashboard has no life-stage, named-action or person-ID refresh panels. Make observability and a measured tuning loop required evidence for every stage. Add a common Grafana layout for queue and dispositions, throughput, ETA, freshness and phase latency. Prepare the life-stage metrics adapter for the private aggregate data. Use the reviewed growing-up journey and stable face-ID reconstruction as the rollout gate for all-photo processing. Keep the current live rollout scoped until those checks pass.

Revision 22. Dashboard updates and live tuning proceed for each active scope as soon as telemetry can be verified. Deploy the shared Grafana row separately through its Flux preview source and publish aggregate life-stage metrics from the existing checkpoint. Measure the bottleneck and verify any tuning independently. The journey and stable face-ID checks gate expansion of person-aware processing to all photos.

Revision 23. The deployed panels received real checkpoints, but the first range-rate extrapolation understated throughput before the collector had a full window. Estimate pace from observed checkpoint times, require two advances and suppress resets. Verify Grafana readback against recent worker results. A 12-photo preparation sample and two comparable live windows support retaining four local workers.

Revision 24. The initial life-stage queue reused the Mac pilot and the RTX endpoint is available. Benchmark the existing RTX Bonsai service on the same marked subjects, capture output agreement, pace and GPU headroom, and preserve other local workloads. If the result supports parallel use, claim a disjoint set of pending assets in the same durable ledger and verify no overlap with the Mac.

Revision 25. The native RTX client produced valid JSON after disabling thinking and supplying the existing life-stage fields as a schema. All five benchmark responses validated and four primary stages agreed, with one adjacent stage. The eight-photo queue canary passed. Reuse the caption client and life-stage work function for the RTX worker. Reuse the video tuning row's narrative, comparison bars, live metrics, quality checks and phase timing layout for life stage, with per-backend counts from the existing checkpoint.

Revision 26. Prometheus returned RTX results, but the overview's default 24-hour sampling reduced the new backend history to one point. Give the two live tuning graphs a shorter time override and visible points. Read both backends from their shared stage series independently of the Host variable, which selects the exporter host.

Revision 27. Ollama already allows two parallel RTX requests, while the life-stage dispatch uses one. Measure the one-request baseline, drain the RTX worker at a checkpoint boundary, reuse the same client and validation for two requests, and verify unique saves and quality. Add the one-request and two-request measurements to the existing before/after dashboard row.

Revision 28. Compare two, three and four RTX requests with the same marked photos and saved-output validation. Keep the Mac processing while draining RTX work at a checkpoint for the benchmark. Verify Ollama's actual slot capacity, GPU residency, valid responses and stage agreement, then select the fastest passing setting and publish the results in Grafana.

Revision 29. Cold vision initialization exceeded the original trial timeout even after restoring two slots. Preserve the failed cold-start attempts as separate evidence. Warm one four-capacity runner fully and compare two, three and four active requests against that same loaded instance before selecting production concurrency.

Revision 30. Let both life-stage graphs use the dashboard time picker so completed runs remain visible over the selected history. Keep the existing throughput calculation and RTX markers. Verify the generated and deployed panels omit their fixed time override.

## Rough sequence

The stories below are ordered by the first useful album. S2 now has a measured starting point. S2 and S3 can diverge after identity passes. S7 and S8 stay rough until the first album has been reviewed. The numbered changes below are candidate PR boundaries; use the contract result to choose which work is needed.

### OpenLABEL album pilot ([#231](https://github.com/homeiac/home/issues/231))

Start with the existing reviewed group-action subset of the private growing-up album. Join exact saved face IDs to current source regions, preserve reviewed caption wording, and encode the principal actions and supported participant roles in ASAM OpenLABEL 1.0.0. Use one private PostgreSQL pilot store. Render its readback into a linked album preview. Verify the person and verb clicks against the saved faces, replay without additional revisions, and record coverage, latency and model-call count. Show the preview before extending coverage.

Pilot readback covered 5 of 88 highlights. All 13 reviewed sentences retained their wording. Browser checks exercised 18 name clicks and 13 principal verb clicks against source face regions. The held-person example selected the two faces in their reviewed roles. A repeat run left five PostgreSQL rows at revision one and made zero model calls. On the Mac the measured first build took 80 ms and the repeat took 27 ms, excluding the live source lookup. Most end-to-end time was in verifying current membership, identity and geometry. Keep the scoped batch lookup and the existing CPU path for this pilot. Grafana’s shared photo processing panels report stage `openlabel-pilot`.

**Pilot correction.** Preserve each reviewed sentence once and link each supported action phrase to its own OpenLABEL occurrence and actor. Reuse the saved face binding for a coordinated verb only where the reviewed clause keeps the same subject. A name click should show that person's reviewed sentences. Check the expected secondary tags independently of the generated buttons on the same five photos.

The corrected five-photo preview preserves all 13 sentences with 21 action tags. Browser checks exercised all 18 name clicks and 21 action clicks against source geometry and reviewed text. Regeneration reused existing evidence with zero model calls. The second run kept the same five revision-two scenes.

**Full album.** Refresh the exact owner-only membership. Keep the five reviewed group scenes, audit the remaining marked-subject captions for face-grounded action spans, and preserve scene-only wording where the saved review withheld an ambiguous face. Bind passive phrases to the affected person. Keep the source face and person IDs, exact saved captions and per-photo span decisions in a private manifest. Check the browser's complete set of cards, captions, action phrases, roles and face boxes against that manifest and the current source readback. Replay the same inputs to check revisions and duplicates before publishing.

All 88 highlights are in the refreshed review. Of the 83 added photos, 79 had saved face-linked captions with 180 reviewed action phrases. Four had an ambiguous face location and retain their saved scene descriptions. The complete album has 201 action links and 97 name links. Chrome exercised each link against the current face geometry. Replaying the export used zero model calls and retained 88 assets across 93 stored revisions.

The full-album run reads `album-reviewed-spans.json` from the private album directory. Each marked-subject entry records the exact source caption, face namespace, face ID, person ID and an ordered list of spans. Each span gives the start, exclusive end, exact words and action sense. The four scene-only entries keep their scene text and saved withholding reason. The publisher rejects changed bindings, changed text, overlapping spans and incomplete coverage. Git contains the vocabulary, renderer and checker. The face data and per-photo decisions stay with the private album.

**Participant and date correction.** Where a reviewed interaction identifies a second face, store its own source face ID, person ID, box and role. Test separate clicks for the action, actor and recipient, including after a rename. Carry saved capture-date conflicts onto the cards and distinguish the recorded date from the visual life stage. Keep the capture year unresolved until evidence supports it.

Browser verification covered 98 face clicks, 201 action clicks and all three disputed dates. For the corrected hug, clicking the verb highlighted both participants. Each face link highlighted just its own source box. The four scene-only cards still have no inferred participants.

**Album-wide participant audit.** Inspect each caption and its image with numbered source face boxes. Link verified people, including unnamed participants and individually verifiable members of a group. Preserve the original wording and distinguish an action participant from a person elsewhere in the scene. Record the reason for each ungrounded mention. Recheck the visual age evidence against the birth year, keeping collages and owner-confirmed dates separate. Replay the export and exercise the face links on the private review page.

**Collages in journeys.** Exclude reviewed collage parents from the dated selection. Keep each original and catalogue its component photographs in reading order, with a polygon in the oriented parent image, the native face occurrences inside that polygon and actions grounded in that panel. Verify child boundaries and reject cross-panel actor assignments. A single embedded photograph remains a distinct media type.

The 88-source audit yields 83 journey photos and five collage originals. The five catalogue entries contain 46 component photos, 64 native face occurrences, and 45 panel-specific observations. One panel shows food and has no verified human action. Regular white gutters reproduced the 15-, 15- and two-photo layouts. The two irregular layouts used visually checked polygons. All three capture-date conflicts remain visible. The single embedded-photo file keeps its own classification.

**Run on another collection.** The publisher's `--participant-jobs PATH` emits private JSONL jobs with the original image, saved captions and source regions. Run `scan_caption_participants.py JOBS OUTPUT` against local Bonsai. Each asset has its own replayable output. The scanner checks singular and plural phrases twice under different face numbers, matches by the native detection ID, and withholds physical-contact partners unless an independent role observation corroborates the ID. Keep model proposals separate from visually checked decisions. An owner-scoped publisher reads accepted records from `caption-participants/<asset>.json`. Display names are resolved on refresh. A per-photo face ID survives a later person assignment. Changed text or geometry invalidates the reviewed binding.

Known collage parents are excluded even when their panel layout is pending. The catalogue uses normalized input polygons, OpenLABEL pixel polygons, child-scoped actions and links to the actual Immich face rows. The journey selector accepts the media-type inventory. The private HTML exporter also excludes collage cards on replay. The optional `openlabel_sources.py --sync-journey` reconciles only reviewed collage memberships through the Immich album API and reads the exact remaining set back.

**Journey caption parity.** Render verified participant and action links on the chronological cards as well as the catalogue cards. Show a short native face ID with an unnamed participant and the full ID on selection. Check the journey itself for caption text, correct highlight geometry and date evidence before following the link to the catalogue.

**Per-person action coverage.** Inventory each visible Immich detection on every multi-person journey photo. Reuse saved subject claims, then visually review the remaining detections. Persist each additional observation against its native face ID and reviewed box. Keep uncertain actions explicit. Verify coverage per photo and test clickable actions on the timeline before publishing.

The private `journey-face-actions.json` review is keyed by asset ID and native face ID. Each entry includes the source box and a reviewed action or a withholding reason. A two-person action contains a `{person}` placeholder, the target face ID and its reviewed box. The shared Grafana stage `journey-group-actions` counts group photos with an action for every detection as complete. A photo with even one withheld detection counts once as withheld.

**Reproduce privately.** Use `memory-acceptance/openlabel_sources.py` with the existing private album directory to refresh the source snapshot. Run `review_openlabel.py` with that directory, the snapshot and the pinned OpenLABEL 1.0.0 JSON Schema. Supply the private database connection through the normal libpq environment and pass `--timeline` on first publication to enable face links on the chronological page. The preview is a snapshot of the resolved names. Refresh both steps after a relabel. The browser checker takes the timeline and source snapshot and requires Puppeteer and Chrome. [Pilot entry point](../../scripts/knowledge-index/memory-acceptance/review_openlabel.py) · [ASAM schema](https://openlabel.asam.net/V1-0-0/schema/openlabel_json_schema.json)

### S1. Measure the growing-up reference set and record the first gap ([#229](https://github.com/homeiac/home/issues/229))

**Starts after** — Start here.

1. **Freeze the reference baseline.** Reuse the checker template and confirmed annotations. Agree on the reader surfaces, release, selection policy, correction deadline and retry limit. Exercise one synthetic fixture and record how to reproduce it.
2. **Capture identity and inventory.** Read the existing private mappings and ledger for the frozen set. Run the checker, report coverage by year and source, and name the first failed or missing field.

- **Required task** — Capture the live Grafana panels, identify the bottleneck, tune or justify keeping the settings, and verify the outcome.

**Done when** — A reproducible live reference report exists for the proposed 30–50 cases. Its baseline and source evidence are private. The report names the next gap or records passing identity and accounting gates. This measurement story can close with a failing product gate.

### S2. Read a photo description that uses the confirmed person’s name and place ([#230](https://github.com/homeiac/home/issues/230))

**Starts after** — S1 evidence.

1. **Resolve a confirmed person.** If the identity capture fails, fix the first failing lookup. Test an alias, two confirmed people together, and someone newly named through the same path.
2. **Show who is in the scene.** Use saved evidence to put confirmed names in the primary description. Capture the rendered text and the reviewed person/action associations, including a painted figure as a negative control.
3. **Show the supported place and date.** Carry place/date source, precision and revisions into the agreed surfaces. Preserve the raw caption and show a pending state after invalidation.

- **Required task** — Capture the live Grafana panels, identify the bottleneck, tune or justify keeping the settings, and verify the outcome.

**Done when** — The identity and context gates pass on the reference set. A reader can tell who is in the scene and what supports the place and date. Unknowns remain explicit.

### S3. Request a growing-up album and review the years it covers ([#231](https://github.com/homeiac/home/issues/231))

**Starts after** — S1 and a passing identity gate.

1. **Resolve one growing-up request.** Use one supported ordinary-language request and an alias to retrieve the eligible pool. Keep eligible missing-GPS photos and report uncertain dates and exclusions.
2. **Select chronological highlights.** Apply the agreed selection policy. Show the full pool, ordered selected IDs and coverage for each available year.

- **Required task** — Capture the live Grafana panels, identify the bottleneck, tune or justify keeping the settings, and verify the outcome.

**Done when** — The retrieval and selection gates pass for growing-up on the reference set, including early photos and a wrong-person negative.

### S4. Open the selected memories as a private Immich album ([#232](https://github.com/homeiac/home/issues/232))

**Starts after** — S2 and S3.

1. **Publish one private album.** Use one compatible existing consumer or Immich API path. Map the selected assets and retain the managed album ID.
2. **Read the album back as its viewer.** Capture membership, original access and the context revision actually shown on each agreed surface.

- **Required task** — Capture the live Grafana panels, identify the bottleneck, tune or justify keeping the settings, and verify the outcome.

**Done when** — The delivery gate passes. The viewer opens the expected private album, can reach every selected original and sees the intended current description on the agreed surface.

### S5. Keep the album correct after an edit or worker interruption ([#233](https://github.com/homeiac/home/issues/233))

**Starts after** — S4.

1. **Propagate one edit path at a time.** Start with a rejected match. Extend to rename, place correction and newly eligible asset using the same fixture. Keep user removals and measure convergence.
2. **Replay and recover.** Replay an unchanged request, interrupt one job and supply one malformed response. Capture stable membership, bounded attempts, preserved edits, inference deltas, deployed revision and egress.

- **Required task** — Capture the live Grafana panels, identify the bottleneck, tune or justify keeping the settings, and verify the outcome.

**Done when** — Corrections and operations pass on the reference scope. Repeat requests reuse the album and saved inference. An unrelated item completes after the malformed response.

### S6. Verify the growing-up album across its declared library scope ([#234](https://github.com/homeiac/home/issues/234))

**Starts after** — S1–S5 reference evidence.

1. **Run scoped rollout acceptance.** Freeze the full journey inventory. Reuse the probes, publish year/source coverage and classify missing, withheld and excluded items. If any required item fails, revise this plan for one bounded fix before coding.

- **Required task** — Capture the live Grafana panels, identify the bottleneck, tune or justify keeping the settings, and verify the outcome.

**Done when** — All eight tasks pass together in a live growing-up rollout run on one release. The report includes the full scope and dispositions.

### S7. Find memories of colleagues traveling away from their work site ([#235](https://github.com/homeiac/home/issues/235))

**Starts after** — Later journey; refine after the growing-up review.

1. **Prove or disprove the first travel match.** Begin with dated colleague membership, travel evidence, site boundary and an on-site negative. Use the shared album path. Size further PRs after the first reference result.

- **Required task** — Capture the live Grafana panels, identify the bottleneck, tune or justify keeping the settings, and verify the outcome.

**Done when** — The offsite-colleagues live rollout passes all required gates on its declared scope, including negative controls for location and travel intent.

### S8. Find a child, their pet and school friends together ([#236](https://github.com/homeiac/home/issues/236))

**Starts after** — Later journey; refine after the growing-up review.

1. **Prove or disprove one group match.** Use explicit friend and pet evidence. Agree whether together means the same photo or the same event. Include artwork and a different pet as negatives. Size further PRs after the first reference result.

- **Required task** — Capture the live Grafana panels, identify the bottleneck, tune or justify keeping the settings, and verify the outcome.

**Done when** — The child-pet-friends live rollout passes all required gates on its declared scope, including the agreed co-occurrence rule and negative controls.

## Platform sign-off

Run the platform checker against all three live rollout bundles on the same release. Close the epic when that check passes. Keep captures, identifiers, captions, relationship facts and private baselines outside GitHub. Publish the journey, scope, release, gate result and failed field names as needed. The [executable contract](../../scripts/knowledge-index/memory-acceptance/check.py) defines the result.
