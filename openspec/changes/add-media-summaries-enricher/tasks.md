## Notes
Revised 2026-11-16 after review: enricher is a Dockerfile + Kubernetes Job (GitOps), Frigate is stopped during a run (handoff + watchdog), new photos trigger runs automatically.
`media_summary.py`, its ctl commands and tests are done and are reused inside the image; the host-run `enrich start` stays as a manual/debug path.

## 1. Measure and decide (cluster access: `scripts/k3s/get-kubeconfig.sh`, falls back to the host address in proxmox/inventory.txt)
- [x] 1.1 (partly) Measured: both on the one 3070, time-sliced x4; 4.7 GiB VRAM free with Frigate up (see design.md). Still to measure: peak VRAM of Qwen2.5-VL 3B / 7B Q4 under load, and free VRAM with Frigate down
- [ ] 1.2 How the pod reads the photos dataset (read-only) and writes the index dataset (NFS export vs virtiofs); confirm VM 105 is not involved
- [ ] 1.3 Count photos, videos and total GB (`knowledge-index-ctl.sh query` on `gphotos_media`, after the Phase 1 backfill)
- [ ] 1.4 Frigate recovery time after scale-up; what else depends on Frigate (Home Assistant automations, health CronJobs are suspended)

## 2. Enricher code (done, reused in the image)
- [x] 2.1 Stub OpenAI-compatible test server and ffmpeg fixtures
- [x] 2.2 `enrichers/media_summary.py`: queue, photo path, video path (frames + Whisper), JSON parse, error rows
- [x] 2.3 Batch Parquet writer (tmp + rename), schema equal to `SUMMARIES_SCHEMA`
- [x] 2.4 `test-enricher.sh`: schema, idempotent re-run, failed file stays queued, summarized file leaves queue, dry run writes nothing
- [x] 2.5 Runbook section; `knowledge-index-ctl.sh enrich sample|start|status|stop` (manual path)

## 3. Container image
- [x] 3.0 qwen2.5vl:3b pulled (GitOps Job `ollama/job-pull-qwen25vl-3b.yaml`, model already present); measured beside Frigate: too slow (3 min/photo, 8 frames timeout): the handoff in section 4 is REQUIRED
- [x] 3.0b (done 2026-11-16: gemma4:e2b think:false, Frigate paused = ~3-11 s/item; qwen2.5vl:3b rejected) Re-measure with Frigate paused for a few minutes (warm model, 1 photo, 4 frames at 640 px, then 7B Q4): sec/item decides the backfill duration; fix the existing `ollama-model-update-gemma4` Job (it points at nonexistent svc `ollama-gpu`, correct name `ollama-lb`)
- [ ] 3.1 Dockerfile (pinned base, python deps, ffmpeg, duckdb, faster-whisper); verify tags exist, no `latest`, bash present if scripts need it (CLAUDE.md image hygiene)
- [ ] 3.2 Build/publish route (registry used by this repo, e.g. ghcr; check `ollama/secrets/ghcr-creds.sops.yaml` pattern); image tag pinned in the manifest
- [ ] 3.3 Replace the VRAM guard with the handoff (guard stays only as a sanity check that the GPU is free after Frigate is down)

- [x] 3.4a `--api ollama` native mode (honors think:false), ctl uses it; pilot 20 items: 10.1 s/item
- [ ] 3.4 Default model gemma4:e2b + `--extra-json '{"think": false}'` in the Job; keep model loaded (keep_alive) during a run; unload at the end
- [~] 3.5 (20-item sample done, quality good; user review of ~50 more + video accuracy pending) Pilot on REAL photos/videos (task 5.1) before any bulk run

## 4. GPU handoff and automation (GitOps)
- [ ] 4.1 `handoff` entrypoint: annotate + scale Frigate to 0, wait for GPU free, run, restore in `finally`; max duration
- [ ] 4.2 Manifests under `gitops/clusters/homelab/apps/media-summaries/`: namespace, ServiceAccount + Role (patch/scale `deployment/frigate` only), suspended CronJob template, model server, PVC/NFS mounts, watchdog CronJob
- [ ] 4.3 Test the handoff against a fake Deployment in a scratch namespace (restore on success, on crash, on timeout; Flux does not revert mid-run)
- [ ] 4.4 Ingest trigger: after a successful `index-unit.sh`, if the queue is non-empty create the Job (guard against a running one); test with a fake kubectl

## 4b. Observability (Prometheus textfile + Grafana as code)
- [x] 4b.1 `export-metrics.py` (index, quota, ingest, enrichment, SMART per disk) -> node-exporter textfile, systemd timer every 5 min, installed by `ctl install`
- [x] 4b.2 Dashboard generated from `gen-dashboard.py` into `infrastructure/monitoring/dashboards/knowledge-index.yaml` (ConfigMap, grafana_dashboard=1)
- [x] 4b.3 `knowledge-index-alerting-rules.yaml` (exporter stale, units pending, enrichment stalled/high errors, SMART pending sectors/failed, host rebooted)
- [x] 4b.4 `test-metrics.sh`: format, numbers, dashboard==generated, every dashboard/alert metric exists
- [x] 4b.6 Backfill progress metrics (`progress.py`, adapter `--prom`; phase, files done/total, rate, ETA, process stats) + 'Value delivered' row (throughput/min, quota-query speedup, index vs library size, illustrative cloud cost with editable prices); `check-promql.sh` validates all expressions against live Prometheus (79 valid)
- [x] 4b.7 GPU and Ollama section (DCGM metrics by pod, loaded model and its GPU share via exporter reading /api/ps, tenant replica states, energy and illustrative electricity cost) + alerts (Xid errors, hot GPU, Ollama down, model mostly on CPU); 107 expressions valid against live Prometheus
- [x] 4b.8 Real-library acceptance: path-for-path diff of `SELECT path FROM gphotos_quota` vs gphotos-quota-list.py is EMPTY (18,264 paths each)
- [ ] 4b.5 After merge: confirm Flux applied the ConfigMap and rule, the dashboard renders data in Grafana, and the alert rules load in Prometheus

## 5. Rollout
- [ ] 5.1 Pilot: ~20 videos + ~50 photos, human quality review, tune frames and prompt, record seconds per item
- [ ] 5.2 Backfill window policy (e.g. nights), then full run
- [ ] 5.3 Runbook update (handoff, watchdog, how to force-restore Frigate), regenerate README, secret grep, commit with #212 reference, PR; `openspec archive` after merge
