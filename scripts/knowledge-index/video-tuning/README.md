# Tune videos for useful stories

A useful caption preserves the main subject, setting, action and supported changes
across time. It keeps distinctive evidence for recalling a moment. Invented
relationships, dialogue and actions between sampled frames fail the quality gate.

`trial.py` runs on Piglet with the existing knowledge-index venv. It uses a fixed
sample of already-captioned short, medium and long clips, and stores source paths,
frames, model answers and timings only in a private directory. Production Parquet
is never written by trials. `trials.sqlite3` skips completed cells on restart;
an interrupted cell is repeated in full so measured wall time covers its full count.

Compare eight/four frames, 1024/768 resolution and the original/story prompt. Run
one backend at a time with production inference paused through GitOps. The first
pass screens candidates; a reversed second pass checks the winner against baseline
on the same sample. Then vary request concurrency. Warm models are shared with the
existing production endpoints; other GPU consumers remain active, so this is a
homelab workload comparison, not an isolated hardware benchmark.

Record valid JSON, model latency, input/output tokens, successful videos/minute,
source-video minutes covered/minute and quality decisions. Inspect contact sheets
and both captions for retained events, supported sequence and invented details.
Text agreement alone is not a quality verdict. Do not count cached answers as new
inference speed. A duration-weighted score alone can favor easy long static clips.

Promote a candidate only after all sampled captions pass structural checks and
story review. Prefer a material speed increase (target 20%); retain more visual
evidence when candidates are close. Stop when another round gives under 5% or
would trade away meaningful events. Validate the selected configuration on a live
window, measure errors and model slots, and audit new production rows for duplicate
successes. Report the sample size, workload changes and any failed candidates.

Only aggregate trial results and chosen settings enter Git/Grafana. Private
captions, names, media, paths and account usage readings do not.

## Run a comparison

Use the existing Proxmox host from the inventory:

```sh
python3 scripts/knowledge-index/video-tuning/manage.py --host root@<host> install
python3 scripts/knowledge-index/video-tuning/manage.py --host root@<host> audit-snapshot
python3 scripts/knowledge-index/video-tuning/manage.py --host root@<host> run --profiles baseline8,sequence4 --backends rtx --block 4 --parallel 2
python3 scripts/knowledge-index/video-tuning/manage.py --host root@<host> report
python3 scripts/knowledge-index/video-tuning/manage.py --host root@<host> audit-verify
```

Pause and resume production only through `caption-gitops/config.json` and Flux.
Use a new block for another concurrency; do not pool different slot counts. Trial
media and captions are private. Export only aggregate `report` output to
`results.json` after review, then regenerate the dashboard. The trial runner uses
fixed local model endpoints and the existing host-local runtime key.

## Story-quality decision

The screening intentionally compares a faster four-frame option with eight frames.
A shorter prompt is not automatically better: frame-by-frame prose can omit the
actual activity. The selected prompt should describe the main event and supported
temporal changes, preserve distinctive visible details and avoid inferring names,
relationships or dialogue. The saved metadata remains available to reconciliation.
Manual review uses private frame contact sheets and paired captions. It is not a
blind full-video accuracy study; minor unsupported details must not be presented
as verified facts. The existing risk-based reconciliation remains the next layer.

The host currently has no faster-whisper installation. These measurements cover
visual summaries; they do not establish speech or full audiovisual comprehension.
The existing optional transcription path is preserved and its prompt contribution
is bounded when a transcript is supplied.

## Selected configuration — November 24, 2026

Keep up to eight frames (the existing short-clip cap remains), resize the decoded
1024px JPEG previews to 768px with the same path used in trials, and use the
`video-story-v1` event-focused prompt. Bound output to 256 tokens. Existing photos
keep their prompt/settings. Retain the completed-work enricher identity, so the
new prompt applies to future work and does not requeue completed captions.

The final cache-controlled RTX comparison measured 5.96 → 8.73 clips/minute at
two requests (+46.5%). Each cell reset the model runtime, then warmed weights and
kernels with synthetic blank frames outside the timed interval. Warm replay alone
had misleadingly suggested a much larger gain; the evidence export retains those
runs separately. Model input was 4,445 → 2,728 reported tokens on the matched sample.

Mac results were 3.08 clips/minute for the old 1024px/four-request setup, and 4.79
for 768px/one request (+55.5%). At the selected input settings, one/two/four requests
measured 4.79/4.82/4.85 clips/minute. The observed p95 values (only six requests per
cell) were 14.33/26.38/69.43 seconds. Select one offered request: additional concurrency
gained under 2% while lengthening waits. The server still has four allocated contexts;
the production dispatcher caps videos at one request while retaining four-photo capacity. Mac memory pressure remained normal.

Four-frame candidates were faster but omitted useful event detail. Literal
frame-by-frame prompts were less useful for recall. The retained story prompt
keeps the main activity and supported sequence. Review accepted useful main-event
recall with residual inferred details; it does not establish factual perfection.

`results.json` contains aggregate cells only. Raw media, contact sheets, answers
and trial identities remain in the private host SQLite evaluation directory.
