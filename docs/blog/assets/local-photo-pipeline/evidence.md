# Evidence for the local photo pipeline article and slides

Prepared November 21, 2026 (Pacific); final results appended November 25. Historical screenshots captured November 22 UTC. This is an editorial evidence register, not a new benchmark run. Architecture was checked against repository revision `1989dc7` and the tandem implementation chat. No private photographs, face names, GPS coordinates, credentials or raw session logs are included.

## Measurement scope

| Claim used | Evidence and scope |
|---|---|
| Local RTX 16.0 → RTX+Mac 22.3 saves/min; 223 distinct items after | Tandem implementation report, November 21, 2026, 16:56:13 UTC. Two ten-minute production windows, verified against Parquet. RTX contributed 13.3/min and Mac 9.0/min in the after window. Different inputs; 39% is observed change, not a controlled causal estimate. |
| Mac four vs. twenty requests: 9.62 vs. 9.65/min; p95 48 vs. 124 s | Same implementation report, referring to that day's local benchmark database. This report preserves the summarized measurements; the private evaluation database is not bundled. |
| Continuous refill 21.4 → 28.0/min | Recorded before/after values in the versioned dashboard and implementation report. Before contained 38 videos, after one. This confound is stated beside the comparison. |
| Photos-first 31.4/min, 943 distinct photos, zero videos | Tandem implementation report November 21, 2026, 21:55:40 UTC; 30-minute window, RTX+Mac only, direct Parquet verification reported. A follow-up at 21:57:48 UTC explains the five-minute sampling artifact. |
| Local photo-only page 24 and page 48 both 32/min; photo/video request costs | [Committed dispatch notes](../../../../scripts/knowledge-index/bonsai-dispatch.md), especially commit [3bc7460](https://github.com/homeiac/home/commit/3bc7460). These are distinct from the mixed before/after refill windows. |
| Luna 4/8/20 request slots ≈31/53/66 saves/min | [Luna README](../../../../scripts/knowledge-index/luna-backfill/README.md), commit [29448b8](https://github.com/homeiac/home/commit/29448b8). Production samples had different photo/video mixes. |
| Luna fixed 20 requests: 4 prep/24 jobs 62.6; 6 prep/24 jobs 55.9; 4 prep/48 jobs 69.3/min | Same README, commit [a555dee](https://github.com/homeiac/home/commit/a555dee). Sequential production samples. Local Bonsai guardrail: 112 vs. 128 photos in equal four-minute windows. |
| Face batch read ≈0.96–1.16 s →8–10 ms after ≈0.86 s setup | This chat's bounded live profile and implementation [dbbe470](https://github.com/homeiac/home/commit/dbbe470). The code streams one query in 256-row batches. Timing is only the reader phase; complete face matching remains additional work. |

The tandem chat was supplied by the user (chat ID `01a1f090-1a01-7030-97a1-f59af0133cbb`). Its summaries were read as historical evidence, not treated as current live status. Detailed source logs and private evaluation data remain local. Measurements above were not rerun for this editorial update.

## Grafana pictures

All included pictures are native browser screenshots, not reconstructed charts. The source was the private [Knowledge Index dashboard](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index?orgId=1&from=1795258800000&to=1795312800000&timezone=utc), with the fixed range **2026-11-21 11:00:00–2026-11-22 02:00:00 UTC**, all hosts and all pipeline enrichers. The actual dashboard timestamps and legends are retained.

- `grafana-throughput.jpg`: historical multi-model throughput capture. Retained as source material, but omitted from the finalized article/deck because it combines local and cloud measures.
- `grafana-live-tuning.jpg`: GPU request-slot occupancy, applied policy and photo/video/query-write stage timings. Included in the article and finalized slide 5.
- `grafana-overview.jpg`: supporting overview capture of historical before/after cards and run state.

Snapshot observations included 28.6 local saves/min, 96.9 combined captions/min and 36,446 distinct captioned items. They are endpoint readings, not the same measurement as the earlier trials. The dashboard also showed zero native Immich outstanding jobs but 12,556 pending synchronization assets and 475 conflicts. “Immich native indexing done” does not imply all custom metadata or captions are finished.

Dollar panels use configured electricity/API-equivalent assumptions and estimated usage accounting. They are not actual billed amounts, verified cost savings or independently proven cloud-space reclamation. The 2,280-second sidecar baseline is a configured historical comparison.

The value stream map was inspected in Grafana. Its large multi-pipeline layout was not legible as a single slide screenshot, so the deck uses a separately labeled conceptual architecture SVG and authentic throughput/policy screenshots. No synthetic chart is presented as a Grafana capture.

## Architectural and operational sources

- [Knowledge index schema, ingest hook and operations](../../../runbooks/knowledge-index.md).
- [Host Takeout ingest and ledger](../../../../scripts/backup/host/gphotos-ingest-host.sh).
- [Cloud copy job launcher](../../../../scripts/backup/cloud-backup-run-now.sh): the Drive/OneDrive pull still runs as a Kubernetes Job. Host-side Takeout extraction is a separate path.
- [Mirror target policy](../../../../scripts/backup/cloud-backup-install-mirror.sh): the SSD contains the Photos quota subset, not the entire library; the HDD target excludes Photos. Installation alone does not prove current coverage or matching hashes.
- [Photo PostgreSQL/readside architecture](../../../../scripts/knowledge-index/photo_enrichment/README.md).
- [Immediate rejection overlay](https://github.com/homeiac/home/commit/914a403), [priority review](https://github.com/homeiac/home/commit/51e8cdc), [reuse Immich context](https://github.com/homeiac/home/commit/7b7b751).
- [Luna runner, shared ledger and context snapshot](../../../../scripts/knowledge-index/luna-backfill/README.md).
- [Takeout range repair](../../../../scripts/backup/host/takeout-range-repair.py).
- [Immich GPU OCR](../../../runbooks/immich-ocr-gpu.md) and [observability](../../../runbooks/immich-observability.md).

External behavior was checked against primary documentation: [rclone copy](https://rclone.org/commands/rclone_copy/), [Google Photos API changes](https://developers.googleblog.com/en/google-photos-picker-api-launch-and-library-api-updates/), and [Immich external libraries](https://docs.immich.app/features/libraries/).

## Editorial boundaries

The article claims a path toward reducing Google's storage warning, not a measured amount of quota freed. It distinguishes native indexing, captioning, synchronization and review. The deck's comparison bars encode reported values, while its scheduling animation is conceptual. Optional cloud processing is explicitly labeled. No claim is made that every rollout component has merged to main or that the complete photo library has two verified independent local copies.

## November 22 worker-status investigation

Read-only inspection at approximately 08:36 Pacific found `knowledge-index-enrich.service` with `LoadState=not-found` and `ActiveState=inactive`. The previous boot journal ended at 2026-11-22 04:13:42 UTC; the new boot began at 04:15:59 UTC. The pipeline metrics file last changed at 04:13:49 UTC and still contained the previous running flag, but its heartbeat was stale. The node-exporter scrape-error flag was zero. Luna published a current heartbeat separately.

The launcher uses `systemd-run --collect`; preview overrides are stored under `/run/systemd/system`. Those are temporary runtime units/settings. This explains why the worker did not return after reboot and why both local-backend panels lacked fresh reports. It does not establish why the host rebooted. No worker or host changes were made during this diagnosis. Reproduce the read-only checks with `scripts/knowledge-index/check-caption-health.sh`.

## November 22 GitOps recovery

Flux applied worker bundle `2244713d49e0` from PR #218 commit `bbdfc5f`. The installer
Job completed at 16:49:24 UTC after backing up existing files and retiring the
temporary overrides. The unit's permanent fragment is
`/etc/systemd/system/knowledge-index-enrich.service`; it is enabled for boot.

At 16:50:03 UTC the scheduled reconciliation reported no changed files and no
restart; the worker PID stayed 357095. A controlled service-only restart at
16:50:34 UTC produced PID 359801 and a fresh heartbeat. Exactly one worker process
was present. No host reboot was performed.

The audit baseline captured 1,996 completed Parquet files before deployment.
By 16:51:13 UTC, two new batches contained 30 successful, distinct item identities
and two retryable error rows. Fifteen successes were saved before the restart and
15 afterward. New successful rows had zero duplicates within the new output and
zero matches against previously successful `(source, path, size_bytes, enricher)`
keys. This is a bounded recovery check, not a claim that historical data contains
no duplicates or that all captioning has finished.

Reproduce with `scripts/knowledge-index/caption-gitops/audit-host.sh verify` and
`check-host.sh`; `check-flux.sh` reads installer and scheduled-reconciliation logs.
Local validation passed nine reconciliation/locking/audit tests, 16 metrics tests,
five cache tests and all 27 enricher integration assertions.


## Frontier model versus local GPU

Slide 7 compares elapsed time to the 70,000th currently published Luna photo with
an estimate for the RTX 3070 and Mac GPU running together. The 31.4 photos/min
measurement is **both local GPUs combined**, not the RTX alone: 943 distinct photos
in a 30-minute photos-first window. Do not add the Mac's rate to it again.

The read-only `scripts/knowledge-index/luna-backfill/measure-campaign.sh` query
reported these retained ledger timestamps on November 22:

| Event | Pacific time | UTC |
|---|---|---|
| First retained attempt | Nov 21, 9:08:44 a.m. | 2026-11-21 17:08:44 |
| 70,000th successful published photo, ordered by finish time and ID | Nov 22, 6:54:17 a.m. | 2026-11-22 14:54:17 |
| Last successful photo/video | Nov 22, 7:47:37 a.m. | 2026-11-22 15:47:37 |

The 70,000-photo milestone spans 78,333 seconds: **21h 45m 33s**, displayed as
**21h 46m**. This elapsed time includes the other work and pauses during the run;
it is not photo-only model time. Retained finish timestamps include corrections,
so the query identifies the 70,000th current saved result, not necessarily the
first historical moment when 70,000 items had any version of a caption.

The combined local projection is `70,000 / 31.4 / 60 = 37.155 hours`, or
**37h 09m**, assuming both GPUs remain available at that sustained rate. The
observed Luna interval is about **15h 24m shorter than this projection**.
The percentage reduction is `100 × (1 − 78,333 / 133,757.962) = 41.4368%`,
displayed as **41% less elapsed time** with the local projection as denominator.
Equivalently, the local projection is 70.76% longer than Luna, using Luna as the
denominator; the slide uses only the first percentage to avoid mixing bases. This
is not a completed local run of the same 70,000 photos or a controlled model
speed/quality comparison. Earlier individual-GPU trials used different workloads
and are not added to this combined rate.

The full Luna campaign published **71,643 photos and 6,064 videos** (77,707 total).
Reported/projected API-equivalent cost was $42.33019, plus a $1 pilot allowance:
**$43.33019**. The slide rounds this to about $43 and labels it as the **full
campaign**, not the cost of precisely 70,000 photos. Enterprise Codex supplied
inference; this accounting does not establish an incremental subscription charge.

The earlier electricity illustration used only assumed RTX draw against a rate
that already included the Mac. It has been removed. No combined RTX-host/Mac
energy measurement or hardware allocation is available in this comparison;
therefore the slide makes no numerical local-cost or billed-savings claim.


### What the local result supports

The slide's editorial takeaway is that a consumer RTX 3070, alongside the Mac GPU,
is a competitive practical setup for this library: useful captions, existing
hardware, and no per-request API fee. The quality statement records the author's
practical assessment supplied in the conversation. No scored blind comparison,
quality-equivalence rate or price/performance superiority has been established.
The timing estimate remains the **combined RTX + Mac** result, not RTX-only.

Luna's final configuration submitted 20 requests concurrently. Higher concurrency
and shorter campaign elapsed time support the cloud-capacity point, but do not
isolate a causal contribution from model architecture or cloud infrastructure.
The actual cloud hardware allocated to these requests was not measured, so the
comparison does not pit the home GPUs against an entire provider data center.

## Closing the final caption gaps

The combined audit excluded album copies using the existing name-and-size rule,
then compared current `(path, size_bytes)` identities with both published datasets.
It found 12 gaps: six readable items with failed/interrupted requests and six
source-file problems. The existing local GPU worker prioritized the frozen repair
manifest through Flux; its normal success filter and single-writer lock remained
in force. Two photos and four videos each received exactly one successful local
caption. The temporary repair priority was removed after verification.

Combined coverage is now **85,889 of 85,890 photos** and **6,909 of 6,914 videos**:
92,798 captioned items out of 92,804 under that album-copy rule. This does not claim
hash-level deduplication or that every album copy has a separate caption.

The six permitted exceptions remain uncaptioned and their originals are unchanged:

| Count | Finding |
|---:|---|
| 3 MOVs | Metadata-only containers; no video stream and only eight payload bytes |
| 1 MOV | Roughly 138 MB of trailing zero bytes, including the missing playback index |
| 1 MPG | Roughly 10 MB of zero-filled blocks; no MPEG video start codes found |
| 1 PNG | Malformed data after about 41 KB; tolerant decoding recovers only 79 of 1,161 rows |

The retained-version and configured USB-backup searches found a PNG backup with
exactly the same SHA-256, so it was not substituted. No blank, partial or fabricated
caption was counted as a success. The user accepted leaving these files out.
Private filenames and diagnostic manifests remain on Piglet; the repository stores
only the read-only diagnosis, coverage and verification scripts.

<a id="final-results-november-25"></a>

## Final results — November 25

Read-only live checks at **2026-11-25 18:30:59–18:31:00 UTC** (10:31 a.m.
Pacific) supersede the historical run-state screenshots for current completion.
The local catalogue contains 118,987 media paths and 119,670 sidecar paths.
The caption exporter reported success; its file was about two minutes old.

| Final measure | Result | Scope |
|---|---:|---|
| Local or either-model photo coverage | 85,889 / 85,890 | Presumed-copy groups, not content hashes |
| Either-model video coverage | 6,909 / 6,914 | Same grouping; six total damaged source exceptions described above |
| Local video coverage | 6,885 | Remaining captioned videos can use Luna's saved visual description |
| Luna photo/video coverage | 71,643 / 6,064 | Original campaign; not an independent whole-library second pass |
| Photos with local but no Luna coverage | 14,247 | Optional second opinion, not missing usable local captions |
| Current reconciliations | 77,463 ok; 220 skipped | No pending/reserved/sent current revisions |
| Critical completed-reconciliation conflicts | 0 | Does not validate local-only photos or prove historical accuracy |
| Eligible video stories | 6,909 ok | Zero error/skipped/pending/inflight; zero unpublished updates |
| Current video-story snapshot | 6,909 rows / 6,909 unique identities | No duplicate rows; no repeated successful audio jobs |

Reproduce caption coverage with `scripts/knowledge-index/check-caption-completion.sh`;
Luna/reconciliation status uses the read-only ledger queries in
`luna-backfill/check-status.sh` and `reconciliation.status`. The final audio audit
uses `scripts/knowledge-index/audio-story/audit.py`. Diagnostics and raw source
identities stay private. Metrics report coverage by both grouped items and file
paths; a caption on a mapped copy covers its group.

The one-time `seed()` in `luna-backfill/host.py` selects the then-uncaptioned local
queue and records a seeded generation. Reconciliation discovery follows new
available pairs, not all missing Luna captions. This explains why being caught up
with reconciliation does not imply a full second model pass. The user accepted
local captions as the useful baseline and the six damaged-source exceptions;
there is no scored accuracy evaluation of the 14,247 local-only photo groups.

The platform claim is a **private queryable evidence layer** for life, family and
work journey analysis across years and places: saved descriptions, dates/people/
location context, speech, separate source outputs and human decisions. Immich
remains the gallery. A dedicated automatic journey writer, graph database and MCP
interface are not delivered by this PR. Example journey questions in the slides
are illustrative, not demonstrated answers or claims about all native Immich
capabilities. Sharing policy for a future interface remains a design choice.

## Final video and audio results

[Video tuning results](../../../../scripts/knowledge-index/video-tuning/results.json)
record the fixed six-clip comparison. Request concurrency stayed at two for RTX;
Mac changed from four to one. Selected previews use up to eight frames, 768px,
a concise activity/change prompt and a 256-token output limit. Four-frame variants
lost event detail. RTX runtime caches were reset per cell with synthetic warmup;
the Mac server was warm with prompt caching disabled. Decoding/warmup are excluded
from model trials. Shared homelab load and the small sample limit inference.

| Backend | Before saves/min | After saves/min | Derived increase |
|---|---:|---:|---:|
| RTX | 5.96 | 8.73 | 46.48% (slide: 46%) |
| Mac | 3.08 | 4.79 | 55.52% (slide: 56%) |

[Audio/story results](../../../../scripts/knowledge-index/audio-story/results.json)
record 151.93 seconds over six short clips plus a silence control, Whisper small
Q5_1 multilingual with VAD, beam one, warm services, HTTP transfer included and
extraction excluded. Wall times were Mac **7.90 s**, RTX **26.73 s**, CPU **147.42 s**.
These are not whole-library completion times or human-labelled accuracy scores.
The production choice uses Mac and spare CPU capacity, returning RTX capacity to
Immich. No claim is made that the Mac is universally faster than RTX.

Final audio states: **2,059 speech, 4,128 no speech detected, 93 no audio stream,
629 uncertain speech**, summing to 6,909. Seven speech-classified transcripts were
withheld during story assembly because they were dominated by repetition; raw
transcripts, audio classifications and visual captions were preserved. All stories
settled, but not all contain speech-derived text.

The authorized Codex text route had **509 completed production assessments**:
224 useful, 261 unclear and 24 incidental, plus seven pilot/calibration checks.
No unknown or waiting requests remained. Total token-based API-equivalent
accounting was **$0.501818** including pilots, rounded to ~$0.50. This is separate
from the original caption campaign's ~$43.33 estimate and from reconciliation's
observed **$0.000869 per successful item**. These measures must not be summed as an
actual bill or used to claim measured cash savings. No raw account readings or
observation amounts are recorded here.

The value of avoided work is architectural: speech backfill reuses vision;
settled exact text requests are cached; no-audio/unusable speech settles without
inference; deterministic discovery avoids unnecessary story revisions. We did not
measure a dollar total for avoided calls or combined local electricity/hardware.

## Final recovery lessons

- **Caption ties:** 1,052 video groups were ambiguous under the old winning
  timestamp selection. Raw successful rows plus complete deterministic ordering
  remove that ambiguity. Two discovery scans on a private copy of all 6,909 live
  groups produced zero input changes and zero requeues on repeat, without model
  calls or production queue writes. A real newer caption still refreshes its story
  without retranscription. See commit `c73edd3` and `verify-discovery.py`.
- **Repetitive ASR:** all seven remaining failed inputs were privately reviewed.
  One reproduction showed `finish_reason=length`, a repeated phrase, and an
  unterminated JSON string. Historical model response bodies for the other six
  were unavailable; the exact same output failure is not asserted for each.
  Short repetitive segments passed the old compression-only filter. New guards
  filter repetition in fresh/saved ASR, preserve distinct useful speech, validate
  typed complete JSON, and route usable local failures to the existing budgeted,
  idempotent Luna path. All seven recovered without further inference, each with
  `story_note=repetitive_transcript_withheld`. See commits `06d2689` and `fa0a167`.

The worker fix passed 23 worker tests, five Codex-adapter tests and three scoped
installer tests. It was deployed through the existing Flux Job/ConfigMap host
installer; the service was active with zero restarts in its new lifecycle.
Authenticated Grafana provisioning checks passed. Final aggregate recovery proof
is in `audio-story/results.json`; no private transcript, identity or photograph
is included in these editorial assets.


## Final editorial focus: local descriptions

The finalized ten-slide sequence follows local descriptions: the memory-platform
outcome, preserved originals and local workers, RTX/Mac throughput, idle-slot
recovery, live tuning, video speech, optional cloud assistance, cross-year analysis,
ongoing operation and final local coverage. The same local-first definition is
used in the article. One successful local visual description per item is the normal
target; successful items are skipped. Video speech/story enrichment reuses that
visual result. An explicit future model/prompt upgrade would be separate work.

The published article and deck no longer show the historical mixed-model
throughput screenshot or its ambiguous completion terminology. The headline
throughput measure is local descriptions successfully saved per minute, with RTX
and Mac contributions identified. Native comparison bars use recorded local
trials; the real Grafana policy/occupancy capture remains, clearly dated.

Final coverage labels distinguish **85,889 local photo descriptions**, **6,885 local
video descriptions** and **6,909 saved video stories**; the last count includes 24
videos whose visual caption comes from Luna. Optional cloud comparisons are kept
on their own slide/section. No additional benchmark or pipeline change is implied
by this editorial revision.
