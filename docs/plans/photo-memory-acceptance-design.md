# When a photo-memory task is done

Design for issue #217 · November 25, 2026 · Proposed for review

A person asks for an album in their own words, opens it in Immich, and understands why each memory belongs. For the first journey, that means seeing the selected child grow up across the available years. When a confirmed name can be tied to the person in a scene, the main description uses that name. The same behavior must work for someone first named tomorrow, two people together, and people outside the family.

This design turns the [platform definition of done](photo-memory-platform.md) and [first journey plan](person-growing-up-slice.md) into independently checkable tasks. The [acceptance checker](../../scripts/knowledge-index/memory-acceptance/check.py) runs offline against saved evidence. Product changes, live probes and the choice of companion app remain future work.

## How a request becomes an album

1. **Resolve the request.** Turn the request into a subject, relevant relationships, time range, place rules and inclusion rules. Resolve names and aliases to stable identities. Record the interpretation. Ask for clarification when two interpretations would produce different albums.
2. **Build the matching pool.** Join the current catalogue, confirmed face associations, dated relationships, place evidence and existing Immich asset mappings. Use saved descriptions and speech for activities. DuckDB can read the saved Parquet for this step. Keep human confirmations and corrections in the durable store. Preserve source, precision and revision with each fact.
3. **Describe the people in the scene.** Combine saved visual text with current confirmed facts. Store the contextual text and its input revisions separately from the raw caption. If an action cannot be assigned to a particular person, describe the people present and the action separately. Show pending enrichment while stale text is replaced.
4. **Select and publish.** Build highlights from the full pool under a versioned selection policy. Keep one managed private Immich album per saved request. Map selected items to source assets, preserve user removals, and give unmapped items a visible disposition. On correction, refresh only affected descriptions, memberships and selections.
5. **Read it back.** Open the album as the intended reader. Capture the primary text they see, album membership, source links and the facts the chosen consumer actually received. A worker receipt alone cannot answer those questions.

The proposed first surface is our photo detail and album review for named prose, and Immich for the album and originals. Record that choice before scoring. If native Immich Description is required, the probe must read that field in the native surface. The existing preservation key and a nearby face badge cannot stand in for displayed prose. A film remains an optional downstream output. The [Immich sync boundary](../runbooks/immich-knowledge-index-reconciliation.md) documents the current write permissions.

## Tasks and independent sign-off

Each row is one implementation task with a stable checker ID. A ticket can cite its row, journey, scope, baseline digest, run and evidence location. Independent rows can close while later rows are still open.

| Task | Depends on | Evidence that earns a pass |
|---|---|---|
| `identity` | None | The canonical name and aliases retrieve the expected people. A group photo retains each confirmed person. Confirming a previously unnamed person makes them queryable through the same logic. A whole-photo tag or unconfirmed suggestion alone never assigns a face. |
| `context` | Identity | Capture the primary displayed text on each agreed surface for the fixed cases. Every expected name appears. Compare the reviewed person/action associations to an independent answer key. Verify supported places, date/precision sources, input revisions, unchanged raw captions and the painted-figure regression. |
| `retrieval` | Identity | Run the ordinary-language request. Read back the resolved facts, exact eligible pool and explicit uncertain/excluded cases. Apply the journey-specific checks below. |
| `selection` | Retrieval | Under the frozen policy, the ordered highlight IDs equal the expected sequence, cover the eligible years or events, and include zero known wrong subjects. Keep the complete pool available for review. |
| `delivery` | Selection, context | Open the private album, enumerate its members, open the originals and capture the contextual facts read by the selected consumer. Member and reachable-original IDs must both equal the highlight set, including multiplicity. |
| `corrections` | Delivery | On a reversible private fixture, rename a person, reject a match, correct a place and add a newly eligible item. Observe pending/stale state and the updated primary text, search results and album. Persist the removal. Measure elapsed time from edit to the last converged surface. |
| `operations` | Delivery | Replay the request, interrupt/resume a job, and inject a malformed fixture response. Observe the same album ID, zero duplicates or repeated inference on unchanged inputs, retained edits, bounded attempts for the bad item, and completion of an unrelated item. Record deployed Git revision and compare observed outbound traffic to the authorized scope. |
| `accounting` | None | Compare the entire frozen inventory to the actual per-asset dispositions. Show coverage by year and source, reasons and disposition references for exceptions, and zero unresolved required items or unexplained gaps. |

**Story-specific retrieval evidence**

| Request | Positive and negative controls |
|---|---|
| Growing up | At least one suitable moment per available year in highlights. Positives with missing GPS stay eligible. Uncertain dates remain visible without invented ages. Include early and recent photos and a similar-looking, incorrect subject. |
| Colleagues traveling off site | Check colleague membership at the time, evidence of travel, and location relative to the applicable work site. Include an on-site negative and an away-from-site photo without enough evidence of work travel. |
| Child, pet and school friends | Use the confirmed child, actual pet, and explicitly established friends. Freeze whether all must be in the same photo or may appear across a supported event. Include a different dog, artwork, and an unconfirmed friend as negative controls. |

## What the checker decides

- **PASS** means the task's observations satisfy its assertions and all prerequisites passed for the same run. Close only that task for the named scope.
- **FAIL** means at least one captured observation contradicts the contract. The report lists the failed field names, including failures observed in a task whose prerequisite also failed.
- **BLOCKED** means evidence, an approved expected value, or a prerequisite is missing or unusable. A different baseline, wrong run or altered source attachment also blocks sign-off. A later task can keep its evidence while waiting for a prerequisite.

