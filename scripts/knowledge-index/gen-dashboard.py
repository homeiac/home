#!/usr/bin/env python3
"""Generate the Grafana dashboard ConfigMap for the knowledge index (dashboards as code, issue #212).

Usage: gen-dashboard.py > gitops/clusters/homelab/apps/photo-enrichment/knowledge-index-dashboard.yaml
Output is deterministic; test-metrics.sh fails if the committed YAML differs from what this prints. Edit THIS file, then regenerate.
Metrics come from export-metrics.py (node-exporter textfile on the Proxmox host); host/disk panels also use node_boot_time_seconds and nvme_* .
"""
import json
from immich_dashboard import add_graph

DS = {"type": "prometheus", "uid": "prometheus"}
INST = '{instance=~"$instance"}'
_id = [0]


def _panel(kind, title, exprs, x, y, w, h, unit="none", thresholds=None, mappings=None, decimals=None, extra=None, description=None):
    _id[0] += 1
    steps = [{"color": c, "value": v} for c, v in (thresholds or [("green", None)])]
    defaults = {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}, "color": {"mode": "thresholds" if thresholds else "palette-classic"}}
    if mappings:
        defaults["mappings"] = [{"type": "value", "options": mappings}]
    if decimals is not None:
        defaults["decimals"] = decimals
    p = {"id": _id[0], "type": kind, "title": title, "datasource": DS, "gridPos": {"h": h, "w": w, "x": x, "y": y},
         "targets": [{"expr": e, "legendFormat": legend, "refId": chr(65 + i)} for i, (e, legend) in enumerate(exprs)],
         "fieldConfig": {"defaults": defaults, "overrides": []}}
    p.update(extra or {})
    if description:
        p["description"] = description
    return p


def stat(title, expr, x, y, w=4, h=4, legend="", extra_opts=None, description=None, **kw):
    opts = {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "none"}
    opts.update(extra_opts or {})
    return _panel("stat", title, [(expr, legend)], x, y, w, h, extra={"options": opts}, description=description, **kw)


