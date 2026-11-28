# Recovering basic descriptions and missing previews

## November 27, 2026 · baseline

Question: which assets processed by the historical Waffles scanner have no basic description in Immich? The unit is one Immich asset UUID. An asset counts as described if either its native description or its saved Knowledge Index summary contains text. The scanner's success measures inference on an image or a video preview.

Run the following queries in their respective databases in read-only transactions. Join their outputs by asset UUID. Save the initial UUIDs privately before writing a caption. Rerunning the missing-description query after a successful write deliberately removes that asset from the result.

**Waffles queue** (`photo_enrichment`)

```sql
SELECT asset_id, status, last_error
FROM waffles.jobs
WHERE run_id = 'historical-waffles'
  AND (status = 'complete' OR
       (status = 'failed' AND last_error = 'thumbnail_http_404'));
```

**Caption coverage** (`immich`)

```sql
SELECT a.id AS asset_id, a.type, a.visibility,
       NULLIF(btrim(e.description), '') IS NULL
       AND NULLIF(btrim(m.value->>'summary'), '') IS NULL AS missing_description
FROM asset AS a
LEFT JOIN asset_exif AS e ON e."assetId" = a.id
LEFT JOIN asset_metadata AS m
       ON m."assetId" = a.id AND m.key = 'home.knowledge-index.v1'
WHERE a."deletedAt" IS NULL AND NOT a."isOffline";
```

Intersect the completed IDs with `missing_description = true`. This yields **2,192** of 75,722 completed assets. All 2,192 lacked the custom packet altogether. The independent thumbnail cohort contains **3,178** failed jobs, including **3,176 hidden videos**. A missing thumbnail or a hidden motion-photo component is insufficient evidence of original corruption.

| Files in the caption cohort | Count |
|---|---:|
| Canon RAW (.CR2) | 2,120 |
| BMP | 36 |
| JPEG | 6 |
| TIFF (.tif or .tiff) | 3 |
| JPEG 2000 (.jp2) | 1 |
| MP4 | 20 |
| WMV | 5 |
| AVI | 1 |

Recovery checks: use the exact asset ID, recheck for existing text before publishing, and verify the written caption. Sample multiple frames for video. Keep the original Waffles run and prior metadata intact. For thumbnail failures, verify native preview availability or a decoded original/playback frame. Permission errors, unavailable mounts, unsupported codecs and timeouts do not establish corruption. Only independently confirmed corrupt originals qualify for archival. Keep a private reversible ledger of affected IDs.

### Direct-media checks

The two standalone timeline assets in the failed-preview cohort both returned preview HTTP 404. The video returned HTTP 206 from playback and FFmpeg decoded a 768 × 432 JPEG. The sync service's native thumbnail-job request returned HTTP 403. Its ability to read a file and generate a derived frame is independent of permission to run Immich's thumbnail jobs.

The PNG original was present (1,311,442 bytes). Its first invalid chunk length occurred at byte 41,082. Pillow and FFmpeg failed to decode it strictly. A tolerant Sharp decode produced visibly repeated strips. We backed up its previous timeline visibility and prior health metadata, archived that single asset via the Immich API, and verified both the archive visibility and the saved reason under `home.media-health.v1` with `excludeFromProcessing = true`. No original bytes changed. A derived partial PNG preview is diagnostic only.

Of the 3,176 hidden videos, 3,137 are referenced by a current parent Live Photo and 39 have no live parent reference. The separate [direct-media recovery run](2026-11-27-quality-and-media-recovery.md) owns those 3,178 failed-preview UUIDs. Do not enqueue them a second time.

### Caption run

The private SQLite ledger stores the frozen IDs, per-asset inference results, submission state, and errors. Only aggregate evidence belongs in Git. Filename matching found 689 candidate pairs for 676 assets. A filename alone does not prove that two images show the same moment. A caption can be reused across this run only when the sampled inputs and duration hash identically.

The operator script uses the existing local photo prompt and the chronological video prompt. External assets go through the normal publisher, which verifies filepath, content and API readback. Pilot uploads use the same owned Immich metadata key with API readback. Native descriptions remain available for user edits.