A reference run answers “does this work on these reviewed examples?” Start with roughly 30–50 carefully chosen photos. A rollout run answers “does it work for this journey's declared library scope?” Freeze the whole scope inventory, item dispositions, independent known positives, exclusions, year/source coverage and selection policy. Explicitly account for stale, pending, failed and withheld items in the captures. Eligible pending work keeps the gate open. Report excluded, withheld and accepted exceptions separately from complete items. Recognition accuracy outside the annotated evidence remains unmeasured.

Platform sign-off requires **all three live rollout journeys on the same release**. A synthetic run exercises the checker. A reference pass earns reference-scope credit only. The five-minute healthy-worker correction target, retry budget, highlights policy, consumer release and exact display surfaces require agreement before using a live baseline. The checker reads those decisions from the approved private baseline or its referenced policy.

## Evidence protocol

**Before the run**, prepare a private baseline using confirmed annotations, source inventory and a reviewed expected selection. Record the application and adapter versions under the release or policy revision. Record each intended surface, scope revision and approval reference. Freeze the baseline before collecting observations. Use opaque stable IDs for matching. A private review record can map them to people, evidence and real assets.

**During the run**, an operator or future read-only adapter captures each task separately. Save the raw capture under the private run directory, together with a normalized JSON observation. Use UI text for primary captions, authenticated app/API reads for membership and originals, edit/restart traces for lifecycle, and bounded counter deltas or logs for inference and egress. A zero count requires a working observation point for the entire experiment. An unavailable observation is missing evidence. The existing [context](../../scripts/knowledge-index/check-photo-context.py) and [Immich sync](../../scripts/knowledge-index/check-immich-reconciliation.py) checks can contribute evidence about inputs and queues.

**For semantic checks**, a reviewer records which named subject performs each action in the actual displayed caption, citing a digest of that caption and surface. Compare those observations with the independently reviewed expected associations. Token matching alone would pass a sentence that swaps two people's actions. Review the fixed regression sample once per changed caption or policy. This is acceptance work on a bounded sample, not a new owner-review queue for the whole library.

**At sign-off**, retain the approval, baseline, raw captures, normalized observations and checker report together. The checker verifies the captured source files' hashes, compares normalized observations and enforces dependencies. It relies on the collector and reviewer for faithful observations and the approved inventory for completeness. A digest detects changes to a referenced file. It does not authenticate a fabricated or self-approved evidence bundle. Keep all live material in private storage outside Git.

### Run the contract

From the worktree root, these commands print the field scaffold, check a prepared private run, and run the synthetic checker tests. The template prints to stdout. Save and fill it in private storage before a live run.

```sh
python3 scripts/knowledge-index/memory-acceptance/check.py template growing-up
python3 scripts/knowledge-index/memory-acceptance/check.py check \
  /private/path/growing-up/baseline.json /private/path/growing-up run-001
python3 -B -m unittest discover -s scripts/knowledge-index/memory-acceptance -v
```

The other journey keys are `offsite-colleagues` and `child-pet-friends`. To check platform completion, place each live rollout under its journey key in one private directory, with its own `baseline.json` and captures. Use the same acceptance campaign ID and release across journeys.

```sh
python3 scripts/knowledge-index/memory-acceptance/check.py platform /private/path run-001
```

The checker uses Python's standard library, reads local files and writes its report to stdout. Exit codes are **0** for pass, **1** for failed assertions and **2** for blocked. Inspect `mode`, `scope` and `tasks` on a journey report before marking anything done.

### Build a task capture

The template lists required **expected** fields. Each task capture is named after its checker ID, for example `identity.json`. Its **observed** fields also include fixed safety checks that the baseline cannot weaken. The [field definitions](../../scripts/knowledge-index/memory-acceptance/check.py) list both. The following is a synthetic example of the complete shape of one task. Replace placeholder digests with the SHA-256 of the exact file bytes.

```json
{
  "run_id": "run-001",
  "baseline_sha256": "<digest of approved baseline.json>",
  "artifacts": {"raw/identity-query-results.json": "<digest of raw capture>"},
  "observed": {
    "canonical_query_matches": ["person-A"],
    "alias_query_matches": ["person-A"],
    "multiple_confirmed_people": ["asset-7|person-A", "asset-7|person-B"],
    "newly_confirmed_query_matches": ["person-C"],
    "unconfirmed_claimed_as_named": []
  }
}
```

Use unique strings for unordered row sets, stable asset IDs for the eligible pool and highlights, and arrays in display order for ordered selections. Use collision-free composite keys when a row represents several facts, for example a serialized JSON tuple. For a caption assertion, the baseline maps each surface/asset key to the required names and the capture maps the same key to the actual displayed sentence. For the ledger, map every scoped asset ID to a state of `complete`, `excluded`, `withheld` or `accepted_exception`. The latter three require a reason and a private disposition reference in the expected and observed ledger. Observed pending/retry/stale states are valid evidence of unfinished work and fail that comparison. Field names missing from a capture are reported without printing private captions.

## Where work starts

Freeze the private reference set, expected outcomes, selection policy, acceptance surfaces and thresholds first. Then run identity and accounting independently. Use the first observed mismatch to select the next implementation task. The November 25 audit in the north-star document found gaps in current name-aware captions. It supplies a starting point for investigation. No live journey has earned a pass under this contract yet.
