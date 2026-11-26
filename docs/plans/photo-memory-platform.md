# Photo memory platform north star and definition of done

Status: discussion draft. The north star and mandatory person enrichment are agreed;
acceptance thresholds and delivery choices below are proposed. No implementation
is authorized by this plan. Updated November 25, 2026. Related issue: #217.

## North star

Ask for an album in ordinary language and get relevant memories across people,
relationships, activities, places and years. Review the evidence, correct mistakes,
and use the collection through Immich and compatible applications.

The platform supplies dependable private context to existing apps. Its success is
a useful album or story, not the number of model calls or an empty enrichment queue.

This applies to **every person with a confirmed identity across the library**, not
only family members, people named in these examples, or the subject of the first
slice. Support any confirmed person, their aliases, multiple people together and
explicit relationship groups such as colleagues or school friends. Newly confirmed
identities must work through the same rules without person-specific code or a
hardcoded list of names.

The growing-up album is the first end-to-end acceptance slice. It proves the
shared capabilities on a bounded scope; it does not restrict which people the
platform can enrich, search for or include in later albums.

The owner's concrete scenarios become these reusable acceptance journeys. Personal
names, person IDs, birthdates, colleague lists, site coordinates and selected photos
belong in private evaluation fixtures, not this repository.

| Journey | Required understanding | Result |
|---|---|---|
| My colleagues traveling outside our work site | Explicit colleague membership, relevant time period, site boundaries and supported locations | Reviewable album of the relevant people away from that site |
| My eldest son growing up | Consistent identity across ages, reliable capture dates and useful coverage across years | Chronological album with a representative selection and visible gaps |
| My son and our dog with his school friends | The specific child, actual pet and explicitly known friend relationships; same-photo versus same-event intent | A collection matching the requested combination, excluding unrelated dogs and artwork |

Do not guess employers, kinship, friendship or pet identity from appearance. A
geographic trip alone does not establish work travel. Ask or use confirmed facts
when those relationships change the answer.

## Person enrichment is mandatory

A confirmed identity must be used in the primary contextual description of the
corresponding person. A face card with the right name beside a generic main caption
is insufficient. For an unambiguously associated confirmed subject, the displayed
account should say the saved name instead of only "a man", "a boy" or "a woman".
Unknown people remain unnamed. Apply the same naming rules to every confirmed
identity, including photos containing several known people; never invent identities
or relationships to satisfy the wording requirement.

Use confirmed face associations and canonical identities, retaining aliases for
search. Keep automatic or imported suggestions distinct from human confirmation.
Names must attach to the correct person and action: a person posing through a
painted board must not inherit the painted body's attributes, and a painted dog
must not become the family's pet.

Preserve the original model caption. Store the contextual description separately
with the source caption revision, identity/metadata revisions, generation policy
and provenance. A label or location correction invalidates affected descriptions
and schedules bounded refresh. Until refreshed, show a current factual context
summary or an explicit pending state rather than silently presenting stale context
as final.

## Location enrichment

Use the most specific supported place, with its source and precision. Preserve
explicit user corrections and evidence of conflicting coordinates or place labels.
A nearby-place candidate is not a confirmed visit. Missing GPS is unknown location,
not a reason to drop an otherwise valid person photo from a growing-up album.
Dates need provenance too; uncertain dates cannot establish an exact age or milestone.

## Responsibilities and app reuse

| Component | Responsibility |
|---|---|
| Immich | Original-asset access, gallery, existing recognition/search and album delivery |
| Existing companion apps | Conversational album operations, curation and optional film presentation where verified |
| Our platform | Saved local captions and speech, current confirmed identities/aliases, relationships and places, context enrichment, evidence queries and durable corrections |
| PostgreSQL, Parquet and DuckDB | Existing durable state and analytical/read interfaces; a graph database is not a prerequisite decision |

Prefer an adapter over duplicating an existing app. Verify that a consumer actually
reads our saved descriptions and metadata; neither the existence of an MCP server
nor a custom metadata record proves that integration. Compare release-pinned app
behavior against our deployed Immich version before selecting it.