def series(title, exprs, x, y, w=12, h=8, **kw):
    return _panel("timeseries", title, exprs, x, y, w, h, extra={"options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}}}, **kw)


def bars(title, expr, legend, x, y, w=12, h=8, **kw):
    return _panel("bargauge", title, [(expr, legend)], x, y, w, h, extra={"options": {"orientation": "horizontal", "displayMode": "gradient", "reduceOptions": {"calcs": ["lastNotNull"]}}}, **kw)


def row(title, y):
    _id[0] += 1
    return {"id": _id[0], "type": "row", "title": title, "collapsed": False, "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []}


OK = {"0": {"text": "DOWN", "color": "red"}, "1": {"text": "OK", "color": "green"}}
YN = {"0": {"text": "no", "color": "text"}, "1": {"text": "yes", "color": "blue"}}
RED_IF_POS = [("green", None), ("red", 1)]


TEXTBOXES = [("kwh_price", "Electricity $/kWh (assumption)", "0.35"),
             ("price_photo", "Cloud $/photo (assumption)", "0.002"), ("price_video_min", "Cloud $/video minute (assumption)", "0.02"),
             ("baseline_s", "Baseline: sidecar scan seconds", "2280")]


def _textbox(name, label, default):
    return {"type": "textbox", "name": name, "label": label, "query": default, "current": {"text": default, "value": default},
            "options": [{"selected": True, "text": default, "value": default}], "hide": 0, "skipUrlSync": False}


def shift(items, dy):
    for it in items:
        it["gridPos"]["y"] += dy
    return items


def backfill_panels():
    """Top section: live progress of the (re)index run. Needs the adapter's --prom file; the process_* panels work for any run."""
    p = [row("Backfill progress", 0)]
    p += [stat("Phase", "knowledge_index_backfill_phase{instance=~\"$instance\"} == 1", 0, 1, w=4, legend="{{phase}}", extra_opts={"textMode": "name"}),
          stat("Progress", "knowledge_index_backfill_progress_ratio" + INST, 4, 1, w=4, unit="percentunit", decimals=1, thresholds=[("orange", None), ("green", 0.999)]),
          stat("Files read", "knowledge_index_backfill_files_done" + INST, 8, 1, w=4),
          stat("Files total", "knowledge_index_backfill_files_total" + INST, 12, 1, w=4),
          stat("Speed (files/s)", "knowledge_index_backfill_rate_files_per_second" + INST, 16, 1, w=4, decimals=1),
          stat("Time left", "knowledge_index_backfill_eta_seconds" + INST, 20, 1, w=4, unit="s")]
    p += [stat("Running", "knowledge_index_backfill_active" + INST, 0, 5, w=4, mappings=YN),
          stat("Elapsed", "knowledge_index_backfill_process_elapsed_seconds" + INST, 4, 5, w=4, unit="s"),
          stat("Read from disk", "knowledge_index_backfill_process_read_bytes" + INST, 8, 5, w=4, unit="bytes", decimals=1),
          stat("CPU used", "knowledge_index_backfill_process_cpu_seconds" + INST, 12, 5, w=4, unit="s"),
          stat("Sidecars parsed", "knowledge_index_backfill_sidecars_done" + INST, 16, 5, w=4),
          stat("Parse errors", "knowledge_index_backfill_parse_errors" + INST, 20, 5, w=4, thresholds=[("green", None), ("orange", 1)])]
    p += [series("Files listed / read over time", [("knowledge_index_backfill_files_listed" + INST, "listed"), ("knowledge_index_backfill_files_done" + INST, "read"),
                                                   ("knowledge_index_backfill_expected_files" + INST, "expected (ledger)")], 0, 9, 12, 7),
          series("Disk read throughput", [("rate(knowledge_index_backfill_process_read_bytes" + INST + "[5m])", "read B/s")], 12, 9, 6, 7, unit="Bps"),
          series("CPU", [("rate(knowledge_index_backfill_process_cpu_seconds" + INST + "[5m])", "cores")], 18, 9, 6, 7, decimals=2)]
    return p


def value_panels():
    """Top section: what the index and the local GPU deliver, in numbers that matter (speed, size, cost avoided)."""
    FILES = "deriv(knowledge_index_backfill_files_done" + INST + "[5m]) * 60"
    SUMM = 'sum(deriv(media_summaries_rows{status="ok",instance=~"$instance"}[10m])) * 60'
    QS = 'knowledge_index_query_seconds{query="quota",instance=~"$instance"}'
    COST = ('sum(media_summaries_ok_items{kind="photo",instance=~"$instance"}) * $price_photo'
            ' + sum(media_summaries_video_seconds' + INST + ') / 60 * $price_video_min')
    p = [row("Value delivered", 0)]
    p += [stat("Files indexed per minute", "clamp_min(" + FILES + ", 0)", 0, 1, w=4, decimals=0, description="Backfill speed: files read per minute (5 min window). Only while a run publishes progress."),
          stat("Summaries per minute", "clamp_min(" + SUMM + ", 0)", 4, 1, w=4, decimals=1, description="Photos and videos described by the local model per minute (10 min window)."),
          stat("Quota question answered in", QS, 8, 1, w=4, unit="s", decimals=2, description="How long 'what counts against Google quota?' takes against the index right now."),
          stat("Faster than before", "$baseline_s / " + QS, 12, 1, w=4, unit="suffix:x", decimals=0, description="Baseline: reading ~120k Takeout sidecars from the USB disk took about 38 min (2026-11-16). Edit the baseline_s variable to change it."),
          stat("Index size", "knowledge_index_dataset_bytes" + INST, 16, 1, w=4, unit="bytes", decimals=1, description="Parquet files plus the DuckDB view file."),
          stat("Index vs library", "knowledge_index_dataset_bytes" + INST + ' / sum(knowledge_index_bytes{source="gphotos",instance=~"$instance"})', 20, 1, w=4, unit="percentunit", decimals=3, description="Index size as a share of the photo library it describes.")]
    p += [stat("Library size", 'sum(knowledge_index_bytes{source="gphotos",instance=~"$instance"})', 0, 5, w=4, unit="bytes", decimals=1),
          stat("Photos described", 'sum(media_summaries_ok_items{kind="photo",instance=~"$instance"})', 4, 5, w=4),
          stat("Video minutes described", "sum(media_summaries_video_seconds" + INST + ") / 60", 8, 5, w=4, decimals=0),
          stat("Cloud-equivalent cost avoided", COST, 12, 5, w=8, unit="currencyUSD", decimals=2,
               description="ILLUSTRATIVE. No cloud service describes a Google Photos library like this. Priced as if a multimodal AI API charged per photo and per video minute; set the two price variables at the top to your own assumptions. Not a quote."),
          stat("Counts against Google quota", 'sum(gphotos_quota_bytes{kind="media",instance=~"$instance"})', 20, 5, w=4, unit="bytes", decimals=1)]
    p += [series("Throughput per minute", [("clamp_min(" + FILES + ", 0)", "files indexed / min"), ("clamp_min(" + SUMM + ", 0)", "summaries / min")], 0, 9, 12, 7),
          series("Index size vs library size", [("knowledge_index_dataset_bytes" + INST, "index"), ('sum(knowledge_index_bytes{source="gphotos",instance=~"$instance"})', "library")], 12, 9, 12, 7, unit="bytes")]
    return p


def gpu_panels():
    """GPU (DCGM exporter) and Ollama (exporter's /api/ps reader). GPU series are not filtered by $instance: the DCGM exporter has its own instance label."""
    pods = 'DCGM_FI_DEV_GPU_UTIL'
    KWH = "sum(increase(DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION[$__range])) / 3.6e9"   # sum: the pod label changes as different pods use the GPU
    PAUSED = {"0": {"text": "STOPPED", "color": "red"}, "1": {"text": "running", "color": "green"}}
    p = [row("GPU and Ollama (RTX 3070, shared)", 0)]
    p += [stat("GPU utilization", "avg(DCGM_FI_DEV_GPU_UTIL)", 0, 1, w=4, unit="percent", decimals=0, thresholds=[("green", None), ("orange", 85)]),
          stat("GPU memory used", "sum(DCGM_FI_DEV_FB_USED)", 4, 1, w=4, unit="mbytes", decimals=0),
          stat("GPU memory free", "sum(DCGM_FI_DEV_FB_FREE)", 8, 1, w=4, unit="mbytes", decimals=0, thresholds=[("red", None), ("orange", 2000), ("green", 4000)]),
          stat("Power", "sum(DCGM_FI_DEV_POWER_USAGE)", 12, 1, w=4, unit="watt", decimals=0),
          stat("Temperature", "max(DCGM_FI_DEV_GPU_TEMP)", 16, 1, w=4, unit="celsius", decimals=0, thresholds=[("green", None), ("orange", 75), ("red", 85)]),
          stat("GPU errors (Xid)", "sum(DCGM_FI_DEV_XID_ERRORS)", 20, 1, w=4, thresholds=RED_IF_POS, description="Non-zero means the NVIDIA driver logged a GPU fault.")]
    p += [stat("Ollama API", "ollama_up" + INST, 0, 5, w=4, mappings=OK, thresholds=[("red", None), ("green", 1)]),
          stat("Model loaded", "ollama_model_loaded" + INST + " == 1", 4, 5, w=4, legend="{{model}}", extra_opts={"textMode": "name"}),
          stat("Model on GPU", "ollama_model_gpu_fraction" + INST, 8, 5, w=4, unit="percentunit", decimals=0, thresholds=[("red", None), ("orange", 0.5), ("green", 0.9)],
               description="Share of the loaded model in GPU memory. Low means part runs on the CPU and is much slower (qwen2.5vl:3b was 0% on this card)."),
          stat("Model size", "ollama_model_size_bytes" + INST, 12, 5, w=4, unit="bytes", decimals=1),
          stat("Unloads in", "ollama_model_expires_timestamp_seconds" + INST + " - time()", 16, 5, w=4, unit="s"),
          stat("Models stored", "ollama_models_pulled" + INST, 20, 5, w=4)]
    p += [stat("Frigate", 'kube_deployment_spec_replicas{namespace="frigate",deployment="frigate"}', 0, 9, w=4, mappings=PAUSED, thresholds=[("red", None), ("green", 1)],
               description="0 = paused on purpose for GPU work (scripts/k3s/gpu-tenants.sh); cameras are not recording."),
          stat("Stable Diffusion", 'kube_deployment_spec_replicas{namespace="stable-diffusion",deployment="stable-diffusion-webui"}', 4, 9, w=4, mappings=PAUSED, thresholds=[("red", None), ("green", 1)]),
          stat("Ollama pod", 'kube_deployment_status_replicas_available{namespace="ollama",deployment="ollama-gpu"}', 8, 9, w=4, mappings=PAUSED, thresholds=[("red", None), ("green", 1)]),
          stat("GPU energy (selected range)", KWH, 12, 9, w=4, unit="suffix: kWh", decimals=2, description="Whole-GPU energy over the dashboard time range."),
          stat("Electricity cost (range)", "(" + KWH + ") * $kwh_price", 16, 9, w=4, unit="currencyUSD", decimals=2, description="Illustrative: kWh x the kwh_price variable. Compare with the cloud-equivalent cost in the Value row."),
          stat("GPU hours busy (range)", "sum_over_time((max(DCGM_FI_DEV_GPU_UTIL) > bool 50)[$__range:1m]) / 60", 20, 9, w=4, unit="suffix: h", decimals=1)]
    p += [series("GPU utilization by pod", [("DCGM_FI_DEV_GPU_UTIL", "{{pod}}")], 0, 13, 12, 7, unit="percent"),
          series("GPU memory by pod (MiB)", [("DCGM_FI_DEV_FB_USED", "{{pod}} used"), ("DCGM_FI_DEV_FB_FREE", "free")], 12, 13, 12, 7, unit="mbytes"),
          series("Power and temperature", [("sum(DCGM_FI_DEV_POWER_USAGE)", "power W"), ("max(DCGM_FI_DEV_GPU_TEMP)", "temp C")], 0, 20, 12, 7),
          series("Ollama model on GPU", [("ollama_model_gpu_fraction" + INST, "{{model}}")], 12, 20, 12, 7, unit="percentunit")]
    return p


def panels():
    p = list(value_panels())
    p += shift(backfill_panels(), 16)
    p += shift(gpu_panels(), 16 + 16)
    p += shift(core_panels(), 16 + 16 + 27)
    # Build new panels after the existing ones to preserve their IDs and links.
    insert_at = next(i for i, panel in enumerate(p) if panel["title"] == "Backfill progress")
    offset = p[insert_at]["gridPos"]["y"]
    pipeline = pipeline_panels()
    enrichment = photo_enrichment_panels()
    shift(p[insert_at:], 99)
    p[insert_at:insert_at] = shift(pipeline, offset) + shift(enrichment, offset + 42)
    return p


def pipeline_panels():
    """Stage telemetry comes straight from the worker, not the five-minute inventory scan."""
    sel = '{instance=~"$instance",enricher=~"$pipeline_enricher"}'
    stage_rate = 'rate(media_pipeline_stage_seconds_total' + sel + '[$__rate_interval])'
    share = '100 * sum by (stage) (' + stage_rate + ') / scalar(sum(' + stage_rate + '))'
    heartbeat = 'time() - media_pipeline_heartbeat_timestamp_seconds' + sel
    current = ('(media_pipeline_worker_stage' + sel + ' and (' + heartbeat + ' < 60))'
               ' or (media_pipeline_worker_stage' + sel + ' * 0 - 1)')
    states = {str(i): {"text": name, "color": color} for i, name, color in [
        (-1, "No recent telemetry", "gray"), (0, "Between stages", "gray"), (1, "Selecting batch", "purple"),
        (2, "Read / decode", "blue"), (3, "Transcribing", "yellow"), (4, "Building prompt", "light-blue"),
        (5, "Ollama request", "green"), (6, "Parsing answer", "light-purple"), (7, "Writing Parquet", "orange"),
        (8, "Finished", "dark-green"), (9, "Failed", "red")]}
    p = [row("Pipeline bottlenecks", 0)]
    p += [stat("Worker stage", current, 0, 1, w=8, mappings=states, legend="{{instance}} / {{enricher}}"),
          stat("Time in current stage", '(time() - media_pipeline_stage_started_timestamp_seconds' + sel + ') and (' + heartbeat + ' < 60) and (media_pipeline_running' + sel + ' == 1)',
               8, 1, w=8, unit="s", legend="{{instance}} / {{enricher}}"),
          stat("Worker telemetry age", heartbeat, 16, 1, w=8, unit="s", thresholds=[("green", None), ("orange", 30), ("red", 60)],
               description="Published every 5 s by the instrumented worker. Missing data means it has not published yet. After 60 s, the state becomes unknown rather than claiming it is still busy.")]
    graph = _panel("nodeGraph", "Value stream map", [], 0, 5, 24, 10,
                   description="Share of measured worker time by stage in the rate window. Inference includes transport and Ollama time; it is not pure GPU time. Photo path skips transcription; parse loops to decode until the batch is saved. Edges show control flow, not measured per-stage queues.")
    graph["targets"] = [
        {"refId": "nodes", "expr": '(100 * sum by (id, title) (' + stage_rate + ') / scalar(sum(' + stage_rate + ')) >= 0) or (sum by (id, title) (media_pipeline_stage_seconds_total' + sel + ') * 0)', "format": "table", "instant": True, "range": False},
        {"refId": "edges", "expr": 'max by (id, source, target) (media_pipeline_edge_info' + sel + ')', "format": "table", "instant": True, "range": False}]
    photo_rate = 'rate(photo_enrichment_stage_seconds_total' + INST + '[$__rate_interval])'
    graph["targets"][0]["expr"] += ' or (100 * sum by (id, title) (' + photo_rate + ') / scalar(sum(' + photo_rate + ')) >= 0) or (sum by (id, title) (photo_enrichment_stage_seconds_total' + INST + ') * 0)'
    graph["targets"][1]["expr"] += ' or max by (id, source, target) (photo_enrichment_edge_info' + INST + ')'
    # The shared Frigate service reports milliseconds, not a share of caption-worker time.
    # Keep units explicit in each node title instead of formatting every value as percent.
    fresh = ' and on(instance) (time() - photo_frigate_last_poll_timestamp_seconds' + INST + ' < 60)'
    graph["targets"][0]["expr"] = ('label_replace((' + graph["targets"][0]["expr"] + '), "title", "$1 (%)", "title", "(.+)")'
        ' or max by (id,title) (photo_frigate_processing_milliseconds' + INST + fresh + ')'
        ' or max by (id,title) (photo_frigate_service_up' + INST + fresh + ')')
    graph["targets"][1]["expr"] += ' or max by (id,source,target) (photo_frigate_edge_info' + INST + fresh + ')'
    review_rate = 'rate(photo_review_stage_seconds_total' + INST + '[$__rate_interval])'
    graph["targets"][0]["expr"] += ' or label_replace(((100 * sum by(id,title) (' + review_rate + ') / scalar(sum(' + review_rate + ')) >= 0) or sum by(id,title)(photo_review_stage_seconds_total' + INST + ') * 0), "title", "$1 (%)", "title", "(.+)")'
    def node(expression, node_id, title):
        return 'label_replace(label_replace((' + expression + '), "id", "' + node_id + '", "", ""), "title", "' + title + '", "", "")'
    graph["targets"][0]["expr"] += ' or ' + node('sum(photo_enrichment_jobs{instance=~"$instance",kind=~"ready|retry"})','photo_jobs','PostgreSQL queue (jobs)')
    graph["targets"][0]["expr"] += ' or ' + node('max(photo_snapshot_export_seconds'+INST+')','photo_export','Parquet export (seconds)')
    graph["targets"][0]["expr"] += ' or ' + node('time()-min(photo_snapshot_captured_timestamp_seconds'+INST+')','photo_analytics','DuckDB snapshot age (seconds)')
    graph["targets"][0]["expr"] += ' or ' + node('histogram_quantile(0.95,sum by(le)(rate(photo_app_db_duration_seconds_bucket{service_name="photo-review",stage="duckdb.query"}[$__rate_interval])))','photo_gallery','Gallery DuckDB query p95 (seconds)')
    graph["targets"][0]["expr"] += ' or ' + node('histogram_quantile(0.95,sum by(le)(rate(photo_app_db_duration_seconds_bucket{service_name="photo-review",stage="db.query"}[$__rate_interval])))','photo_live_db','GUI PostgreSQL calls p95 (seconds)')
    graph["targets"][1]["expr"] += ' or max by(id,source,target)(photo_pipeline_edge_info'+INST+') or max by(id,source,target)(photo_review_edge_info'+INST+')'
    graph["targets"][1]["expr"] += ' or max by(id,source,target)(photo_app_edge_info'+INST+')'
    context_rate='rate(photo_context_stage_seconds_total'+INST+'[$__rate_interval])'
    graph["targets"][0]["expr"] += ' or label_replace(((100 * sum by(id,title) ('+context_rate+') / scalar(sum('+context_rate+')) >= 0) or sum by(id,title)(photo_context_stage_seconds_total'+INST+') * 0), "title", "$1 (%)", "title", "(.+)")'
    graph["targets"][0]["expr"] += ' or '+node('sum(photo_context_jobs{instance=~"$instance",kind=~"ready|retry"})','photo_context_jobs','Photo context queue (photos)')
    graph["targets"][1]["expr"] += ' or max by(id,source,target)(photo_context_edge_info'+INST+')'
    graph["description"] += " Photo context runs independently: saved person labels and cached nearby Wikipedia/Wikidata candidates go to the local vision model; PostgreSQL retains provenance and the original caption. Nearby does not mean pictured. Provider calls are serialized and budgeted; the GUI performs no external lookup."
    graph["targets"][0]["expr"] += ' or '+node('max(photo_snapshot_index_rows{instance=~"$instance",kind="photos"})','photo_search','Search/group index (photos)')
    graph["description"] += " Gallery lists, filters and counts run in DuckDB over Parquet. Recent PostgreSQL review edits overlay the snapshot immediately. GUI PostgreSQL timing includes live edit reads and other point operations. Query nodes show p95 seconds, not worker percentages; edges describe data flow. Open the Photo App dashboard for request latency, active lock waits, traces and automatic triage."
    graph["description"] += " PostgreSQL is authoritative for enrichment and human edits. Jobs are leased and retries do not block other files. Parquet export is independent of extraction; DuckDB pins a complete generation. Queue nodes show jobs, export shows last successful duration, analytics shows snapshot age; units are explicit in each node title. GUI matching/review percentages are normalized separately from worker percentages. Matching compares saved embeddings against human-confirmed people without regenerating embeddings. Optional automatic acceptance is a separate measured stage; its machine labels never become reference examples until a person confirms them."
    graph["description"] += " Two independent components read the same indexed library: GPU summaries and optional CPU photo enrichment. Percentages are normalized within each worker, not across workers. Photo review is only database-save time, not human thinking/wait time. Optional Frigate calls may use the shared GPU. Uninstrumented photo stages are absent, never synthetic zero measurements. Pending queues appear below; oldest unfinished PostgreSQL job age is shown below; end-to-end lead time is not yet measured."
    add_graph(graph, node)
    # Node Graph reads field.name, not Organize's display-name override.
    # Copy the sole numeric value into an actual mainstat field.
    graph["transformations"] = [
        {"id": "calculateField", "filter": {"id": "byRefId", "options": "nodes"},
         "options": {"mode": "reduceRow", "reduce": {"reducer": "sum", "include": ["Value", "Value #nodes"]}, "alias": "mainstat"}},
        {"id": "organize", "filter": {"id": "byRefId", "options": "nodes"},
         "options": {"excludeByName": {"Time": True, "Value": True, "Value #nodes": True}}},
        {"id": "organize", "filter": {"id": "byRefId", "options": "edges"},
         "options": {"excludeByName": {"Time": True, "Value": True, "Value #edges": True}}}]
    graph["options"] = {"nodes": {"mainStatUnit": ""}}
    graph["description"] += " Frigate is a separate shared-service component: API reachability is 1/0, detector/face nodes show Frigate's rolling processing milliseconds (ms). Those are not caption-worker percentages or evidence of identity-match readiness. Titles identify each unit; no cross-component percentages are added. Frigate values describe its camera service, not uploaded-photo throughput. Zero face milliseconds means no recorded native face processing; it does not prove recognition is working. Frigate nodes disappear after 60 seconds without polling."
    p += [graph, bars("Time spent by stage", share, "{{stage}}", 0, 15, 8, 6, unit="percent", decimals=1,
                      description="Includes in-flight operations, so a stalled decode or model request is visible before it completes. This is wall time, not CPU or GPU utilization.")]
    timeline = _panel("state-timeline", "Worker activity (sampled)", [(current, "{{instance}} / {{enricher}}")], 8, 15, 16, 6, mappings=states)
    timeline["options"] = {"mergeValues": True, "showValue": "auto", "alignValue": "center", "rowHeight": 0.9,
                           "legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "single"}}
    timeline["fieldConfig"]["defaults"]["custom"] = {"spanNulls": False}
    timeline["description"] = "Sampled at Prometheus scrape cadence: stages shorter than a scrape can be missed. Cumulative timing counters still include every measured stage."
    p.append(timeline)
    for x, kind, title in ((0, "photo", "Photo: seconds per stage operation"), (8, "video", "Video: seconds per stage operation"),
                           (16, "batch", "Batch: query / write seconds")):
        ks = '{instance=~"$instance",enricher=~"$pipeline_enricher",kind="' + kind + '"}'
        avg = ('sum by (stage) (rate(media_pipeline_stage_completed_seconds_total' + ks + '[$__rate_interval])) / '
               '(sum by (stage) (rate(media_pipeline_stage_operations_total' + ks + '[$__rate_interval])) > 0)')
        p.append(series(title, [(avg, "{{stage}}")], x, 21, 8, 7, unit="s", decimals=2,
                        description="Mean of completed operations, including failures. Queue and write are per batch, not per item; absent stages have no completed samples."))
    ollama_avg = ('sum by (phase, kind) (rate(media_pipeline_ollama_seconds_total' + sel + '[$__rate_interval])) / '
                  '(sum by (phase, kind) (rate(media_pipeline_ollama_observations_total' + sel + '[$__rate_interval])) > 0)')
    tokens = ('sum by (phase, kind) (rate(media_pipeline_ollama_tokens_total' + sel + '[$__rate_interval])) / '
              '(sum by (phase, kind) (rate(media_pipeline_ollama_seconds_total' + sel + '[$__rate_interval])) > 0)')
    p += [series("Ollama: seconds per response", [(ollama_avg, "{{kind}} / {{phase}}")], 0, 28, 12, 7, unit="s", decimals=2,
                 description="Native API timings: load, prompt processing, generation and total. Total overlaps the components; do not add them. Missing fields are not reported as zero."),
          series("Ollama: tokens per second", [(tokens, "{{kind}} / {{phase}}")], 12, 28, 12, 7, unit="suffix: tokens/s", decimals=1),
          series("Attempted vs saved items per minute", [
              ('sum by (kind, status) (rate(media_pipeline_items_total' + sel + '[$__rate_interval])) * 60', '{{kind}} {{status}} attempted'),
              ('sum by (kind, status) (rate(media_pipeline_persisted_items_total' + sel + '[$__rate_interval])) * 60', '{{kind}} {{status}} saved')],
                 0, 35, 12, 7, decimals=1, description="Attempted items include errors. Saved items advance only after atomic Parquet writes; batching creates bursts."),
          series("Worker time by stage", [(share, "{{stage}}")], 12, 35, 12, 7, unit="percent", decimals=1)]
    # The host is scraped every 30 s; tell Grafana so $__rate_interval includes enough samples.
    for panel in p:
        for target in panel.get("targets", []):
            target["interval"] = "30s"
            if panel["type"] == "stat":
                target.update({"instant": True, "range": False})
            elif panel["type"] != "nodeGraph":
                target.update({"instant": False, "range": True})
    graph["description"] += " Nodes show zero during the first two scrapes while rate samples accumulate."
    return p


def photo_enrichment_panels():
    """Show real CPU branch timing, backlogs and output alongside the GPU branch."""
    age = 'time() - photo_enrichment_heartbeat_timestamp_seconds' + INST
    current = '(photo_enrichment_worker_stage' + INST + ' and (' + age + ' < 60)) or (photo_enrichment_worker_stage' + INST + ' * 0 - 1)'
    states = {str(i): {"text": name} for i, name in [(-1, "Stale telemetry"), (0, "Idle / waiting for selection"),
        (1, "Catalog / queue"), (2, "Read EXIF"), (3, "CPU faces"), (4, "PostgreSQL commit"),
        (5, "Save human labels"), (6, "Optional Frigate"), (7, "Export Parquet"), (8, "Finished"), (9, "Failed")]}
    inventory = lambda kind: 'sum(photo_enrichment_inventory{instance=~"$instance",kind="' + kind + '"})'
    p = [row("Photo enrichment — parallel CPU branch", 0),
         stat("Photo worker stage", current, 0, 1, w=6, mappings=states),
         stat("Photo telemetry age", age, 6, 1, w=6, unit="s", thresholds=[("green", None), ("orange", 30), ("red", 60)]),
         stat("Faces awaiting names", 'sum(photo_enrichment_queue{instance=~"$instance",stage="review"})', 12, 1, w=6),
         stat("Photos with GPS", inventory("gps"), 18, 1, w=6)]
    p += [series("Enrichment work remaining", [('sum by (stage) (photo_enrichment_queue' + INST + ')', '{{stage}} pending'), ('max(media_summaries_queue{instance=~"$instance",enricher=~"$pipeline_enricher"})', 'captions pending')], 0, 5, 12, 7,
                 description="EXIF/faces count indexed photos without a current successful extraction/scan; review counts unnamed detected faces. Face scans with zero faces still count as completed. Human review is optional. These are backlog snapshots, not queue waiting seconds. Snapshot refreshes at startup and after operations; source catalog refresh runs hourly."),
          series("Enrichment facts over time", [(inventory(kind), name) for kind, name in
                 (("exif", "EXIF extracted"), ("gps", "GPS available"), ("faces", "faces detected"), ("named_faces", "faces named"), ("groups", "annotated groups"))], 12, 5, 12, 7,
                 description="Authoritative PostgreSQL facts. Counts can decrease after edits. A separate timer publishes coherent Parquet generations.")]
    average = 'sum by (stage) (rate(photo_enrichment_stage_completed_seconds_total' + INST + '[$__rate_interval])) / (sum by (stage) (rate(photo_enrichment_stage_operations_total' + INST + '[$__rate_interval])) > 0)'
    p += [series("Photo stages: seconds per operation", [(average, '{{stage}}')], 0, 12, 12, 7, unit="s", decimals=3,
                 description="EXIF and CPU faces operate on photos; persistence operates on transactions; review measures annotation saves only; export covers a set of tables. Failed operations are included. Optional Frigate includes HTTP and server time."),
          series("Photo stage operations per minute", [('sum by (stage, status) (rate(photo_enrichment_stage_operations_total' + INST + '[$__rate_interval])) * 60', '{{stage}} / {{status}}')], 12, 12, 12, 7)]
    share = '100 * sum by (stage) (rate(photo_enrichment_stage_seconds_total' + INST + '[$__rate_interval])) / scalar(sum(rate(photo_enrichment_stage_seconds_total' + INST + '[$__rate_interval])))'
    p += [series("CPU branch time by stage", [(share, '{{stage}}')], 0, 19, 12, 7, unit="percent",
                 description="Share of measured operation time, including in-flight work. Idle human time and queue residence are unmeasured. A dominant stage indicates where elapsed work occurs, not hardware saturation."),
          series("Photo extraction errors", [(inventory("exif_errors"), 'EXIF files with errors')], 12, 19, 6, 7),
          series("Photo current operation age", [('((time() - photo_enrichment_stage_started_timestamp_seconds' + INST + ') and (photo_enrichment_worker_stage' + INST + ' > 0) and (photo_enrichment_worker_stage' + INST + ' < 8) and (' + age + ' < 60)) or (photo_enrichment_worker_stage' + INST + ' * 0 and (' + age + ' < 60))', 'current operation seconds')], 18, 19, 6, 7, unit="s", description="Zero between operations or after a clean stop; missing data means telemetry is absent or older than 60 seconds.")]
    frigate_age = 'time() - photo_frigate_last_poll_timestamp_seconds' + INST
    fresh = ' and on(instance) (' + frigate_age + ' < 60)'
    p += [row("Frigate processing — shared service", 45),
          stat("Frigate API reachable", 'photo_frigate_service_up' + INST + fresh, 0, 46, w=6,
               mappings={"0": {"text": "Unreachable", "color": "red"}, "1": {"text": "Up", "color": "green"}},
               description="Endpoint reachability is not face-classifier readiness."),
          stat("Frigate telemetry age", frigate_age, 6, 46, w=6, unit="s"),
          stat("Frigate object processing", 'photo_frigate_frames_per_second{instance=~"$instance",kind="objects"}' + fresh, 12, 46, w=6, unit="fps"),
          stat("Frigate face processing", 'photo_frigate_processing_milliseconds{instance=~"$instance",kind="faces"}' + fresh, 18, 46, w=6, unit="ms",
               description="Native rolling processing time. Zero means no native face processing recorded; this is not an identity-readiness check."),
          series("Frigate processing time", [('photo_frigate_processing_milliseconds' + INST + fresh, '{{kind}}')], 0, 50, 12, 7, unit="ms",
                 description="Native camera-service processing. Uploaded-photo requests are timed separately in the optional photo worker."),
          series("Frigate processing rate", [('photo_frigate_frames_per_second' + INST + fresh, '{{kind}}')], 12, 50, 12, 7, unit="fps")]
    # Missing instrumentation is deliberately distinct from idle (zero) or no backlog.
    for panel in p:
        if "fieldConfig" in panel:
            panel["fieldConfig"]["defaults"]["noValue"] = "Not instrumented"
        for target in panel.get("targets", []):
            target.update({"interval": "30s", "instant": panel["type"] == "stat", "range": panel["type"] != "stat"})
    p += [row("PostgreSQL queue and analytical snapshots", 26),
          series("Photo jobs over time", [('sum by(kind)(photo_enrichment_jobs{instance=~"$instance",kind=~"ready|running|retry|done"})','{{kind}}')],0,27,12,7),
          series("Queue and analytics freshness", [('max(photo_enrichment_jobs{instance=~"$instance",kind="oldest_seconds"})','oldest unfinished job'),('time()-min(photo_snapshot_captured_timestamp_seconds'+INST+')','analytical snapshot age')],12,27,12,7,unit="s"),
          stat("Snapshot export status",'min(photo_snapshot_success'+INST+')',0,34,w=6,mappings=OK),
          stat("Parquet export duration",'max(photo_snapshot_export_seconds'+INST+')',6,34,w=6,unit="s"),
          stat("Current analytical snapshot",'sum(photo_snapshot_bytes'+INST+')',12,34,w=6,unit="bytes"),
          stat("Analytical freshness",'time()-min(photo_snapshot_captured_timestamp_seconds'+INST+')',18,34,w=6,unit="s",thresholds=[("green",None),("orange",600),("red",1800)]),
          series("GUI review operations", [('sum by(stage,status)(rate(photo_review_stage_operations_total'+INST+'[$__rate_interval])) * 60','{{stage}} / {{status}} per minute')],0,38,12,7),
          series("Snapshot export history", [('photo_snapshot_export_seconds'+INST,'export seconds')],12,38,12,7,unit="s")]
    return p


def core_panels():
    p = []
    p.append(row("Index health", 0))
    p += [stat("Exporter", "knowledge_index_exporter_success" + INST, 0, 1, mappings=OK, thresholds=[("red", None), ("green", 1)]),
          stat("Last export age", "time() - knowledge_index_last_run_timestamp_seconds" + INST, 4, 1, unit="s", thresholds=[("green", None), ("orange", 900), ("red", 3600)]),
          stat("Library files", 'sum(knowledge_index_files{source="gphotos",instance=~"$instance"})', 8, 1),
          stat("Media files", 'sum(knowledge_index_files{kind="media",instance=~"$instance"})', 12, 1),
          stat("Sidecars", "knowledge_index_sidecars" + INST, 16, 1),
          stat("Units not indexed", "knowledge_index_pending_units" + INST, 20, 1, thresholds=RED_IF_POS)]
    p.append(row("Photos and Google quota", 5))
    p += [stat("Counts against quota", 'sum(gphotos_quota_bytes{kind="media",instance=~"$instance"})', 0, 6, unit="bytes", decimals=1),
          stat("Media without sidecar", "gphotos_media_without_sidecar" + INST, 4, 6),
          stat("Album duplicates skipped", "gphotos_album_dup_files" + INST, 8, 6),
          stat("Sidecar parse errors", "knowledge_index_sidecar_parse_errors" + INST, 12, 6, thresholds=[("green", None), ("orange", 1)]),
          stat("Older versions kept", "knowledge_index_versions_files" + INST, 16, 6),
          stat("Index size", "knowledge_index_dataset_bytes" + INST, 20, 6, unit="bytes", decimals=1),
          bars("Counted by 'Photos from' year", "gphotos_quota_media_bytes_by_year" + INST, "{{year}}", 0, 10, unit="bytes", decimals=1),
          bars("Library files by kind", "knowledge_index_files" + INST, "{{kind}}", 12, 10)]
    p.append(row("Summaries (local GPU model)", 18))
    p += [stat("Summarized", 'sum(media_summaries_rows{status="ok",instance=~"$instance"})', 0, 19),
          stat("Errors", 'sum(media_summaries_rows{status="error",instance=~"$instance"})', 4, 19, thresholds=[("green", None), ("orange", 1)]),
          stat("Still to do", "max(media_summaries_queue" + INST + ")", 8, 19),
          stat("Progress", 'sum(media_summaries_rows{status="ok",instance=~"$instance"}) / (sum(media_summaries_rows{status="ok",instance=~"$instance"}) + max(media_summaries_queue{instance=~"$instance"}))', 12, 19, unit="percentunit", decimals=1),
          stat("Enricher running", "knowledge_index_enrich_active" + INST, 16, 19, mappings=YN),
          stat("Last batch", "time() - max(media_summaries_last_batch_timestamp_seconds" + INST + ")", 20, 19, unit="s"),
          series("Throughput (summaries per hour)", [('increase(media_summaries_rows{status="ok",instance=~"$instance"}[1h])', "{{enricher}} ok"),
                                                      ('increase(media_summaries_rows{status="error",instance=~"$instance"}[1h])', "{{enricher}} error")], 0, 23, 12),
          series("Rows and queue", [("media_summaries_rows" + INST, "{{enricher}} {{status}}"), ("media_summaries_queue" + INST, "{{enricher}} queue")], 12, 23, 12)]
    p.append(row("Ingest and index pipeline", 31))
    p += [stat("Backfill running", "knowledge_index_backfill_active" + INST, 0, 32, mappings=YN),
          stat("Takeout archives ingested", "gphotos_ingest_archives" + INST, 4, 32),
          stat("Last ingest", "gphotos_ingest_last_ok" + INST, 8, 32, mappings=OK, thresholds=[("red", None), ("green", 1)]),
          stat("Last ingest age", "time() - gphotos_ingest_last_finished_timestamp_seconds" + INST, 12, 32, unit="s"),
          stat("Units in index", "knowledge_index_units" + INST, 16, 32),
          stat("Export time", "knowledge_index_exporter_duration_seconds" + INST, 20, 32, unit="s", decimals=1),
          series("Parquet files per table", [("knowledge_index_parquet_files" + INST, "{{table}}")], 0, 36, 24, 6)]
    p.append(row("Host and disks (the 2026-11-17 outage)", 42))
    p += [stat("Disk SMART", "smart_passed" + INST, 0, 43, w=6, mappings=OK, legend="{{device}} {{model}}", thresholds=[("red", None), ("green", 1)]),
          stat("Host uptime", 'time() - node_boot_time_seconds{job="proxmox-node-exporter",instance=~"$instance"}', 6, 43, w=6, unit="s"),
          series("Pending sectors per disk", [("smart_pending_sectors" + INST, "{{device}} {{model}} pending"),
                                              ("smart_offline_uncorrectable" + INST, "{{device}} {{model}} uncorrectable"),
                                              ("smart_reallocated_sectors" + INST, "{{device}} {{model}} reallocated")], 12, 43, 12, 8),
          series("Reboots (boot time changes per hour)", [('changes(node_boot_time_seconds{job="proxmox-node-exporter",instance=~"$instance"}[1h])', "{{instance}}")], 0, 47, 12, 6),
          series("NVMe power cycles", [("nvme_power_cycles_total" + INST, "{{device}}")], 0, 53, 12, 6)]
    # Allocate the new panel last so existing panel IDs (and bookmarked links) stay stable.
    summary_stats = {panel["title"]: panel for panel in p if panel["type"] == "stat"}
    history = series("Summary progress over time",
                     [(summary_stats[name]["targets"][0]["expr"], name)
                      for name in ("Summarized", "Still to do", "Errors")],
                     0, 23, 24, 8, decimals=0,
                     description="The totals above over the selected time range. Errors use the right axis. Counts update when the metrics exporter runs.")
    history["fieldConfig"]["defaults"].update({
        "min": 0, "custom": {"drawStyle": "line", "lineInterpolation": "linear", "lineWidth": 2,
                              "fillOpacity": 0, "showPoints": "never", "spanNulls": False,
                              "axisLabel": "Items", "stacking": {"mode": "none", "group": "A"}}})
    for name, color in (("Summarized", "green"), ("Still to do", "blue"), ("Errors", "orange")):
        properties = [{"id": "color", "value": {"mode": "fixed", "fixedColor": color}}]
        if name == "Errors":
            properties += [{"id": "custom.axisPlacement", "value": "right"},
                           {"id": "custom.axisLabel", "value": "Errors"}]
        history["fieldConfig"]["overrides"].append({"matcher": {"id": "byName", "options": name}, "properties": properties})
    for target in history["targets"]:
        target.update({"range": True, "instant": False})
    insert_at = next(i for i, panel in enumerate(p) if panel["gridPos"]["y"] >= 23)
    shift(p[insert_at:], 8)
    p.insert(insert_at, history)
    return p


def dashboard():
    return {
        "annotations": {"list": []}, "description": "Knowledge index: photo inventory, Google quota, GPU summaries, ingest pipeline, host and disk health. Generated by scripts/knowledge-index/gen-dashboard.py",
        "editable": True, "graphTooltip": 1, "id": None, "links": [{"title": "Photo app traces, logs & triage", "url": "/d/photo-app/photo-app"}], "panels": panels(), "refresh": "1m", "schemaVersion": 39,
        "tags": ["knowledge-index", "photos", "homelab"], "time": {"from": "now-24h", "to": "now"}, "timezone": "browser",
        "templating": {"list": [{"current": {}, "datasource": DS, "definition": "label_values(knowledge_index_exporter_success, instance)", "hide": 0, "includeAll": True,
                                 "label": "Host", "multi": True, "name": "instance", "options": [], "query": "label_values(knowledge_index_exporter_success, instance)",
                                 "refresh": 2, "regex": "", "skipUrlSync": False, "sort": 1, "type": "query", "allValue": ".*"},
                                {"type": "query", "name": "pipeline_enricher", "label": "Pipeline enricher", "datasource": DS,
                                 "query": 'label_values(media_pipeline_worker_stage{instance=~"$instance"}, enricher)', "refresh": 2,
                                 "multi": True, "includeAll": True, "allValue": ".*", "current": {"text": "All", "value": "$__all"}, "options": []},
                                *[_textbox(n, l, v) for n, l, v in TEXTBOXES]]},
        "title": "Knowledge Index", "uid": "knowledge-index", "version": 1,
    }


def main():
    body = json.dumps(dashboard(), indent=2)
    print("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: grafana-dashboard-knowledge-index\n  namespace: monitoring\n  labels:\n    grafana_dashboard: \"1\"\n"
          "  annotations:\n    grafana_folder: \"Homelab\"\ndata:\n  knowledge-index.json: |")
    print("\n".join("    " + ln for ln in body.splitlines()))


if __name__ == "__main__":
    main()
