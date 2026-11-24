# Video stories with speech

Whisper transcribes full audio from videos that already have a successful local
or Luna visual caption. A text-only Bonsai request extracts useful spoken context;
the saved story retains the visual account and explicitly attributes speech.
No images go to that request. Existing vision captions and original media stay
unchanged. This worker does not spend cloud/API credits.

## What runs where

- **Mac Metal:** Whisper.cpp v1.9.6, multilingual small Q5_1, Silero VAD,
  one request, two CPU helper threads. Launchd starts it at login after reboot.
  Its model owns an AC-only sleep assertion; display and battery sleep remain enabled.
  A loopback SSH reverse tunnel reaches Piglet. The Git policy controls enablement/model.
- **still-fawn:** the same model in a digest-pinned CPU image, one request, two
  threads and a two-CPU limit. No GPU allocation. It contributes spare capacity.
- **RTX:** tested using a normally reserved Kubernetes GPU share. The idle Immich
  ML deployment was temporarily paused for that trial and restored afterwards.
  CUDA Whisper is now standby at zero replicas; Immich semantic search keeps its
  share. Do not bypass device accounting or silently suspend interactive search.
- **Piglet host:** a separate systemd coordinator and SQLite ledger. Flux installs
  code/config through the existing restricted SSH ConfigMap/Job credentials. A
  five-minute CronJob repairs drift. Audio updates do not restart the vision worker.

Matched measurements are in `results.json`. Six private clips were capped at
30 seconds plus a ten-second silence control. At beam 1, 151.93 seconds of source
audio took 7.90 seconds on Mac, 26.73 on the loaded RTX, and 147.42 on still-fawn
(19.23x/5.68x/1.03x real time). Extraction is excluded; HTTP overhead and some first
request warmup remain. These are small-sample operational measurements, not a
full-library ETA. Beam 3 was compared only on a matched subset; it did not justify
its added CPU/RTX cost, so production retains beam 1.

## Data and recovery

Private state: `/local-3TB-backup/photo-enrichment/audio-story/`.
`ledger.sqlite3` contains one job per canonical path, byte size and transcription
version. Grouping follows coverage's existing presumed album-copy rule (filename
and byte size, not a content hash). Audio caching additionally hashes extracted
PCM plus model version, sharing successful transcription across identical audio.
Timestamped 120-second chunks survive restarts. Full transcripts remain available;
long story inputs sample up to 40 segments across the entire clip.

A singleton file lock prevents duplicate coordinators. Transactional claims fence
backends; each has one in-flight request. A bad item receives at most three attempts
with backoff, then is skipped while the queue continues. Unhealthy endpoints do not
consume new claims. No-audio, no-speech and uncertain-speech outcomes are distinct.
Low-confidence language, low-confidence segments and repetitive ASR artifacts are
withheld automatically. The original visual account remains usable. There is no
speaker identification and no human review queue for incidental audio differences.

Discovery runs every five minutes, including Luna-only captions. Local captions
are preferred when available. A later visual caption updates only the story; it
does not rerun Whisper. A story-prompt revision likewise preserves transcripts.
Changes to Whisper model/settings that require fresh transcription must bump the
transcription `version`; original results remain in the private ledger/backups.

Current Parquet snapshot:
`/local-3TB-backup/photo-enrichment/audio-story/parquet/current.parquet`.
Publication is atomic and batches settled changes at most every 30 seconds,
including separate `visual_summary`, `visual_source`, timed `transcript`, language,
audio state, backend, `story`, and story/transcription versions. Publication retries
without repeating inference. Schema migrations back up SQLite first. The initial
rollout's per-row exports are archived outside the current dataset, avoiding
thousands of small files in normal DuckDB queries.

```sql
SELECT path, visual_source, audio_state, story, transcript
FROM read_parquet('/local-3TB-backup/photo-enrichment/audio-story/parquet/current.parquet')
WHERE story_state = 'ok';
```

## Operate and verify

Run from this worktree after checking `proxmox/inventory.txt`:

```sh
python3 scripts/knowledge-index/audio-story/test_worker.py
python3 scripts/knowledge-index/audio-story/test_install.py
python3 scripts/knowledge-index/audio-story/generate.py
python3 scripts/knowledge-index/gen-dashboard.py > gitops/clusters/homelab/apps/photo-enrichment/knowledge-index-dashboard.yaml
CB_HOST=root@192.168.4.175 python3 scripts/knowledge-index/caption-gitops/bootstrap.py --installer-only
# Review/commit/push, then let Flux deploy the bundle.
python3 scripts/knowledge-index/check-reconciliation-dashboard.py --reconcile
python3 scripts/knowledge-index/audio-story/status.py --host root@192.168.4.175
```

`status.py --discover` is an offline initialization tool and obtains the same
singleton lock; do not use it to reset a running coordinator. Normal discovery is
automatic. `tune.py` resumes only completed trial cells; `story-trial.py` compares
prompts using saved text only. `export.py` exports aggregate evidence to Git.
Raw speech, media IDs, trial captions and review examples stay on the private host.

The Grafana row **Video stories · speech and context** shows speech/no-audio/
uncertain/skipped outcomes, eligible and pending counts, story completion, worker
throughput and queue ETA. The ETA covers videos with an existing visual caption;
accepted missing/corrupt inputs remain separately visible. Percent complete counts
terminal audio checks including skips, whose count is shown beside it.

## Immich search

Immich's native Description filter searches its description field. The existing
sync publishes generated summaries in owned custom metadata, preserving native
fields on the read-only external library. That custom metadata is not searched by
Description or embedded into CLIP automatically. Audio/story output is separately
queryable Parquet; this change does not claim native Immich summary indexing.
`check-immich-search.py` tests native description and context search using the
existing sync pod's credential without copying it. Context search requires the
Immich ML service even after all image embeddings have been generated.

Non-English spoken context currently waits for a capable text translation route.
Whisper continues saving the original timed transcript. The dashboard explicitly
shows how many are waiting and whether the route is enabled/healthy. Context is
not sent to an external service merely because transcription has completed.

## Prepared Codex translation route (disabled)

`codex_translate.py` is a text-only broker for the existing ChatGPT-authenticated
Codex CLI on the Mac. It is prepared and tested offline, but is not installed or
started while `codex_translation.enabled` is false. It sends only selected timed
speech plus a short saved visual description to OpenAI; original media stays local.
This external text destination requires explicit authorization. Existing runners
in this environment are host services, not an observed Codex Kubernetes pod.

The adapter uses Luna with tools/plugins/web search disabled. It must return a
short spoken-context interpretation or explicitly mark the text unclear/incidental.
One story worker admits requests. Exact input/revision fingerprints and a durable
broker ledger prevent resubmission after ambiguous timeouts. Authentication and
rate-limit failures disable the route. Unknown requests retain their reservation
and are skipped individually; other audio work continues.

The separate translation estimate cap is $10, with $0.025 reserved per unresolved
request and known token usage settled using the existing Luna API-equivalent rate.
This is not actual account cost or a raw account usage reading. The original
caption/reconciliation campaign limits are unchanged. The disabled configuration
cannot submit requests. Offline tests mock both network and model invocation:
`python3 scripts/knowledge-index/audio-story/test_codex_translate.py`.
