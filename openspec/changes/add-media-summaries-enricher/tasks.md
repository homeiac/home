## Notes
Runner executes on the Proxmox host (reads the photos dataset directly); only the model server runs in the GPU VM. This resolves 1.2 unless the pilot shows a problem.

## 1. Measure and decide
- [ ] 1.1 Free VRAM on the 3070 beside Frigate (idle and busy); pick model size
- [ ] 1.2 How the GPU VM reads the photos dataset read-only; how it reaches the index dataset
- [ ] 1.3 Count photos, videos and total GB (`knowledge-index-ctl.sh query` on `gphotos_media`, after the Phase 1 backfill)

## 2. Model server
- [ ] 2.1 Install the model server on the GPU VM by script/GitOps (verify image tags exist, no `latest`)
- [ ] 2.2 Pull Qwen2.5-VL 3B (and 7B Q4 if it fits); smoke test one image and one frame set

## 3. Enricher
- [x] 3.1 Stub OpenAI-compatible test server and an ffmpeg-made fixture photo and video
- [x] 3.2 `scripts/knowledge-index/enrichers/media_summary.py`: queue fetch, photo path, video path (frames + Whisper), JSON parse, error rows
- [x] 3.3 Batch Parquet writer (tmp + rename), schema equal to `SUMMARIES_SCHEMA`
- [x] 3.4 VRAM guard (nvidia-smi, where available) and bounded batches; host has no nvidia-smi: guard source still to decide (1.1)
- [x] 3.5 `test-enricher.sh`: schema, idempotent re-run, failed file stays queued, summarized file leaves queue, dry run writes nothing

## 4. Operations
- [x] 4.1 `knowledge-index-ctl.sh enrich sample N | start | stop | status`
- [ ] 4.2 Pilot: ~20 videos + ~50 photos, human quality review, tune frames and prompt, record seconds per item
- [ ] 4.3 Check Frigate detection latency is unaffected during a run (USE method)
- [ ] 4.4 Full run as a background systemd unit

## 5. Docs
- [x] 5.1 Runbook section (operations, new prompt version re-run, search examples); regenerate README
- [ ] 5.2 Secret grep, commit with #212 reference, PR; `openspec archive` after merge