The first ten-item canary yielded two video sampling failures, four empty or non-JSON model answers, and four timeouts. None was published. A revised Mac request with the existing production thinking-disabled settings produced a 38-word RAW caption, submitted it to the normal reconciliation worker, and matched its text to the exact Immich asset on readback. The RTX had Bonsai loaded with a 4,096-token context. An 8,192-token request timed out; the run now uses the resident context. A seek failure falls back to chronological decoded frame indices and actual frame timestamps. A media failure stays in the ledger for investigation.

#### Live progress


- 2026-11-27T05:56-08:00 · 2 read back from Immich, 10 submitted, 0 independently filled, 2,179 pending, 1 unresolved.

#### Preview recovery evidence

The deployed Waffles media service served the standalone video's cached 1,600 × 900 JPEG twice (HTTP 200). At the residual check, six hidden video files failed direct MP4 decoding. Four had current, readable parent photos. Examining the actual media bytes recovered two valid embedded MP4 streams, one inside a companion file and one inside its linked parent. FFmpeg decoded a video frame from each. Both generated JPEGs were installed in the recovery cache and fetched through the worker service with matching SHA-256 hashes.

The other four hidden derivatives had no decodable motion stream in the checked files. Each received a verified `home.media-health.v1` record with `state = unreadable_motion_component` and `excludeFromProcessing = true`. They retain their existing hidden visibility. This disposition applies to the video component only. The separately confirmed damaged PNG is the **one** original moved to Archive.

Processing queries can exclude either disposition by asset UUID:

```sql
WHERE NOT EXISTS (
  SELECT 1 FROM asset_metadata h
  WHERE h."assetId" = a.id
    AND h.key = 'home.media-health.v1'
    AND h.value @> '{"excludeFromProcessing": true}'::jsonb
)
```

A recovery cache thumbnail is available to the processing workers. Native regeneration for the standalone video was denied to the sync role. No native thumbnail replacement was verified.

#### Why the captions were missing

A live join on catalog path and original byte size explains the entire cohort. The Takeout adapter classified 2,165 inputs as `other`: 2,120 CR2, 36 BMP, five WMV, three TIFF and one JP2. None had a catalog summary row. The 20 MP4s and one AVI were correctly classified as media and had an earlier summary error. The six JPEGs were managed Immich assets outside the external Takeout library. The counts sum to 2,192.

Both model backends produced useful descriptions. Visual spot checks of one RAW image from each backend confirmed the main scene and subjects. Two early video retries attempted to create a temporary directory on a read-only container filesystem. Streaming the selected JPEG frames to stdout removed that dependency. That infrastructure error is distinct from corrupt media.

Immich also returned the owner-visible tag **Media health/Corrupt original** on the archived PNG. Existing tags were backed up locally before the additive assignment. Use this tag to find the file in Immich, or use the metadata predicate above to exclude it from jobs.

At 06:02 Pacific the separate preview recovery run reached a terminal result of 3,171 completed and seven failed. Two of those seven subsequently had validated embedded-motion JPEGs installed and read back. Across the original 3,178 preview failures this accounts for **3,173 usable processing previews and five exclusions**. The live exclusion query returned one archived corrupt original and four hidden unreadable components. Historical inference rows preserve the original run outcomes.

Two videos that failed the initial timestamp-seeking path each produced four chronological frames through the corrected streaming decoder. Both generated a description and were submitted to the normal Immich publisher.

A spot check of 24 same-stem companion pairs found zero exact matches after orientation, sRGB conversion, and resizing to the model input dimensions. These records continue through scene inference. No sibling caption was copied based on its filename.

At 06:06 Pacific, a fresh join of all 2,192 frozen IDs to Immich found 37 saved captions whose text exactly matched the recovery ledger (27 photos and 10 videos). The Mac and RTX had generated 68 captions in total at the checkpoint. Generated and submitted records count toward completion only after Immich readback.

