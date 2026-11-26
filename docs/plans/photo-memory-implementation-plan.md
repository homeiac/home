# Photo memory implementation plan

**First milestone:** ask for a growing-up album, open it in Immich and read descriptions that name confirmed people. The same identity rules apply across the library. Start with the reviewed photos, earn a reference pass, then measure the full declared scope. This plan tracks the work after the [acceptance design](photo-memory-acceptance-design.md) in PR #218. Issue #217 tracks the underlying enrichment work.

Track the stories and their status in [epic #228](https://github.com/homeiac/home/issues/228).

## Before changing implementation

1. Pick one story, one observed gap and the smallest result a reviewer can see. **Update this plan and the active issue first, before editing implementation.** Record the evidence, the next PR's scope, the acceptance field or observable result, and what is deferred. Put the plan revision in its own commit before the code, even when both belong to the same PR.
2. If evidence changes the approach mid-PR, pause code changes. Record the new finding, amend the active plan and issue, and then resume. A passing existing path needs only evidence. An unrelated discovery goes into the backlog. Investigate further now only when it would change the current acceptance decision.
3. Give each implementation PR one observable behavior or one missing measurement. Include its story, expected result and redacted after-result. Split again if a PR crosses two independently testable changes. A private evidence run can close a gap without a code PR.
4. At review, update the story and this plan with the result and next small step. Close a product story when its named gates pass for the stated scope. Label measurement-only closure explicitly. A merge, an empty queue or a synthetic pass alone cannot close a product story.

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

## Rough sequence

The stories below are ordered by the first useful album. S2 now has a measured starting point. S2 and S3 can diverge after identity passes. S7 and S8 stay rough until the first album has been reviewed. The numbered changes below are candidate PR boundaries; use the contract result to choose which work is needed.

### S1. Measure the growing-up reference set and record the first gap ([#229](https://github.com/homeiac/home/issues/229))

**Starts after** — Start here.

1. **Freeze the reference baseline.** Reuse the checker template and confirmed annotations. Agree on the reader surfaces, release, selection policy, correction deadline and retry limit. Exercise one synthetic fixture and record how to reproduce it.
2. **Capture identity and inventory.** Read the existing private mappings and ledger for the frozen set. Run the checker, report coverage by year and source, and name the first failed or missing field.

**Done when** — A reproducible live reference report exists for the proposed 30–50 cases. Its baseline and source evidence are private. The report names the next gap or records passing identity and accounting gates. This measurement story can close with a failing product gate.

### S2. Read a photo description that uses the confirmed person’s name and place ([#230](https://github.com/homeiac/home/issues/230))

**Starts after** — S1 evidence.

1. **Resolve a confirmed person.** If the identity capture fails, fix the first failing lookup. Test an alias, two confirmed people together, and someone newly named through the same path.
2. **Show who is in the scene.** Use saved evidence to put confirmed names in the primary description. Capture the rendered text and the reviewed person/action associations, including a painted figure as a negative control.
3. **Show the supported place and date.** Carry place/date source, precision and revisions into the agreed surfaces. Preserve the raw caption and show a pending state after invalidation.

**Done when** — The identity and context gates pass on the reference set. A reader can tell who is in the scene and what supports the place and date. Unknowns remain explicit.

### S3. Request a growing-up album and review the years it covers ([#231](https://github.com/homeiac/home/issues/231))

**Starts after** — S1 and a passing identity gate.

1. **Resolve one growing-up request.** Use one supported ordinary-language request and an alias to retrieve the eligible pool. Keep eligible missing-GPS photos and report uncertain dates and exclusions.
2. **Select chronological highlights.** Apply the agreed selection policy. Show the full pool, ordered selected IDs and coverage for each available year.

**Done when** — The retrieval and selection gates pass for growing-up on the reference set, including early photos and a wrong-person negative.

### S4. Open the selected memories as a private Immich album ([#232](https://github.com/homeiac/home/issues/232))

**Starts after** — S2 and S3.

1. **Publish one private album.** Use one compatible existing consumer or Immich API path. Map the selected assets and retain the managed album ID.
2. **Read the album back as its viewer.** Capture membership, original access and the context revision actually shown on each agreed surface.

**Done when** — The delivery gate passes. The viewer opens the expected private album, can reach every selected original and sees the intended current description on the agreed surface.

### S5. Keep the album correct after an edit or worker interruption ([#233](https://github.com/homeiac/home/issues/233))

**Starts after** — S4.

1. **Propagate one edit path at a time.** Start with a rejected match. Extend to rename, place correction and newly eligible asset using the same fixture. Keep user removals and measure convergence.
2. **Replay and recover.** Replay an unchanged request, interrupt one job and supply one malformed response. Capture stable membership, bounded attempts, preserved edits, inference deltas, deployed revision and egress.

**Done when** — Corrections and operations pass on the reference scope. Repeat requests reuse the album and saved inference. An unrelated item completes after the malformed response.

### S6. Verify the growing-up album across its declared library scope ([#234](https://github.com/homeiac/home/issues/234))

**Starts after** — S1–S5 reference evidence.

1. **Run scoped rollout acceptance.** Freeze the full journey inventory. Reuse the probes, publish year/source coverage and classify missing, withheld and excluded items. If any required item fails, revise this plan for one bounded fix before coding.

**Done when** — All eight tasks pass together in a live growing-up rollout run on one release. The report includes the full scope and dispositions.

### S7. Find memories of colleagues traveling away from their work site ([#235](https://github.com/homeiac/home/issues/235))

**Starts after** — Later journey; refine after the growing-up review.

1. **Prove or disprove the first travel match.** Begin with dated colleague membership, travel evidence, site boundary and an on-site negative. Use the shared album path. Size further PRs after the first reference result.

**Done when** — The offsite-colleagues live rollout passes all required gates on its declared scope, including negative controls for location and travel intent.

### S8. Find a child, their pet and school friends together ([#236](https://github.com/homeiac/home/issues/236))

**Starts after** — Later journey; refine after the growing-up review.

1. **Prove or disprove one group match.** Use explicit friend and pet evidence. Agree whether together means the same photo or the same event. Include artwork and a different pet as negatives. Size further PRs after the first reference result.

**Done when** — The child-pet-friends live rollout passes all required gates on its declared scope, including the agreed co-occurrence rule and negative controls.

## Platform sign-off

Run the platform checker against all three live rollout bundles on the same release. Close the epic when that check passes. Keep captures, identifiers, captions, relationship facts and private baselines outside GitHub. Publish the journey, scope, release, gate result and failed field names as needed. The [executable contract](../../scripts/knowledge-index/memory-acceptance/check.py) defines the result.