The current Immich preservation key is `home.knowledge-index.v1`. It is not a native
caption or native face assignment. Native caption/GPS/date promotion is gated and
native face transfer disabled. This plan does not change those policies. See the
[Immich reconciliation boundary](../runbooks/immich-knowledge-index-reconciliation.md).

## Definition of done

Each delivered slice names its scope, app/release, acceptance surface, private test
set and measured limits. Every required gate needs evidence. An exception needs a
reason and explicit disposition; excluded and skipped items are never relabelled
successful. A completed first slice does not mean every north-star journey works.

| Gate | Required evidence |
|---|---|
| Actual user outcome | The requested collection opens as an album in the chosen existing app/Immich workflow; individual originals are reachable |
| Correct identity and caption | The same enrichment rules apply to any confirmed identity and aliases, including multiple known people together; described confirmed people are named correctly, with no identity swaps or reliance on whole-photo tags alone |
| Useful coverage | Coverage by year and source is shown; no available era disappears silently; date and identity uncertainties are visible |
| Context and provenance | Names, locations, activities and relationships have traceable support; missing evidence stays unknown |
| Retrieval and selection | The query produces a relevant reviewable pool and curated selection; proposed quality thresholds are agreed before rollout |
| Corrections | A corrected identity, rejection or place changes descriptions, queries and album membership within the agreed refresh interval |
| Consumer integration | The chosen app demonstrably receives the intended saved facts; native/custom Immich fields and any unsupported display surface are explicit |
| Safe reuse | Unchanged originals, vision results and transcripts are reused; repeated queries/refreshes do not duplicate expensive inference or album membership |
| Durable operation | Restart and interruption checks preserve work and corrections; malformed responses are isolated; policy and lifecycle follow GitOps |
| Privacy | Original media and sensitive relationships remain private; any external model receives only the deliberately selected, authorized data |
| Truthful status | Scoped pending, stale, failed, withheld and accepted exceptions are visible; overall completion requires all required stages, including person context |
| Grafana for every processing stage | The live Knowledge Index dashboard shows the current scope, progress and dispositions, throughput history, freshness, and the measured bottleneck. ETA is available when the queue and recent rate support it. A stage with synchronous work shows observed request volume, latency and errors, with a documented reason for queue-only fields. Metrics contain aggregate counts and timings. |
| Live tuning for every processing stage | Measure a representative baseline, identify the limiting phase or resource, record the settings and decision, and verify the deployed result under comparable load. Include quality and correctness checks, errors, retries and duplicate work. A deliberate keep decision needs evidence and a repeat measurement. |

Use the reviewed growing-up journey and its stable Immich face-ID reconstruction
as the gate for extending the shared Grafana and tuning workflow to all photos.

For the platform as a whole, all three acceptance journeys must pass their agreed
checks. An automatic life-history writer, universal face-recognition accuracy or a
blanket second cloud caption pass is not implicit in this definition.

## Baseline that must not be mistaken for completion

Read-only audit on November 25 found the person-context service stopped, with
11,421 ready jobs, 523 retries and one stale running job. Of 26,907 named photos
within the audited current-size/non-album-copy scope, 14,388 lacked a context job;
237 had a completed context caption whose saved name set matched current labels.
That is a freshness check, not an accuracy score. The existing reader hides context
when names diverge, then falls back to the generic original caption.

Immich sync reported 75,662 applied records, 10,371 missing asset matches and 162
identity conflicts, plus 32,759 deliberate import-scope exclusions. Those cohorts
need separate treatment; they are not all bugs or all accepted exceptions.
Successful native smart search does not establish caption/context search coverage.

Basic local caption coverage and settled audio stories are completed components.
Person-aware publication and end-to-end app acceptance are not complete. See the
[first growing-up album slice](person-growing-up-slice.md) for the proposed next work.

Use the [acceptance design and executable contract](photo-memory-acceptance-design.md)
to sign off individual tasks, a scoped journey, or the platform.