- 2026-11-27T06:10-08:00 · 58 read back from Immich, 34 submitted, 0 independently filled, 2,100 pending, 0 unresolved.

At 06:10 Pacific, 92 captions had been generated. Immich returned the exact saved text for 58 assets (45 photos, 13 videos); 34 more were in the normal publisher. The corrected decoder and the remaining backfill run under a single, finite local job. It resumes from the private ledger, makes at most one corrected retry per eligible failed asset, records terminal counts here after readback, and exits.

- 2026-11-27T06:12-08:00 · 70 read back from Immich, 34 submitted, 0 independently filled, 2,088 pending, 0 unresolved.

#### Basic-caption recovery throughput · 27 November 2026

The [live per-backend graph](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index?orgId=1&viewPanel=287) counts saved answers per minute over 15 minutes. The state graph beside it counts exact Immich assets. From 09:14 to 09:30 Pacific, inference cleared 120 pending items while Immich readback confirmed 84. The number awaiting readback rose from 409 to 445. More inference alone would grow that queue during this interval.

The [matched benchmark results](../../../scripts/knowledge-index/caption-recovery/tuning-results.md) use one previously verified photo from each of six original file-size buckets. The [replay tool and selection query](../../../scripts/knowledge-index/caption-recovery/benchmark.py) keep the previews and answers local. The Mac ran three, six, then three concurrent requests against the same six images. We compared the RTX and still-fawn on the same first three images, with one request in flight on each backend. All requests used the production basic scene prompt and 768-pixel preview preparation. These are photo-only measurements on shared machines, and they exclude Immich publication.

The [CPU trial](../../../scripts/knowledge-index/caption-recovery/still-fawn-cpu-canary.sh) ran inside still-fawn's K3s VM with three CPU threads, one model slot and no GPU. It used the pinned Bonsai 27B Q1_0 weights and Q8_0 vision projector. On the first photo, prompt and image processing took 192 seconds of the 232-second request. The actual caption took 38 seconds to generate. The trial kept its results outside the production ledger.

#### Additive Mac slot trial protocol · 27 November 2026

Keep the current Mac server, RTX and recovery dispatcher running. Start with eight additional Metal slots on a separate loopback server using the same weights, prompt and per-slot context. Replay verified photos outside the production ledger. Sample occupied slots and request turnovers on the original server alongside the recovery ledger, compare each caption against its image, and reduce only the extra capacity if quality or throughput declines. Keep the production queue moving throughout.

The [additive trial runner](../../../scripts/knowledge-index/caption-recovery/additive-mac-trial.py) starts its own loopback server, checks the reported slot count, and releases that process after measuring it. To reproduce, run the [benchmark](../../../scripts/knowledge-index/caption-recovery/benchmark.py) in `prepare` mode with `--count 16` and a private folder. Start the [slot observer](../../../scripts/knowledge-index/caption-recovery/observe-mac-trial.py) in `observe` mode with the same folder and the read-only ledger. Collect 90 seconds before starting the trial runner. Its `--slots` parameter sets both the number of added model slots and the number of clients. The observer's `report` mode summarizes the original server over each trial's exact start and end times.

During 927 one-second samples the original Mac server answered every probe. Its PID and the active recovery dispatcher's PID survived all four trials. Immich readback advanced from 1,322 to 1,406 verified assets. Each trial returned 16 valid captions; visual review found the same dark-frame error in all four. With eight extra slots, the original server slowed to 9.03 requests/min. The extra server added 6.81 captions/min, giving 15.84 combined compared with 16.79 and 15.40 in the two baseline windows. No tested addition demonstrated a reliable overall gain. The baseline workers continue to own the queue. The [full table in Grafana](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index?orgId=1&viewPanel=288) includes all four settings.

#### Canon RAW importer verification plan

Classify mixed-case CR2 extensions on import and check older catalog rows. Use the existing Immich asset and its saved caption when available. Otherwise try the Immich preview before developing the original into a temporary JPEG. Exercise both image paths on the same private sample, repeat the lookup, and check asset and caption counts. Keep identifiers and image bytes out of Git.

#### Canon CR2 results

The catalog contained 2,782 CR2 paths, including 111 in album folders. The frozen gap contained 2,120 Immich asset IDs with that extension. Reading 12 bytes from each of those 2,120 originals found **2,120 JPEG signatures** (`FF D8 FF`). The extension alone gave the wrong decoder for every file in the gap.

On three already-described family photos sampled across file sizes, the regular worker read the Immich preview. With the preview withheld, it decoded the JPEG bytes in each original. Both routes produced a 683 × 1,024 image for each sample. Each caption round-tripped through an isolated Parquet index with zero model calls. The second Immich lookup returned the same asset ID and metadata. The canary performed only reads against the live library.

A separate genuine Canon 40D sRAW fixture from the rawpy project (Git blob `b8594dda24cdcc904fe2dab4c5c6916676870d21`) produced a 1,024 × 683 JPEG through LibRaw on the caption host. The importer keeps that JPEG in memory. [Upstream Canon fixture](https://github.com/letmaik/rawpy/blob/main/test/RAW_CANON_40D_SRAW_V103.CR2) · [Immich preview settings](https://docs.immich.app/administration/system-settings/#image-settings-thumbnails-and-previews)

To repeat the count, query the catalog below. To repeat the byte check, select the original paths from the private frozen ledger, remove the exact external-library prefix, and read their signatures on the index host. A Canon CR2 normally has a TIFF header followed by `CR` at offset 8. The [read-only canary](../../../scripts/knowledge-index/caption-recovery/verify-cr2.py) accepts private relative paths and sizes on stdin.

```sql
SELECT count(*) AS cr2_paths,
       count(*) FILTER (WHERE album IS NOT NULL) AS album_paths
FROM gphotos_media WHERE lower(ext) = 'cr2';
```

The adapter handles new CR2 files. The catalog view also exposes older CR2 partitions as media without re-importing any originals. The worker reuses existing captions and checks original bytes before sharing a machine caption across paths. A regression test dispatched two identical CR2 inputs concurrently, restarted the cache, and counted one model call in total. A private 24-hour reservation initially covered 2,083 exact path/size pairs still owned by the historical recovery, including items awaiting publication.

At 06:25 Pacific, Flux installed the importer and restarted the caption worker. A live catalog query returned **2,782 media paths** for CR2, including the older Parquet partitions. The separate historical recovery had stopped during a Kubernetes pod command. It resumed from the ledger and submitted its 12 previously generated answers without calling a model again. Temporary pod-transport errors now receive bounded retries. The new worker continues to respect the recovery's reservations.

- 2026-11-27T06:28-08:00 · 106 read back from Immich, 70 submitted, 0 independently filled, 2,016 pending, 0 unresolved.

The first production batch exposed 551 external CR2 assets already in Immich's trash. The worker now filters trash, offline assets, and explicit media-health exclusions before inference and refreshes that selection every five minutes during a run. A restored file becomes eligible again. For CR2 album paths it compares candidate originals by SHA-256. Equal filenames and sizes alone cannot suppress work.

All **111** album candidates matched their year-folder originals byte-for-byte. The catalog accounts for 2,782 paths as 2,120 active originals, 551 trashed originals and 111 copies. Four album captions were written during rollout before the new exclusion. Two matched active originals in the recovery cohort and were submitted through the normal publisher for reuse. The other two matched paths outside the recovery cohort. The first 20 successful CR2 Parquet rows had zero repeated source/path/size/enricher keys.

A production batch also exposed a missing telemetry counter for saved-caption reuse. Parquet had already committed the batch when the counter raised an exception. The counter and canary now cover the full persistence step. Reused text is counted separately from model inference.

- 2026-11-27T06:42-08:00 · 206 read back from Immich, 92 submitted, 0 independently filled, 1,894 pending, 0 unresolved.

- 2026-11-27T06:57-08:00 · 286 read back from Immich, 132 submitted, 0 independently filled, 1,774 pending, 0 unresolved.

- 2026-11-27T07:12-08:00 · 366 read back from Immich, 167 submitted, 0 independently filled, 1,655 pending, 4 unresolved.

- 2026-11-27T07:26-08:00 · 450 read back from Immich, 203 submitted, 0 independently filled, 1,535 pending, 4 unresolved.

- 2026-11-27T07:41-08:00 · 534 read back from Immich, 239 submitted, 0 independently filled, 1,415 pending, 4 unresolved.

- 2026-11-27T07:56-08:00 · 630 read back from Immich, 263 submitted, 0 independently filled, 1,295 pending, 4 unresolved.

- 2026-11-27T08:12-08:00 · 714 read back from Immich, 297 submitted, 0 independently filled, 1,176 pending, 5 unresolved.

- 2026-11-27T08:27-08:00 · 794 read back from Immich, 337 submitted, 0 independently filled, 1,056 pending, 5 unresolved.

- 2026-11-27T08:43-08:00 · 891 read back from Immich, 360 submitted, 0 independently filled, 936 pending, 5 unresolved.

- 2026-11-27T08:58-08:00 · 986 read back from Immich, 385 submitted, 0 independently filled, 816 pending, 5 unresolved.

- 2026-11-27T09:14-08:00 · 1,082 read back from Immich, 409 submitted, 0 independently filled, 696 pending, 5 unresolved.

- 2026-11-27T09:30-08:00 · 1,166 read back from Immich, 445 submitted, 0 independently filled, 576 pending, 5 unresolved.

- 2026-11-27T09:50-08:00 · 1,226 read back from Immich, 505 submitted, 0 independently filled, 456 pending, 5 unresolved.

- 2026-11-27T10:07-08:00 · 1,310 read back from Immich, 541 submitted, 0 independently filled, 336 pending, 5 unresolved.

- 2026-11-27T10:28-08:00 · 1,418 read back from Immich, 553 submitted, 0 independently filled, 216 pending, 5 unresolved.

- 2026-11-27T10:49-08:00 · 1,490 read back from Immich, 601 submitted, 0 independently filled, 96 pending, 5 unresolved.

- 2026-11-27T11:02-08:00 · 1,562 read back from Immich, 625 submitted, 0 independently filled, 0 pending, 5 unresolved.

#### End-of-batch readback · 2026-11-27T12:02-08:00

| Status | Assets |
|---|---:|
| error | 5 |
| queued | 613 |
| verified | 1,574 |

0 records qualified for a bounded retry after a change to decoding or inference. The private ledger retains per-asset reasons for any unresolved records.


#### Publisher repair · November 27

The noon ledger showed 613 submitted assets without a matching Immich caption. All 613 still had a saved, unapplied publisher payload. Catalog discovery had marked these recovery-owned jobs as removed. Two competing jobs had saved captions for the correct assets; three reset requests had no saved answer in either the ledger or the source catalog. Preserve recovery ownership across discovery, restore the affected queue states, then compare every original asset with its caption in Immich.

At 5:01 p.m. Pacific, a single read-only Immich database snapshot found a nonempty Knowledge Index caption on **2,192 of 2,192 original asset IDs**. All **613** formerly queued captions matched the saved pre-repair text. Of the five original errors, the two competing jobs exactly matched their earlier publisher payloads. The three connection resets had neither a saved catalog caption nor a recovery cache hit; each received a new local Bonsai caption and passed readback.

Across the entire cohort, 2,188 captions matched their local recovery ledger text and four had other saved captions. Those four comprise the two competing publisher payloads and two previously described assets. Every caption was in the owned Immich metadata key. The native description field was empty on all 2,192 assets.

The 4:57 p.m. catalog sweep processed 121,769 source rows. The recovery publisher subsequently reported 2,149 applied external jobs, zero pending and zero conflicts. The external job count excludes direct publication to uploaded assets. The Grafana row now shows coverage, exact text matches, other preserved captions, and live publisher conflicts. [Recovery coverage](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index?orgId=1&viewPanel=282) · [Source-removed conflicts](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index?orgId=1&viewPanel=291) · [Readback query](../../../scripts/knowledge-index/caption-recovery/audit.py)
