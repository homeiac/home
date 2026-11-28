#!/usr/bin/env python3
"""Generate the Grafana dashboard ConfigMap for the knowledge index (dashboards as code, issue #212).

Usage: gen-dashboard.py > gitops/clusters/homelab/apps/photo-enrichment/knowledge-index-dashboard.yaml
Output is deterministic; test-metrics.sh fails if the committed YAML differs from what this prints. Edit THIS file, then regenerate.
Metrics come from export-metrics.py (node-exporter textfile on the Proxmox host); host/disk panels also use node_boot_time_seconds and nvme_* .
"""
import json
from pathlib import Path
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


SUMMARY_SELECTION = 'instance=~"$instance",enricher=~"$pipeline_enricher"'
THROUGHPUT_HEIGHT = 8
RECONCILIATION_HEIGHT = 28
VIDEO_TUNING_HEIGHT = 42
AUDIO_STORY_HEIGHT = 36
# Derived unit rate only; private account readings remain in the local usage DB.
OBSERVED_RECONCILIATION_USD_PER_SUMMARY = 0.000869
# Observed production transitions in UTC.
ONE_SLOT_REFERENCE = 1795280280  # Last clean 10-minute window ending Nov 21 16:58 UTC.
TWO_SLOT_START = 1795280415      # Runner accepted work Nov 21 17:00:14 UTC.
TWO_SLOT_WINDOW = TWO_SLOT_START + 600
GPU_DISPATCH_START = 1795293575  # Continuous refill deployed Nov 21 at 20:39:35 UTC.
GPU_DISPATCH_BASELINE = 1795292400  # Start of the measured 20:20–20:30 UTC baseline.


def summary_pace(at=None):
    """Successful summary rows committed per second over ten minutes."""
    selector = f'media_pipeline_persisted_items_total{{status="ok",{SUMMARY_SELECTION}}}[10m]'
    if at is not None:
        selector += f' @ {at}'
    return f'max by(enricher) (sum by(instance,enricher) (rate({selector})))'


def backend_pace(backend, window="10m"):
    selector = f'media_pipeline_backend_saved_total{{{SUMMARY_SELECTION},backend="{backend}"}}'
    return f'max(sum by(instance,enricher) (rate({selector}[{window}]))) * 60'


def throughput_panels():
    gpu_pace = f'({backend_pace("primary")}) + ({backend_pace("metal")})'
    after = f'({gpu_pace}) and on() (vector(time()) >= {GPU_DISPATCH_START + 600})'
    before_dispatch = (f'({gpu_pace}) and on() (vector(time()) >= {GPU_DISPATCH_BASELINE + 600}) '
                       f'and on() (vector(time()) < {GPU_DISPATCH_START})')
    # The recorded observation survives TSDB retention. Scope its fallback to
    # the same host and enricher as the pinned Prometheus sample.
    observed = (f'max by(enricher) (media_pipeline_queue{{{SUMMARY_SELECTION},'
                'instance="pumped-piglet",enricher="gemma4-e2b-p1"}) * 0 + 11.789473684210524')
    before = f'(({summary_pace(ONE_SLOT_REFERENCE)}) * 60) or ({observed})'
    rtx_observed = observed.replace("11.789473684210524", "20.208747368421054")
    two_slots = f'(({summary_pace(1795281480)}) * 60) or ({rtx_observed})'
    joint_scope = (f'max(media_pipeline_queue{{{SUMMARY_SELECTION},'
                   'instance="pumped-piglet",enricher="gemma4-e2b-p1"}) * 0')
    observed_joint = f'{joint_scope} + 21.4'
    observed_refill = f'{joint_scope} + 28'
    fast_rate = f'({backend_pace("primary", "2m")}) + ({backend_pace("metal", "2m")})'
    comparison = _panel('stat', 'Summaries saved/min · before and now',
                        [(before, 'RTX · one slot'), (two_slots, 'RTX · two slots'),
                         (observed_joint, 'RTX + Mac · before refill'), (observed_refill, 'RTX + Mac · measured after refill'),
                         (fast_rate, 'RTX + Mac · latest 2 min')],
                        0, 5, 10, 7, decimals=1,
                        extra={'options': {'textMode': 'value_and_name', 'orientation': 'vertical',
                                           'reduceOptions': {'calcs': ['lastNotNull']}}},
                        description='On Nov 21 the RTX and Mac saved 214 items (38 videos) from 20:20–20:30 UTC before refill and 280 items (one video) from 20:43:40–20:53:40 UTC after refill. This production comparison excludes Luna and cache saves. The RTX-only baselines cover 16:48–16:58 and 17:08–17:18 UTC.')
    for target in comparison['targets']:
        target.update(instant=True, range=False)
    comparison['fieldConfig']['defaults']['noValue'] = 'Awaiting sample'
    labels = ('Before refill', 'After refill', 'Goal · 30/min')
    goal = f'vector(30) and on() (vector(time()) >= {GPU_DISPATCH_BASELINE + 600})'
    history = series('RTX + Mac Parquet saves/min · before and after',
                     list(zip((before_dispatch, after, goal), labels)), 10, 5, 14, 7, decimals=1,
                     description='Rolling ten-minute Parquet saves from the RTX and Mac only. Luna and cache saves are excluded. The gap excludes windows crossing the scheduler deployment.')
    for target in history['targets']:
        target.update(instant=False, range=True, interval='30s')
    history['fieldConfig']['defaults'].update(min=0, custom={'drawStyle': 'line', 'lineWidth': 2, 'showPoints': 'never', 'spanNulls': False})
    for label, color in zip(labels, ('orange', 'green', 'gray')):
        history['fieldConfig']['overrides'].append({'matcher': {'id': 'byName', 'options': label},
            'properties': [{'id': 'color', 'value': {'mode': 'fixed', 'fixedColor': color}}]})
    return [comparison, history]


def work_remaining_panels():
    """Queue estimates and USE signals for the summary pipeline on Piglet."""
    selection = SUMMARY_SELECTION
    fresh = ('(knowledge_index_exporter_success' + INST + ' == 1) and on(instance,job) '
             '(time() - node_textfile_mtime_seconds{file=~".*/knowledge_index[.]prom",instance=~"$instance"} < 900)')
    heartbeat = f'(time() - media_pipeline_heartbeat_timestamp_seconds{{{selection}}} < 60)'
    worker_queue = (f'max by(enricher) (media_pipeline_queue{{{selection}}} and on(instance,enricher,job) '
                    f'({heartbeat} and (media_pipeline_running{{{selection}}} == 1)))')
    exported_queue = (f'max by(enricher) (media_summaries_queue{{{selection}}} '
                      f'and on(instance,job) ({fresh}))')
    queue = f'({worker_queue} or {exported_queue})'
    pace = summary_pace()
    window_ready = f'((vector(time()) < {TWO_SLOT_START}) or (vector(time()) >= {TWO_SLOT_WINDOW}))'
    warming = f'((vector(time()) >= {TWO_SLOT_START}) and (vector(time()) < {TWO_SLOT_WINDOW}))'
    running = (f'max by(enricher) (media_pipeline_running{{{selection}}} and on(instance,enricher,job) '
               f'{heartbeat})')
    eta = (f'((({queue} / ({pace} > 0)) and ({running} == 1)) and on() {window_ready}) or ({queue} == 0) '
           f'or ((({queue} > 0) and ({running} == 1)) and on() {warming}) * 0 - 4 '
           f'or (({queue} > 0) and ({running} == 0)) * 0 - 2 '
           f'or (({queue} > 0) unless {running}) * 0 - 3 '
           f'or ({queue} > 0) * 0 - 1')
    stage_rate = f'sum by(enricher,title)(rate(media_pipeline_stage_seconds_total{{{selection}}}[30m]))'
    slowest = f'topk by(enricher)(1, (100 * {stage_rate} / on(enricher) group_left sum by(enricher) ({stage_rate})) > 0)'

    context = 'sum(photo_context_jobs{instance=~"$instance",kind=~"ready|running|retry"})'
    context_pace = 'sum(deriv(photo_context_jobs{instance=~"$instance",kind="done"}[1h]))'
    context_active = 'max(node_systemd_unit_state{instance="pumped-piglet",name="photo-enrichment-context.service",state="active"})'
    context_eta = (f'({context} / ({context_pace} > 0) and on() ({context_active} == 1)) '
                   f'or ({context} == 0) or (({context} > 0) and on() ({context_active} == 0)) * 0 - 2 '
                   f'or ({context} > 0) * 0 - 1')
    no_eta = {"-4": {"text": "Collecting two-slot writes", "color": "blue"},
              "-1": {"text": "No recent progress", "color": "orange"},
              "-2": {"text": "Worker stopped", "color": "orange"},
              "-3": {"text": "Worker status unknown", "color": "gray"},
              "0": {"text": "Queue clear", "color": "green"}}
    p = [row("Work remaining & bottleneck", 0),
         stat("Local queue · files still to process", queue, 0, 1, w=6, unit="locale", legend="{{enricher}}", description="Local worker queue, including file copies and files already captioned by Luna. This is not the number of deduplicated photos missing any caption. The worker updates after successful Parquet writes; fallback is the five-minute index export."),
         stat("Summary finish estimate", eta, 6, 1, w=6, unit="s", legend="{{enricher}}", mappings=no_eta, description="Current backlog divided by the last ten minutes of successful Parquet writes from all active backends. Assumes the same photo/video mix and no new arrivals. Requires a fresh running-worker heartbeat."),
         stat("Summaries saved / minute", pace + ' * 60', 12, 1, w=5, decimals=1, legend="{{enricher}}", description="Successful rows saved to Parquet over the last ten minutes."),
         stat("Summary bottleneck · stage", slowest, 17, 1, w=7, unit="percent", decimals=0, legend="{{title}}", extra_opts={"textMode": "value_and_name"}, description="Largest share of measured operation time over 30 minutes. Concurrent operations each contribute time. Model requests include queueing, transport and inference.")]
    p += [stat("Photo context still to do", context, 0, 5, w=5, unit="locale"),
          stat("Photo context finish estimate", context_eta, 5, 5, w=5, unit="s", mappings=no_eta, description="The context worker pauses during the summaries-only backfill. While active, its ETA uses the last hour of completed jobs."),
          stat("Photo extraction jobs left", 'sum(photo_enrichment_jobs{instance=~"$instance",kind=~"ready|running|retry"})', 10, 5, w=5, unit="locale", description="Includes delayed retries. See the PostgreSQL queue section for age and retry counts."),
          stat("Immich jobs outstanding", 'sum(immich_queue_jobs{state=~"waiting|active|delayed|prioritized|paused"})', 15, 5, w=5, unit="locale", description="All native Immich queues. Open Photo App for per-queue throughput and estimates."),
          stat("Immich sync", 'sum by(state)(immich_sync_assets{state=~"pending|conflict"})', 20, 5, w=4, unit="locale", legend="{{state}}", extra_opts={"textMode": "value_and_name"}, description="Pending assets are ready for transfer. Conflicts require review and do not contribute to automatic queue drain.")]

    host = '{job="proxmox-node-exporter",instance="pumped-piglet"}'
    vm = 'and on(instance,job) node_uname_info{job="node-exporter",nodename="k3s-vm-pumped-piglet-gpu"}'
    gpu = '{Hostname="k3s-vm-pumped-piglet-gpu"}'
    def latest(title, queries, x, width, thresholds, unit='short', description='', decimals=1):
        panel = stat(title, queries[0][0], x, 10, w=width, h=6, unit=unit,
                     legend=queries[0][1], decimals=decimals, thresholds=thresholds,
                     extra_opts={"textMode": "value_and_name"}, description=description)
        panel["targets"].extend({"refId": chr(65 + i), "expr": expr, "legendFormat": label}
                                for i, (expr, label) in enumerate(queries[1:], 1))
        return panel

    p.append(row("USE checks · Piglet host and GPU VM", 9))
    p.append(latest("Utilization · percent busy", [
        (f'avg_over_time((max(DCGM_FI_DEV_GPU_UTIL{gpu}))[5m:15s])', 'Shared GPU'),
        ('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle",job="proxmox-node-exporter",instance="pumped-piglet"}[5m])))', 'Host CPU'),
        (f'100 * (1 - sum(node_memory_MemAvailable_bytes {vm}) / sum(node_memory_MemTotal_bytes {vm}))', 'VM RAM'),
        ('100 * max(rate(node_disk_io_time_seconds_total' + host + '[5m]))', 'Busiest host disk'),
    ], 0, 8, [('green', None), ('orange', 85), ('red', 95)], 'percent', 'Five-minute utilization where available. GPU activity is shared across Ollama, Frigate and Immich.'))
    pressure = [(f'100 * max(rate(node_pressure_{resource}_waiting_seconds_total{host}[5m]) '
                 f'or (rate(node_pressure_{resource}_waiting_seconds_total{{job="node-exporter"}}[5m]) {vm}))', label)
                for resource, label in [('cpu', 'CPU wait'), ('memory', 'Memory wait'), ('io', 'I/O wait')]]
    p.append(latest("Saturation · percent of time waiting", pressure, 8, 8,
                    [('green', None), ('orange', 10), ('red', 25)], 'percent',
                    'CPU, RAM and I/O pressure show the worse of the host and GPU VM over five minutes. Ollama request queue depth is not exported.'))
    p.append(latest("Errors · last hour", [
        (f'sum(increase(media_pipeline_items_total{{status="error",{selection}}}[1h]))', 'Failed summary attempts'),
        (f'max(DCGM_FI_DEV_XID_ERRORS{gpu})', 'Last GPU Xid code'),
        (' + '.join(f'sum(increase(node_network_{metric}_total{host}[1h]))' for metric in ('receive_errs', 'transmit_errs', 'receive_drop', 'transmit_drop')), 'Host network errors/drops'),
    ], 16, 8, RED_IF_POS, description='GPU Xid is the last driver error code, not an hourly count. Summary attempts include failed items before Parquet persistence.', decimals=0))
    for panel in p:
        if panel['type'] == 'stat':
            panel['fieldConfig']['defaults']['noValue'] = 'No data'
        for target in panel.get('targets', []):
            target.update(instant=True, range=False)
    return p


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
    SUMM = f'sum({summary_pace()}) * 60'
    QS = 'knowledge_index_query_seconds{query="quota",instance=~"$instance"}'
    COST = ('sum(media_summaries_ok_items{kind="photo",instance=~"$instance"}) * $price_photo'
            ' + sum(media_summaries_video_seconds' + INST + ') / 60 * $price_video_min')
    p = [row("Value delivered", 0)]
    p += [stat("Files indexed per minute", "clamp_min(" + FILES + ", 0)", 0, 1, w=4, decimals=0, description="Backfill speed: files read per minute (5 min window). Only while a run publishes progress."),
          stat("Summaries per minute", SUMM, 4, 1, w=4, decimals=1, description="Successful local summary rows saved to Parquet per minute over the last ten minutes."),
          stat("Quota question answered in", QS, 8, 1, w=4, unit="s", decimals=2, description="How long 'what counts against Google quota?' takes against the index right now."),
          stat("Faster than before", "$baseline_s / " + QS, 12, 1, w=4, unit="suffix:x", decimals=0, description="Baseline: reading ~120k Takeout sidecars from the USB disk took about 38 min (2026-11-16). Edit the baseline_s variable to change it."),
          stat("Index size", "knowledge_index_dataset_bytes" + INST, 16, 1, w=4, unit="bytes", decimals=1, description="Parquet files plus the DuckDB view file."),
          stat("Index vs library", "knowledge_index_dataset_bytes" + INST + ' / sum(knowledge_index_bytes{source="gphotos",instance=~"$instance"})', 20, 1, w=4, unit="percentunit", decimals=3, description="Index size as a share of the photo library it describes.")]
    p += [stat("Library size", 'sum(knowledge_index_bytes{source="gphotos",instance=~"$instance"})', 0, 5, w=4, unit="bytes", decimals=1),
          stat("Local photo captions · incl. copies", 'sum(media_summaries_ok_items{kind="photo",instance=~"$instance"})', 4, 5, w=4,
               description="Successful local caption rows across enrichers, including separate album file copies. Not a deduplicated photo count; excludes Luna. See deduped completion above for current-file coverage."),
          stat("Video minutes described", "sum(media_summaries_video_seconds" + INST + ") / 60", 8, 5, w=4, decimals=0),
          stat("Cloud-equivalent cost avoided", COST, 12, 5, w=8, unit="currencyUSD", decimals=2,
               description="ILLUSTRATIVE. No cloud service describes a Google Photos library like this. Priced as if a multimodal AI API charged per photo and per video minute; set the two price variables at the top to your own assumptions. Not a quote."),
          stat("Counts against Google quota", 'sum(gphotos_quota_bytes{kind="media",instance=~"$instance"})', 20, 5, w=4, unit="bytes", decimals=1)]
    p += [series("Throughput per minute", [("clamp_min(" + FILES + ", 0)", "files indexed / min"), (SUMM, "summaries saved / min")], 0, 9, 12, 7,
                 description="Indexing throughput and successful local summary writes. The summary line uses the worker's Parquet save counter over ten minutes, including cache saves and excluding Luna."),
          series("Index size vs library size", [("knowledge_index_dataset_bytes" + INST, "index"), ('sum(knowledge_index_bytes{source="gphotos",instance=~"$instance"})', "library")], 12, 9, 12, 7, unit="bytes")]
    return p


def gpu_panels():
    """GPU (DCGM exporter) and Ollama (exporter's /api/ps reader). GPU series are not filtered by $instance: the DCGM exporter has its own instance label."""
    pods = 'DCGM_FI_DEV_GPU_UTIL'
    KWH = "sum(increase(DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION[$__range])) / 3.6e9"   # sum: the pod label changes as different pods use the GPU
    PAUSED = {"0": {"text": "STOPPED", "color": "red"}, "1": {"text": "running", "color": "green"}}
    p = [row("Model servers and shared RTX 3070", 0)]
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
    p += [stat("Frigate", 'kube_deployment_spec_replicas{namespace="frigate",deployment="frigate"}', 0, 9, w=3, mappings=PAUSED, thresholds=[("red", None), ("green", 1)],
               description="0 = paused on purpose for GPU work (scripts/k3s/gpu-tenants.sh); cameras are not recording."),
          stat("Stable Diffusion", 'kube_deployment_spec_replicas{namespace="stable-diffusion",deployment="stable-diffusion-webui"}', 3, 9, w=3, mappings=PAUSED, thresholds=[("red", None), ("green", 1)]),
          stat("Ollama pod", 'kube_deployment_status_replicas_available{namespace="ollama",deployment="ollama-gpu"}', 6, 9, w=3, mappings=PAUSED, thresholds=[("red", None), ("green", 1)]),
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
    priority_stages = [panel for panel in pipeline if panel["gridPos"]["y"] == 21]
    pipeline = [panel for panel in pipeline if panel not in priority_stages]
    shift([panel for panel in pipeline if panel["gridPos"]["y"] > 21], -7)
    shift(priority_stages, 13)
    enrichment = photo_enrichment_panels()
    shift(p[insert_at:], 92)
    p[insert_at:insert_at] = shift(pipeline, offset) + shift(enrichment, offset + 35)
    overview = work_remaining_panels()
    ollama = next(i for i, panel in enumerate(p) if panel['title'] == 'Ollama pod')
    p.insert(ollama + 1, stat("Standalone Bonsai", 'kube_deployment_status_replicas_available{namespace="immich-pilot",deployment="photo-bonsai"}',
                             9, p[ollama]['gridPos']['y'], w=3, mappings=YN))
    intro = [panel for panel in overview if panel['gridPos']['y'] < 5]
    details = [panel for panel in overview if panel['gridPos']['y'] >= 5]
    throughput = throughput_panels()
    luna = [stat("Luna captions saved to Parquet", 'max(knowledge_index_luna_saved' + INST + ')', 0, 12, w=8, unit="locale"),
            stat("Luna estimated token cost", 'max(knowledge_index_luna_proxy_usd' + INST + ')', 8, 12, w=8, unit="currencyUSD", decimals=3,
                 description="Reported Codex tokens valued at standard Luna API rates, plus projected cost for requests without a usage report. The Enterprise account supplies inference."),
            stat("Luna budget available", '250 - max(knowledge_index_luna_proxy_usd' + INST + ') - max(knowledge_index_luna_budget_held_usd' + INST + ') - max(knowledge_index_reconciliation_estimated_and_held_usd' + INST + ')',
                 16, 12, w=8, unit="currencyUSD", decimals=2,
                 description="The shared $250 Luna estimate allowance less original caption costs and holds, reconciliation costs and holds, and the earlier pilot allowance. Not actual billing.")]
    for panel in luna:
        panel['targets'][0].update(instant=True, range=False)
    backend_series = [(backend_pace(name), label) for name, label in
                      (("primary", "RTX"), ("metal", "Mac Metal"), ("cache", "Cache"))]
    luna_rate = 'clamp_min(max(deriv(knowledge_index_luna_saved' + INST + '[10m])), 0) * 60'
    combined_rate = f'sum(({summary_pace()}) * 60) + ({luna_rate})'
    backend_series.extend([(luna_rate, "Luna · Enterprise"), (combined_rate, "Combined · all captions")])
    backends = series("Parquet summaries saved per minute by backend", backend_series, 0, 16, 24, 6, decimals=1,
                      description="Bonsai uses the shared RTX and Mac queue. Luna writes a separate comparison dataset. Each line measures saved rows over ten minutes. The same asset can have both a Bonsai and a Luna caption.")
    scope = "{" + SUMMARY_SELECTION + "}"
    hit_bytes = f'sum by(capacity_mib)(increase(media_pipeline_mac_cache_reusable_bytes_total{scope}[1h]))'
    sent_bytes = f'sum(increase(media_pipeline_mac_candidate_bytes_total{scope}[1h]))'
    cache_sim = series("Mac preview cache · estimated bytes reusable",
                       [(f'100 * {hit_bytes} / on() group_left() ({sent_bytes} > 0)', "{{capacity_mib}} MiB")],
                       0, 22, 12, 6, decimals=2, unit="percent",
                       description="Last hour of actual Mac-bound JPEG traffic after the existing caption cache. Three simulated LRU capacities retain only frame hashes and sizes. A zero means no observed reusable bytes. A gap means no traffic.")
    seconds = f'sum by(phase,kind)(rate(media_pipeline_mac_phase_seconds_total{scope}[10m]))'
    counts = f'sum by(phase,kind)(rate(media_pipeline_mac_phase_observations_total{scope}[10m]))'
    phases = series("Mac inference seconds per successful request", [(f'{seconds} / ({counts} > 0)', "{{kind}} · {{phase}}")],
                    12, 22, 12, 6, decimals=2, unit="s",
                    description="Round trip starts on Piglet before the HTTP request. Prompt processing includes visual input. Generation is output decoding. Queueing, transport and other server overhead contribute to the round trip.")
    occupancy = series("GPU request slots in use · 2 min average", [
        (f'max(avg_over_time(media_pipeline_backend_in_flight{scope[:-1]},backend="{backend}"}}[2m]))', label)
        for backend, label in (("primary", "RTX"), ("metal", "Mac Metal"))
    ] + [(f'max(media_pipeline_mac_request_limit{scope})', "Mac available slots")],
        0, 28, 14, 6, decimals=1,
        description="Active HTTP model requests. RTX has two configured slots. The Mac reports zero available slots when unreachable.")
    active_policy = stat("Bonsai dispatch policy applied", f'max by(mode,page_size,mac_routing,queue_order) '
                         f'(media_pipeline_dispatch_policy_applied_timestamp_seconds{scope}) * 1000',
                         14, 28, w=10, h=6, unit="dateTimeAsIso",
                         legend="{{mode}} · page {{page_size}} · {{queue_order}}",
                         extra_opts={"textMode": "value_and_name"},
                         description="The active Git policy and when the worker adopted it. Photos-first orders the entire pending queue. When pending photos drain, the same worker processes videos. Page 0 uses four items per slot, with a minimum of one Parquet write batch.")
    active_policy["targets"][0].update(instant=True, range=False)
    host_fresh = f'time() - media_pipeline_heartbeat_timestamp_seconds{scope} < 60'
    def host_value(metric, backend=None):
        selector = scope if backend is None else scope[:-1] + f',backend="{backend}"}}'
        return f'max({metric}{selector} and on(instance,enricher,job) ({host_fresh}) and on(instance,enricher,job) (media_pipeline_running{scope} == 1))'
    def luna_value(metric, state=None, fresh=True):
        selector = INST if state is None else INST[:-1] + f',state="{state}"}}'
        clause = ' and on(instance,job) (time() - knowledge_index_luna_heartbeat_timestamp_seconds' + INST + ' < 240)' if fresh else ''
        return f'max({metric}{selector}{clause})'
    def location(title, queries, x, description):
        panel = _panel("stat", title, queries, x, 6, 6, 5, decimals=0, description=description,
                       extra={"options": {"textMode": "value_and_name", "orientation": "vertical", "graphMode": "none"}})
        panel["fieldConfig"]["defaults"]["noValue"] = "No recent report"
        for target in panel["targets"]:
            target.update(instant=True, range=False)
        return panel
    locations = [row("Where work is running", 5),
        location("RTX 3070 · Bonsai", [(host_value("media_pipeline_backend_in_flight", "primary"), "Active requests")], 0,
                 "Ollama runs in K3s on Piglet’s RTX. The summary worker reserves two model slots."),
        location("Mac GPU · Bonsai", [(host_value("media_pipeline_backend_in_flight", "metal"), "Active requests"),
                                      (host_value("media_pipeline_mac_request_limit"), "Photo request capacity"),
                                      (host_value("media_pipeline_mac_video_request_limit"), "Video request cap")], 6,
                 "Piglet sends distinct pending items to the Mac Metal worker. Zero capacity means it is currently unavailable for backfill."),
        location("Submission client → Enterprise Luna", [(luna_value("knowledge_index_luna_runner", fresh=False), "Last active client"),
                                                (luna_value("knowledge_index_luna_parallel", fresh=False), "Request slots"),
                                                (luna_value("knowledge_index_luna_jobs", "sent"), "Submitted"),
                                                (luna_value("knowledge_index_luna_jobs", "reserved"), "Preparing"),
                                                (luna_value("knowledge_index_luna_jobs", "unknown", False), "Requests with projected cost"),
                                                (luna_value("knowledge_index_luna_blocked", fresh=False), "Accounting hold (1 = paused)")], 12,
                 "The client submits to Enterprise Codex. Submitted and preparing require a recent report. The last recorded client and accounting hold remain visible when idle."),
        location("Piglet · Luna publication", [(luna_value("knowledge_index_luna_jobs", "pending", False), "Pending"),
                                              (luna_value("knowledge_index_luna_awaiting_publish"), "Completed, awaiting Parquet")], 18,
                 "Luna has a separate queue and Parquet dataset on Piglet. The Bonsai queue and its finish estimate appear above.")]
    locations[3]["fieldConfig"]["overrides"].append({
        "matcher": {"id": "byName", "options": "Last active client"},
        "properties": [{"id": "mappings", "value": [{"type": "value", "options": {
            "1": {"text": "Mac"}, "2": {"text": "still-fawn"}
        }}]}],
    })
    coverage = 'knowledge_index_caption_coverage{instance=~"$instance",coverage='
    snapshot_fresh = (' and on(instance,job) (knowledge_index_exporter_success' + INST + ' == 1) '
                      'and on(instance,job) (time() - knowledge_index_last_run_timestamp_seconds' + INST + ' < 900)')
    def covered(selector):
        return f'sum(max by(coverage) ({coverage}{selector}}}{snapshot_fresh}))'
    unique = covered('~"local_only|luna_only|both"')
    remaining = covered('"neither"')
    unique_pace = 'max(knowledge_index_caption_first_saved_last_ten_minutes' + INST + snapshot_fresh + ') / 10'
    eta = f'(({remaining}) / (({unique_pace}) > 0)) * 60 or ({remaining} == 0)'
    backends["targets"].append(dict(refId="F", expr=unique_pace, legendFormat="First caption · distinct items"))
    coverage_note = "Piglet joins both published Parquet datasets to the current library by path and byte size every five minutes."
    combined = [
        stat("Combined captions saved / min", combined_rate, 0, 11, w=6, decimals=1,
             description="Bonsai and Luna outputs over ten minutes. When both caption one asset, each output counts."),
        stat("Distinct items with a caption", unique, 6, 11, w=6, unit="locale", description=coverage_note),
        stat("Items without any caption", remaining, 12, 11, w=6, unit="locale", description=coverage_note),
        stat("ETA to first caption for every item", eta, 18, 11, w=6, unit="s",
             description=coverage_note + " Remaining items divided by the count reaching their first retained caption in the preceding ten minutes. Assumes similar media mix, uptime and Luna availability.")]
    for panel in combined:
        panel["targets"][0].update(instant=True, range=False)
        panel["fieldConfig"]["defaults"]["noValue"] = "Awaiting fresh data"
    all_panels = intro + locations + combined + shift(throughput + luna + [backends, cache_sim, phases, occupancy, active_policy] + priority_stages, 10) + shift(details, THROUGHPUT_HEIGHT + 39) + shift(p, 56 + THROUGHPUT_HEIGHT)
    bottom = max(panel["gridPos"]["y"] + panel["gridPos"]["h"] for panel in all_panels)
    all_panels += shift(immich_face_panels(), bottom)
    reconciliation = reconciliation_panels()
    # Allocate new IDs after all existing panels so bookmarked panels stay stable.
    completion = caption_completion_panels()
    shift([panel for panel in all_panels if panel['gridPos']['y'] >= 5], 10)
    all_panels = all_panels[:len(intro)] + completion + all_panels[len(intro):]
    tuning = video_tuning_panels()
    audio = audio_story_panels()
    processing = photo_processing_panels()
    bottom = max(panel["gridPos"]["y"] + panel["gridPos"]["h"] for panel in all_panels)
    all_panels += shift(life_stage_tuning_panels(), bottom)
    # Allocate the backend charts last to keep all existing dashboard links stable.
    charts_at = next(i for i, panel in enumerate(processing) if panel["type"] == "timeseries")
    backend_charts = photo_backend_panels(processing[charts_at]["gridPos"]["y"])
    recovery = caption_recovery_panels()
    # Allocate the timing panel after recovery so existing panel links stay stable.
    timing_y = max(panel["gridPos"]["y"] + panel["gridPos"]["h"] for panel in backend_charts)
    backend_charts.append(photo_server_timing_panel(timing_y))
    for trial in json.loads(Path(__file__).with_name("library-server-timing.json").read_text()).get("cpu_capacity_trials", []):
        trial_y = max(panel["gridPos"]["y"] + panel["gridPos"]["h"] for panel in backend_charts)
        rates = []
        for backend, values in trial["peer_rates"].items():
            rates.extend([
                (f'vector({values["before_per_min"]})', f'{backend} · protected baseline'),
                (f'vector({values["trial_per_min"]})', f'{backend} · CPU trial'),
            ])
        quality = trial["quality"]
        description = (
            f'{trial["threads"]} threads with aggregate quota {trial["quota_percent"]}%. '
            f'{trial["scope"]}. Stage correct {quality["stage_correct"]}/{quality["reviewed"]}, '
            f'supported action {quality["supported_actions"]}/{quality["reviewed"]}, '
            f'both correct {quality["both_correct"]}/{quality["reviewed"]}. '
            f'{trial.get("decision_reason", "Qualification remains open.")} '
            'Independent recomputation completed; cleanup and recovery are recorded per trial. '
            'CPU evaluation responses are excluded from production saved-face counters. Tuning is still active.'
        )
        backend_charts.append(tuning_comparison(
            f'{trial["backend"]} · {trial["threads"]} threads · {trial["decision"]}',
            rates, 0, trial_y, 24, 7, "suffix: faces/min", description,
        ))
        # These published comparison links stay stable as new trial arms are added.
        backend_charts[-1]["id"] = trial["panel_id"]
    cpu_evidence = json.loads(Path(__file__).with_name("library-server-timing.json").read_text())
    if "cpu_quality_screen" in cpu_evidence:
        quality = cpu_evidence["cpu_quality_screen"]
        linux = cpu_evidence["cpu_linux_readiness"]
        evidence_y = max(panel["gridPos"]["y"] + panel["gridPos"]["h"] for panel in backend_charts)
        content = (
            "### CPU model quality and Linux compatibility\n\n"
            f'**{quality["model"]} · Mac CPU · {quality["decision"]}.** '
            f'Same 12 marked faces, separate age/action calls, {quality["threads"]} CPU threads. '
            f'Correct stage **{quality["stage_correct"]}/{quality["known_stages"]}**, '
            f'supported whole action **{quality["supported_actions"]}/{quality["reviewed_faces"]}**, '
            f'both **{quality["both_correct"]}/{quality["known_stages"]}**. '
            f'Invalid actions {quality["invalid_actions"]}; stage abstentions {quality["stage_abstentions"]}. '
            'Historical original-model reference: stage 21/40, action 35/48, both 16/40. '
            'The smaller model does not preserve quality.\n\n'
            f'**{linux["backend"]} · {linux["quota_percent"]}% CPU quota · one readiness face.** '
            f'Age call **{linux["age_s"]:.1f} s**, action call **{linux["action_s"]:.1f} s**. '
            'Both readings were supported. A second diagnostic reproduced the known age error, so the smaller model remains unqualified on Linux. '
            'The 27B Linux profile exceeded its 900 s diagnostic request bound. Keep zero CPU lanes for these tested Linux profiles; cleanup was verified.\n\n'
            '**New CPU production outputs: 0. CPU production lanes: 0.** '
            'Frozen evaluations do not count as library progress. Original-model Mac two-call testing continues; '
            'quality, aggregate workload gain, distinct peer budgets and independent publication/readback must pass before selection.'
        )
        backend_charts.append(_panel('text', 'CPU quality · Mac and still-fawn · no production selection', [],
                                     0, evidence_y, 24, 9,
                                     extra={'options': {'mode': 'markdown', 'content': content}}))
        backend_charts[-1]["id"] = 296
    chart_bottom = max(panel["gridPos"]["y"] + panel["gridPos"]["h"] for panel in backend_charts)
    shift(processing[charts_at:], chart_bottom - processing[charts_at]["gridPos"]["y"])
    processing[charts_at:charts_at] = backend_charts
    processing_height = max(panel["gridPos"]["y"] + panel["gridPos"]["h"] for panel in processing)
    # Move the shared progress row after allocating IDs so existing panel links still work.
    remaining = (reconciliation + shift(tuning, RECONCILIATION_HEIGHT)
                 + shift(audio, RECONCILIATION_HEIGHT + VIDEO_TUNING_HEIGHT)
                 + shift(all_panels, RECONCILIATION_HEIGHT + VIDEO_TUNING_HEIGHT + AUDIO_STORY_HEIGHT))
    recovery_height = max(p['gridPos']['y'] + p['gridPos']['h'] for p in recovery)
    return recovery + shift(processing + shift(remaining, processing_height), recovery_height)


def caption_recovery_panels():
    """Show the frozen missing-description cohort and its own private-ledger measurements."""
    base = 'knowledge_index_caption_recovery_assets'
    fresh = ' and on() (time() - max(knowledge_index_caption_recovery_snapshot_seconds) < 180)'
    done = f'sum(max by(state) ({base}{{state=~"verified|already_described"}}))'
    total = f'sum(max by(state) ({base}))'
    panels = [
        row("Basic-caption recovery · missing Immich descriptions", 0),
        stat("Assets with a caption in Immich", done + fresh, 0, 1, w=5, unit="locale",
             description="Saved captions read back on the original asset, including independently filled descriptions."),
        stat("Recovery complete", f'100 * {done} / {total}' + fresh, 5, 1, w=4, unit="percent", decimals=1),
        stat("Awaiting Immich readback", f'max({base}{{state="queued"}})' + fresh, 9, 1, w=5, unit="locale"),
        stat("Waiting for a caption", f'max({base}{{state="pending"}})' + fresh, 14, 1, w=5, unit="locale"),
        stat("Recovery errors", f'max({base}{{state="error"}})' + fresh, 19, 1, w=5, unit="locale", thresholds=RED_IF_POS),
        series("Basic-caption recovery by state", [(f'max by(state) ({base})' + fresh, '{{state}}')], 0, 5, w=12,h=7,
               description="One disposition per original asset in the frozen recovery ledger."),
        series("Recovery captions saved per minute by backend",
               [(f'max(knowledge_index_caption_recovery_saved_per_minute{{backend="{backend}"}})' + fresh, backend)
                for backend in ('RTX 3070','Mac Metal')],
               12, 5, w=12, h=7,
               description="Ledger answers saved in the last 15 minutes divided by 15. Includes reused answers with their original model timestamp."),
    ]
    # Dispatch alternates between backends, so the two live rates often coincide.
    panels[-1]["fieldConfig"]["overrides"] = [
        {"matcher":{"id":"byName","options":"RTX 3070"}, "properties":[
            {"id":"color","value":{"mode":"fixed","fixedColor":"orange"}},{"id":"custom.lineWidth","value":3}]},
        {"matcher":{"id":"byName","options":"Mac Metal"}, "properties":[
            {"id":"color","value":{"mode":"fixed","fixedColor":"blue"}},
            {"id":"custom.lineStyle","value":{"fill":"dash","dash":[8,8]}}]},
    ]
    tuning_notes = Path(__file__).with_name('caption-recovery') / 'tuning-results.md'
    panels.append(_panel('text', 'Basic-caption recovery · matched backend trials', [], 0, 12, 24, 15,
                         extra={'options': {'mode': 'markdown', 'content': tuning_notes.read_text().strip()}}))
    # Allocate these after the existing panels to preserve bookmarked IDs.
    panels.extend([
        stat("Exact saved captions", f'max({base}{{state="verified"}})' + fresh, 0, 27, w=6, unit="locale",
             description="Original Immich assets whose Knowledge Index caption matched the recovery ledger at readback."),
        stat("Other captions preserved", f'max({base}{{state="already_described"}})' + fresh, 6, 27, w=6, unit="locale",
             description="Assets with existing caption text that was retained during recovery."),
        stat("Publisher marked source removed", 'max(immich_sync_recovery_conflicts{reason="source_removed"})',
             12, 27, w=6, unit="locale", thresholds=RED_IF_POS,
             description="Live publisher count of recovery jobs blocked by catalog removal."),
        stat("Other publisher conflicts", 'max(immich_sync_recovery_conflicts{reason="other"})',
             18, 27, w=6, unit="locale", thresholds=RED_IF_POS),
    ])
    for panel in panels:
        if panel["type"] == "stat":
            panel["targets"][0].update(instant=True, range=False)
    return panels


def photo_processing_panels():
    """Give each processing stage the same operational and live tuning views."""
    selector = 'instance=~"$instance",stage=~"$photo_stage"'

    def counts(states):
        return (f'sum by(stage) (max by(stage,state) '
                f'(knowledge_index_photo_stage_items{{{selector},state=~"{states}"}}))')

    completed = counts("complete|reused")
    scope = counts(".*")
    remaining = counts("pending|running")
    age = f'time() - max by(stage) (knowledge_index_photo_stage_updated_timestamp_seconds{{{selector}}})'
    saved = f'knowledge_index_photo_stage_items{{{selector},state="complete"}}'
    counter = f'knowledge_index_photo_stage_completed_total{{{selector}}}'
    # Estimate slope across actual samples so a newly scraped stage does not
    # extrapolate a small fraction of its rate across an entire range.
    pace = (f'max by(stage) (clamp_min(deriv({saved}[15m]), 0) '
            f'and on(instance,stage) (changes({saved}[15m]) >= 2) '
            f'and on(instance,stage) (resets({counter}[15m]) == 0))')
    eta = (f'(({remaining}) / ({pace} > 0) or on(stage) (({remaining}) == 0)) '
           f'and on(stage) (({age}) < 180)')
    panel_set = [
        row("Photo processing · life stage + action per face, OCR and live tuning", 0),
        stat("Items complete or reused", completed, 0, 1, unit="locale", legend="{{stage}}",
             description="Each completed library face has a life stage and a visible action linked to its existing Immich face ID. The OCR stage counts photos checked for text, including photos with no text."),
        stat("Items queued or running", remaining, 4, 1, unit="locale", legend="{{stage}}"),
        stat("Stage completion", f'({completed}) / ({scope} > 0)', 8, 1,
             unit="percentunit", decimals=1, legend="{{stage}}",
             description="Complete and reused divided by the declared scope, including failed and withheld items."),
        stat("Failed or withheld", counts("failed|withheld"), 12, 1, unit="locale", legend="{{stage}}"),
        stat("Time to drain queue", eta, 16, 1, unit="s", legend="{{stage}}",
             description="Remaining work at the observed successful rate over up to 15 minutes. A positive queue needs fresh progress, two advances and a positive rate without a reset."),
        stat("Last progress report", age, 20, 1, unit="s", legend="{{stage}}",
             thresholds=[("green", None), ("orange", 180), ("red", 600)]),
        series("Queue and outcomes by stage",
               [(f'max by(stage,state) (knowledge_index_photo_stage_items{{{selector}}})',
                 "{{stage}} · {{state}}")], 0, 5, 12, 7, unit="locale"),
        series("Successful work per minute", [(f'{pace} * 60', "{{stage}}")],
               12, 5, 12, 7, decimals=1),
        series("Bottleneck timing by phase (p95)",
               [(f'max by(stage,phase) (knowledge_index_photo_stage_phase_p95_seconds{{{selector}}})',
                 "{{stage}} · {{phase}}")], 0, 12, 24, 7, unit="s",
               description="Compare queue, throughput and available phase timings before and after a tuning change. Missing phases have no reported timing."),
    ]
    for panel in panel_set:
        if panel["type"] != "row":
            panel["transformations"] = [{
                "id": "renameByRegex",
                "options": {"regex": "^library-face-observations(.*)$", "renamePattern": "Life stage + action per face$1"},
            }]
        if panel["type"] == "stat":
            panel["targets"][0].update(instant=True, range=False)
            panel["fieldConfig"]["defaults"]["noValue"] = "Awaiting telemetry"
    return panel_set


def photo_backend_panels(y):
    """Show committed inference results from each backend for the chosen stages."""
    saved = 'knowledge_index_photo_stage_backend_completed{instance=~"$instance",stage=~"$photo_stage"}'
    window = f'{saved}[15m]'
    pace = (f'max by(stage,backend) (clamp_min(deriv({window}), 0) '
            f'and (resets({window}) == 0)) * 60')
    legend = "{{stage}} · {{backend}}"
    face_result = ("Each saved library result links a life stage and a visible action to one existing Immich face ID. "
                   "For a new face, RTX gets both in one model call. Mac uses two calls. "
                   "Resumed work can reuse a previously saved stage or action.")
    panels = [
        series("Results saved per minute by backend (15 min)", [(pace, legend)], 0, y, 12, 7, decimals=1,
               description="Rate of new saves over the last 15 minutes. " + face_result),
        series("Results saved by backend", [(f'max by(stage,backend) ({saved})', legend)],
               12, y, 12, 7, unit="locale",
               description="New saves since the start of processing. Fully reused observations are excluded. " + face_result),
    ]
    for panel in panels:
        for backend, display in (("mac-metal", "Mac Metal"), ("rtx3070", "RTX 3070")):
            panel["fieldConfig"]["overrides"].append({
                "matcher": {"id": "byName", "options": "library-face-observations · " + backend},
                "properties": [{"id": "displayName", "value": display + " · life stage + action per face"}],
            })
    trial = json.loads((Path(__file__).parent / "library-backfill-tuning.json").read_text())
    for x, (backend, result) in enumerate(trial["backends"].items()):
        before, after = result["before"], result["selected"]
        rates = [(f'vector({arm["per_min"]})', f'{label} · {arm["lanes"]} lanes')
                 for label, arm in (("Matched before", before), ("Matched after", after))]
        alternate = result["more_lanes"]
        rates.append((f'vector({alternate["per_min"]})', f'Trial · {alternate["lanes"]} lanes (rejected)'))
        rates.extend((f'vector({value})', label) for label, value in
                     (("Live before", result["live_before"]), ("Live after", result["live_after"])))
        evidence = (f' Complete: {before["successful"]}/{before["attempts"]} before and '
                    f'{after["successful"]}/{after["attempts"]} after. Exact agreement with reviewed '
                    f'life stages: {before["reviewed_stage_exact"]}/{before["reviewed_attempts"]} before and '
                    f'{after["reviewed_stage_exact"]}/{after["reviewed_attempts"]} after. Visually supported actor/action '
                    f'readings: {before["supported_actor_actions"]}/{before["attempts"]} before and '
                    f'{after["supported_actor_actions"]}/{after["attempts"]} after.')
        durations = before["median_seconds"]
        timing = (f' Before tuning, median preview preparation took {durations["preview_seconds"]} s, '
                  f'life stage {durations["age_seconds"]} s and action {durations["action_seconds"]} s.')
        panels.append(tuning_comparison(
            f'Two-pass life stage + action per face · {backend} before and after', rates, x * 12, y + 7, 12, 7,
            "suffix: faces/min", result["decision"] + evidence + timing + " " + trial["method"]))
    paired = json.loads((Path(__file__).parent / "library-pass-comparison.json").read_text())
    quality = ["| Backend | Model calls per face | Completed | Exact life stage | Saved with supported action | Both correct |",
               "|---|---:|---:|---:|---:|---:|"]
    for x, (backend, result) in enumerate(paired["backends"].items()):
        rates = []
        for calls, arm in ((2, result["two_pass"]), (1, result["one_pass"])):
            rates.append((f'vector({arm["per_min"]})', f'{calls} {"call" if calls == 1 else "calls"} per face'))
            total = arm["attempts"]
            reviewed = arm["reviewed_attempts"]
            quality.append(f'| {backend} | {calls} | {arm["successful"]}/{total} | '
                           f'{arm["reviewed_stage_exact"]}/{reviewed} | {arm["supported_actions"]}/{total} | '
                           f'{arm["both_correct"]}/{reviewed} |')
        panels.append(tuning_comparison(
            f'Life stage + action per face · {backend} · two calls vs one', rates, x * 12, y + 14, 12, 6,
            "suffix: faces/min", paired["method"] + " " + result["decision"]))
    quality.extend(["", paired["method"], "", paired["decision"]])
    panels.append(_panel("text", "Life stage + action per face · quality comparison", [], 0, y + 20, 24, 8,
                         extra={"options": {"mode": "markdown", "content": "\n".join(quality)}}))
    return panels


def photo_server_timing_panel(y):
    sample = json.loads(Path(__file__).with_name("library-server-timing.json").read_text())
    mac, rtx, sizes = sample["mac"], sample["rtx"], sample["size_trial"]
    phases = [
        ("Mac · before second output token (estimated)", mac["median_before_second_s"]),
        ("Mac · later decoding (estimated)", mac["median_later_decode_s"]),
        ("RTX · input evaluation", rtx["median_input_s"]),
        ("RTX · output generation", rtx["median_decode_s"]),
    ]
    description = (
        f'Median seconds per request, {sample["start_utc"]} to {sample["end_utc"]}. '
        f'Mac timing uses {mac["closed_requests"]} observed slot transitions. '
        f'RTX timing uses {rtx["closed_requests"]} complete runner records. Admission wait is unmeasured. '
        f'Input-size test on {sizes["photos"]} reviewed faces with the close-up preserved: '
        f'{sizes["before_input_units"]:,} → {sizes["candidate_input_units"]:,} input tokens across both Mac calls. '
        f'{sizes["small_faces_below_minimum"]} of {sizes["small_faces_tested"]} separately sampled small faces '
        f'fell below {sizes["minimum_marked_face_px"]} px in the marked scene. Production keeps the original size.'
    )
    trial = sample.get("guarded_generation_trial")
    if trial:
        description += (
            " Generated-answer trial rejected: RTX reviewed stage matches 6/10 → 5/10 "
            "and supported actions 10/12 → 9/12, median 10.28 → 9.49 s. "
            "Mac stopped after four pairs: stage matches 3/4 → 3/4, actions 3/4 → 2/4, "
            "median 33.77 → 35.19 s. A further unpaired Mac reading is excluded. "
            "These are queued client request times during production. No production resize was deployed."
        )
    cpu = sample.get("cpu_diagnostic")
    if cpu:
        description += (
            f' CPU diagnostic: {cpu["threads"]} threads, {cpu["lanes"]} lane, one reviewed face. '
            f'Correct stage and supported action. {cpu["elapsed_with_startup_s"]} s including startup, '
            f'{cpu["input_s"]} s input and {cpu["generation_s"]} s generation. '
            'Server cleanup verified. Sustained quality and peer qualification remain open.'
        )
    return tuning_comparison(
        "Life stage + action · where server time went (Nov 27 sample)",
        [(f"vector({seconds})", label) for label, seconds in phases], 0, y, 24, 7, "s", description,
    )


def tuning_story(content):
    return _panel('text', 'What changed and why', [], 0, 1, 24, 4,
                  extra={'options': {'mode': 'markdown', 'content': content}})


def tuning_comparison(title, data, x, y, w, h, unit, description, maximum=None):
    panel = _panel('bargauge', title, data, x, y, w, h, unit=unit, decimals=2,
                   extra={'options': {'orientation': 'horizontal', 'displayMode': 'gradient',
                                      'reduceOptions': {'calcs': ['lastNotNull']}}},
                   description=description)
    for target in panel['targets']:
        target.update(instant=True, range=False)
    panel['fieldConfig']['defaults']['min'] = 0
    if maximum is not None:
        panel['fieldConfig']['defaults']['max'] = maximum
    return panel


def life_stage_tuning_panels():
    """Apply the video tuning row pattern to local photo life-stage processing."""
    trials = json.loads((Path(__file__).parent / "life-stage-tuning-results.json").read_text())
    slot_trials = trials.get("slot_trials")
    slot_story = trials["decision"]
    if slot_trials:
        passes = slot_trials.get("passes", 1)
        retained = next(t for t in slot_trials["trials"] if t["slots"] == slot_trials["selected_slots"])
        slot_story = (
            f"**Matched capacity trial:** Retained **{retained['slots']} RTX slots** at "
            f"**{retained['photos_per_minute']} photos/min**. "
            f"All {retained['valid']} selected responses passed validation. "
            + " ".join(t["failure"] for t in slot_trials["trials"] if t.get("failure"))
        )
        if trials.get("cold_slot_trials"):
            slot_story += (
                " The first three- and four-request trials timed out during model startup."
                f" The timed runs began after a {slot_trials['warmup_seconds']:.0f}-second warm-up."
            )
    # This checkpoint reports both GPU backends from the same collector host.
    scope = 'stage="life-stage"'
    saved = f'knowledge_index_photo_stage_backend_completed{{{scope}}}'

    def backend_metric(name):
        return f'{saved[:-1]},backend="{name}"}}'

    def backend_pace(name):
        metric = backend_metric(name)
        return (f'max(clamp_min(deriv({metric}[15m]), 0) '
                f'and on(instance,stage,backend) (changes({metric}[15m]) >= 2) '
                f'and on(instance,stage,backend) (resets({metric}[15m]) == 0)) * 60')

    mac, rtx = backend_pace("mac-metal"), backend_pace("rtx3070")
    panels = [row("Life-stage tuning · Mac and RTX", 0)]
    panels.append(tuning_story(
        "**Before:** Mac-only life-stage queue sustained 15.9–16.1 photos/min in two 10-minute windows.\n\n"
        "**After:** The Mac and RTX share the same checkpoint. The RTX request now uses constrained JSON and "
        "disables thinking. The Mac can pick up rejected responses. Live rates count each completed asset once.\n\n"
        f"**RTX concurrency:** One request saved {trials['before']['rtx_per_minute']:.1f} photos/min. "
        f"Two requests saved {trials['after']['rtx_per_minute']:.1f} photos/min in the measured window. "
        + slot_story
    ))
    panels.extend([
        tuning_comparison("RTX · matched life-stage request latency",
                          [("vector(7.45)", "Before · generic JSON"), ("vector(4.16)", "After · tuned schema")],
                          0, 5, 12, 8, "s", "Median wall time for the same five photos. All baseline RTX responses were invalid.", 23),
        tuning_comparison("Mac · matched life-stage request latency",
                          [("vector(20.09)", "Saved Mac pilot baseline")],
                          12, 5, 12, 8, "s", "Median request time from the four-worker Mac pilot. Use the live rate for backend capacity.", 23),
        stat("Before · Mac-only photos / min", "vector(16)", 0, 13, w=6, decimals=1,
             description="Mean throughput across the two measured Mac-only 10-minute windows."),
        stat("After · combined photos / min", f'({mac}) + ({rtx})', 6, 13, w=6, decimals=1,
             description="Both backends need two observed count advances for a combined live estimate."),
        stat("RTX · matched valid JSON", "vector(100)", 12, 13, w=6, unit="percent",
             description="0/5 before and 5/5 after changing the RTX request. Valid JSON supports parsing."),
        stat("Matched primary life stage", "vector(4)", 18, 13, w=6, unit="locale",
             description="Four of five matched the Mac's primary stage; the fifth was an adjacent life stage."),
        series("Life-stage throughput by backend",
               [(mac, "Mac GPU"), (rtx, "RTX 3070"), (f'({mac}) + ({rtx})', "Combined"), ("vector(16)", "Before · Mac only")],
               0, 17, 12, 8, decimals=1, description="New records per minute based on observed saved-count changes."),
        series("Life-stage results saved by backend",
               [(f'max({backend_metric("mac-metal")})', "Mac GPU"),
                (f'max({backend_metric("rtx3070")})', "RTX 3070")],
               12, 17, 12, 8, unit="locale", description="Persisted model results. Reused album results are accounted for separately."),
        tuning_comparison("Bottleneck · model versus preview preparation",
                          [("vector(22.44)", "Model request p95"), ("vector(0.132)", "Fetch and prepare preview p95")],
                          0, 25, 24, 7, "s", "Same 12-photo concurrent Mac sample. The RTX was added after this phase measurement."),
    ])
    comparison_note = (
        f"Two {trials['window_seconds']}-second live windows on the same queue. The Mac ran concurrently "
        "and both RTX settings used the same prompt and validation."
    )
    for title, field, x, y, unit in (
        ("RTX · one vs two requests", "rtx_per_minute", 0, 32, "suffix: photos/min"),
        ("Combined · one vs two RTX requests", "combined_per_minute", 12, 32, "suffix: photos/min"),
        ("RTX · request latency at one and two slots", "rtx_median_seconds", 0, 39, "s"),
    ):
        values = [(f'vector({trials[side][field]})', label) for side, label in (
            ("before", "Before · one RTX request"), ("after", "After · two RTX requests")
        )]
        panels.append(tuning_comparison(title, values, x, y, 12 if y == 32 else 24, 7, unit, comparison_note))
    if slot_trials:
        note = (f"Identical {slot_trials['sample_size']}-photo target sample, same prompt and validation. "
                "The release check requires valid results, stage agreement or a reported alternative, and full GPU residency.")
        if passes == 2:
            note += " The runs used one warmed runner, with concurrency tested in forward and reverse order."
            note += " Each setting processed the same sample twice. Slots are concurrent requests sent by the worker."

        def slot_label(trial):
            slots = trial["slots"]
            if slots == slot_trials["selected_slots"]:
                return f"After · {slots} slots · retained"
            if slots == 2 and trial["passed"]:
                return "Before · 2 slots"
            if trial["passed"]:
                return f"Trial · {slots} slots"
            return f"{slots} slots · " + ("timed out" if trial.get("failure") else "failed checks")

        for title, field, x, unit in (
            ("RTX · matched capacity at 2, 3 and 4 slots", "photos_per_minute", 0, "suffix: photos/min"),
            ("RTX · median latency at 2, 3 and 4 slots", "median_seconds", 12, "s"),
        ):
            values = [
                (f'vector({trial[field]})', slot_label(trial))
                for trial in slot_trials["trials"]
                if trial[field] is not None
            ]
            panels.append(tuning_comparison(title, values, x, 46, 12, 7, unit, note))
    for panel in panels:
        if panel["type"] != "timeseries":
            continue
        panel["interval"] = "15s"
        panel["options"]["legend"]["calcs"] = ["lastNotNull"]
        panel["fieldConfig"]["overrides"].append({
            "matcher": {"id": "byName", "options": "RTX 3070"},
            "properties": [
                {"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}},
                {"id": "custom.lineWidth", "value": 3},
                {"id": "custom.showPoints", "value": "always"},
                {"id": "custom.pointSize", "value": 5},
            ],
        })
    return panels


def video_tuning_panels():
    """Present the measured tradeoff and the resulting live video throughput."""
    evidence = json.loads((Path(__file__).parent/'video-tuning/results.json').read_text())
    p = [row('Video tuning · preserve the story', 0)]
    narrative = evidence.get('story', 'Matched video trials are in progress.')
    p.append(tuning_story(narrative))
    trial_max = int(max((r['successful_per_minute'] for r in evidence.get('trials', [])
                         if r.get('successful_per_minute') is not None), default=1) * 1.1) + 1
    for backend, x, title in (('rtx', 0, 'RTX · matched video trials'), ('mac', 12, 'Mac · matched video trials')):
        rows = [r for r in evidence.get('trials', []) if r['backend'] == backend and r.get('successful_per_minute') is not None]
        exprs = [('vector('+str(r['successful_per_minute'])+')', r.get('label', r['profile'])) for r in rows]
        if not exprs:
            exprs = [('vector(0)', 'Trials in progress')]
        panel = tuning_comparison(title, exprs, x, 5, 12, 8, 'suffix: clips/min',
                                  'Private matched sample; successful caption-cache-bypassed model requests divided by trial wall time. '
                                  'Each backend is tested separately. '+evidence.get('method', ''), trial_max)
        p.append(panel)
    scope = '{instance=~"$instance",enricher=~"$pipeline_enricher"}'
    p += [stat('Live videos / min · 10m average', 'sum(rate(media_pipeline_video_saved_total'+scope+'[10m])) * 60',
               0, 13, w=6, unit='suffix: clips/min', decimals=2,
               description='Successful video rows saved to production Parquet in ten minutes, including caption-cache reuse.'),
          stat('Source video minutes / minute', 'sum(rate(media_pipeline_video_saved_seconds_total'+scope+'[10m]))',
               6, 13, w=6, decimals=2,
               description='Minutes of source video covered per wall-clock minute. Counts the source duration, not seconds watched; summaries use sampled frames.'),
          stat('Video attempts failing', '100 * sum(rate(media_pipeline_persisted_items_total'+
               '{instance=~"$instance",kind="video",status="error"}[10m])) / sum(rate(media_pipeline_persisted_items_total'+
               '{instance=~"$instance",kind="video"}[10m]))', 12, 13, w=6, unit='percent', decimals=1,
               description='Persisted video errors divided by all persisted video attempts; includes decoder and model failures.'),
          stat('Story review · paired checks', 'vector('+str(evidence.get('reviewed', 0))+')', 18, 13, w=6, unit='locale',
               description=evidence.get('quality', 'Review pending.'))]
    p += [series('Live video throughput by backend',
                [('sum(rate(media_pipeline_video_saved_total'+scope[:-1]+',backend="'+backend+'"}[10m])) * 60', label)
                 for backend, label in (('primary', 'RTX 3070'), ('metal', 'Mac GPU'), ('cache', 'Caption cache'))],
                0, 17, 12, 8, decimals=2, description='Saved production videos per minute. Cache reuse is shown separately from GPU inference.'),
          series('Video work covered · inference only',
                [('sum(rate(media_pipeline_video_saved_seconds_total'+scope[:-1]+',backend="'+backend+'"}[10m]))', label)
                 for backend, label in (('primary', 'RTX 3070'), ('metal', 'Mac GPU'))],
                12, 17, 12, 8, decimals=2,
                description='Source-video minutes covered per minute by RTX/Mac inference, excluding cache reuse. Longer or static clips can raise this without improving story quality.')]
    for title, key, x, unit in (
            ('RTX · matched trial gain', 'rtx_gain_percent', 0, 'percent'),
            ('Mac · matched trial gain', 'mac_gain_percent', 6, 'percent'),
            ('Model input tokens reduced', 'token_reduction_percent', 12, 'percent'),
            ('Matched JSON responses valid', 'valid_percent', 18, 'percent')):
        p.append(stat(title, 'vector('+str(evidence.get(key, 0))+')', x, 25, w=6, unit=unit, decimals=1,
                      description=('JSON parsing and a nonempty summary; not factual accuracy. ' if key == 'valid_percent' else '')
                      + evidence.get('method', 'Trials in progress.')))
    decode = evidence.get('decode', {})
    comparisons = [('vector('+str(r['mean_seconds'])+')', r['label']) for r in decode.get('trials', [])]
    if comparisons:
        panel = _panel('bargauge', 'Read / decode · same eight frames', comparisons, 0, 30, 16, 6, unit='s', decimals=2,
                       extra={'options': {'orientation': 'horizontal', 'displayMode': 'gradient',
                                          'reduceOptions': {'calcs': ['lastNotNull']}}},
                       description=decode.get('method', ''))
        for target in panel['targets']:
            target.update(instant=True, range=False)
        panel['fieldConfig']['defaults']['min'] = 0
        p.append(panel)
        p.append(stat('Compared frame pixels preserved', 'vector('+str(decode['identical_percent'])+')',
                      16, 30, w=8, h=6, unit='percent', decimals=0,
                      description=decode.get('method', '')))
    shift(p[1:], 5)
    def video_count(state):
        return ('max(knowledge_index_caption_completion{instance=~"$instance",kind="video",'
                'model="local",scope="deduplicated",state="'+state+'"}'
                ' and on(instance,job) (knowledge_index_exporter_success'+INST+' == 1)'
                ' and on(instance,job) (time() - knowledge_index_last_run_timestamp_seconds'+INST+' < 900))')
    done, remaining = video_count('complete'), video_count('remaining')
    total = '('+done+' + '+remaining+')'
    for title, expr, x, unit in (
            ('Videos complete · local GPUs', done, 0, 'locale'),
            ('Videos remaining · local GPUs', remaining, 6, 'locale'),
            ('Video completion · local GPUs', '100 * '+done+' / ('+total+' > 0)', 12, 'percent'),
            ('Videos in library · deduped est.', total, 18, 'locale')):
        panel = stat(title, expr, x, 1, w=6, h=5, unit=unit,
                     decimals=1 if unit == 'percent' else 0,
                     description='Current local RTX/Mac caption coverage, not Luna or reconciliation. '
                     'One retained representative per presumed-copy group (filename and byte size, not content hash). '
                     'Updated every five minutes; unresolved input failures remain in remaining.')
        panel['targets'][0].update(instant=True, range=False)
        panel['fieldConfig']['defaults']['noValue'] = 'Awaiting fresh data'
        p.append(panel)
    return p


def audio_story_panels():
    """Speech makes the event understandable; retain visual and spoken provenance."""
    evidence_path=Path(__file__).parent/'audio-story/results.json'
    evidence=json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    def jobs(stage,state):
        return 'sum(knowledge_index_audio_jobs{instance=~"$instance",stage="'+stage+'",state=~"'+state+'"})'
    done=jobs('audio','speech|no_speech|no_audio|uncertain_speech|skipped')
    eligible='max(knowledge_index_audio_eligible'+INST+')'
    remaining=jobs('audio','pending|inflight|error')
    pace='sum(rate(knowledge_index_audio_finished_total'+INST+'[10m]))'
    eta='(('+remaining+') / ('+pace+' > 0)) and on() (time() - max(knowledge_index_audio_updated_timestamp_seconds'+INST+') < 120)'
    p=[row('Video stories · speech and context',0),
       _panel('text','From silent frames to an event story',[],0,1,24,3,extra={'options':{'mode':'markdown','content':evidence.get('story','Whisper adds timestamped speech to saved visual captions. No repeat vision inference. Uncertain speech is withheld; original captions remain available.')}})]
    for title,expr,x in [
      ('Videos with usable speech',jobs('audio','speech'),0),
      ('No speech detected',jobs('audio','no_speech'),4),
      ('No audio track',jobs('audio','no_audio'),8),
      ('Uncertain speech withheld',jobs('audio','uncertain_speech'),12),
      ('Audio attempts exhausted',jobs('audio','skipped'),16),
      ('Stories saved',jobs('story','ok'),20)]:
        p.append(stat(title,expr,x,4,w=4,unit='locale',description='Deduped estimated groups with saved visual captions. Speech confidence is automatic, not verified accuracy. Stories retain the visual caption when speech is absent or unusable.'))
    for title,expr,x,unit in [
      ('Videos ready for audio',eligible,0,'locale'),
      ('Audio checks remaining',remaining,4,'locale'),
      ('Audio pass complete · ready videos','100 * ('+done+') / ('+eligible+' > 0)',8,'percent'),
      ('Awaiting any visual caption','max(knowledge_index_audio_library_videos'+INST+') - '+eligible,12,'locale'),
      ('Story merge remaining',jobs('story','pending|inflight|error'),16,'locale'),
      ('Audio queue ETA · ready videos',eta,20,'s')]:
        p.append(stat(title,expr,x,8,w=4,unit=unit,description='Uses an existing local or Luna visual caption, preferring local when available. The queue grows as captions finish; discovery runs every five minutes. ETA uses successful audio checks over ten minutes and excludes videos still awaiting vision; skipped checks are separately visible.'))
    p += [series('Audio checked per minute by worker',
           [('sum(rate(knowledge_index_audio_finished_total{instance=~"$instance",backend="'+backend+'"}[10m])) * 60',label)
            for backend,label in [('mac','Mac Metal'),('cpu','still-fawn CPU'),('rtx','RTX CUDA'),('pve','PVE CPU')]],0,12,12,8),
          series('Stories saved and speech found',[(jobs('story','ok'),'Stories saved'),(jobs('audio','speech'),'Usable speech'),(jobs('audio','uncertain_speech'),'Speech withheld')],12,12,12,8)]
    comparisons=[('vector('+str(r['realtime_multiple'])+')',r['backend']) for r in evidence.get('trials',[]) if r['beam']==1 and r['clips']==7]
    if comparisons:
        panel=_panel('bargauge','Whisper · matched audio processing speed',comparisons,0,20,12,6,unit='suffix: x realtime',decimals=2,
          extra={'options':{'orientation':'horizontal','displayMode':'gradient','reduceOptions':{'calcs':['lastNotNull']}}},description=evidence.get('method',''))
        for target in panel['targets']:target.update(instant=True,range=False)
        p.append(panel)
    p.append(_panel('text','Why this production split',[],12,20,12,6,extra={'options':{'mode':'markdown','content':evidence.get('decision','Mac Metal and spare CPU transcribe independently. RTX trials finish before its reserved GPU share returns to Immich search.')}}))
    p += [stat('Audio worker report age','time() - max(knowledge_index_audio_updated_timestamp_seconds'+INST+')',0,26,w=6,unit='s'),
          stat('New visual-caption scan age','time() - max(knowledge_index_audio_scan_timestamp_seconds'+INST+')',6,26,w=6,unit='s'),
          stat('Story merge speed','sum(rate(knowledge_index_audio_stories_saved_total'+INST+'[10m])) * 60',12,26,w=6,unit='suffix: stories/min'),
          stat('Audio failures · last 10m','sum(increase(knowledge_index_audio_errors_total'+INST+'[10m]))',18,26,w=6,unit='locale')]
    p += [stat('Waiting for Codex translation','max(knowledge_index_audio_translation_waiting'+INST+')',0,30,w=4,unit='locale',description='Non-English speech is kept for a capable translator; it is not turned into guessed English dialogue. Raw timed speech and original visual captions are preserved.'),
          stat('Codex translation route ready','max(knowledge_index_audio_translation_ready'+INST+')',4,30,w=4,mappings={'0':{'text':'Waiting / disabled','color':'orange'},'1':{'text':'Ready','color':'green'}},description='Translation requires an explicitly enabled and healthy text-only route. Local Whisper audio checks continue independently.')]
    p += [stat('Codex text checks complete','sum(knowledge_index_audio_codex_requests{instance=~"$instance",state="ok"})',8,30,w=4,unit='locale',description='Successful text assessments, including pilot checks. Unclear/incidental speech may be withheld. Production story completion is shown separately under Stories saved.'),
          stat('Codex active / unknown','sum(knowledge_index_audio_codex_requests{instance=~"$instance",state=~"sent|unknown"})',12,30,w=4,unit='locale',description='Unresolved results retain their cost reservation and are not blindly resubmitted.'),
          stat('Translation estimate + holds','max(knowledge_index_audio_codex_estimated_usd'+INST+')',16,30,w=4,unit='currencyUSD',decimals=3,description='Separate text-translation API-equivalent estimate, not actual account usage. Cap $10; unresolved calls retain $0.025.'),
          stat('Translation estimate remaining','10 - max(knowledge_index_audio_codex_estimated_usd'+INST+')',20,30,w=4,unit='currencyUSD',decimals=2)]
    return p


def caption_completion_panels():
    """One caption can cover presumed copies; keep model and media scopes visible."""
    fresh = (' and on(instance,job) (knowledge_index_exporter_success' + INST + ' == 1) '
             'and on(instance,job) (time() - knowledge_index_last_run_timestamp_seconds' + INST + ' < 900)')
    note = ("Photos and videos shown separately. A successful caption on any matching copy covers the group. "
            "Dedup uses the existing assumption: album files with the same filename and byte size as a year-folder file "
            "are copies (not verified by content hash). Separate year-folder files are retained. "
            "Current path and byte size must match the saved result. Updated every five minutes. ")
    panels = []
    for x, model, label in ((0, 'local', 'Local GPU'), (8, 'luna', 'Luna'), (16, 'either', 'Either model')):
        for y, scope, title in ((5, 'deduplicated', 'deduped complete (est.)'),
                                (10, 'including_copies', 'files covered incl. copies')):
            expr = ('max by(kind) (knowledge_index_caption_completion{instance=~"$instance",'
                    f'model="{model}",scope="{scope}",state="complete"}}' + fresh + ')')
            panel = stat(label + ' · ' + title, expr, x, y, w=8, h=5, unit='locale',
                         legend='{{kind}}', extra_opts={'textMode': 'value_and_name', 'orientation': 'horizontal'},
                         description=note + ('Counts one retained representative per group.' if scope == 'deduplicated'
                         else 'Counts every file represented by a completed group, even if only one copy was described. This is coverage, not model calls.'))
            panel['targets'][0].update(instant=True, range=False)
            panel['fieldConfig']['defaults']['noValue'] = 'Awaiting fresh data'
            panels.append(panel)
    return panels


def reconciliation_panels():
    """Current input counts and critical-only review, with separate worker throughput."""
    def jobs(state):
        return f'sum(max by(state) (knowledge_index_reconciliation_jobs{{instance=~"$instance",state=~"{state}"}}))'
    def risk(level):
        return f'max(knowledge_index_reconciliation_risk{{instance=~"$instance",risk="{level}"}})'
    pace='sum(max by(runner) (rate(knowledge_index_reconciliation_runner_finished_total'+INST+'[5m])))'
    remaining=jobs('pending|reserved|sent')
    fresh='(time() - max(knowledge_index_reconciliation_updated_timestamp_seconds'+INST+') < 180)'
    unblocked='(max(knowledge_index_reconciliation_blocked'+INST+') == 0)'
    no_unknown=f'({jobs("unknown")} == 0)'
    eta=(f'((({remaining}) / ({pace} > 0)) and on() ({remaining} > 0) and on() {unblocked} '
         f'and on() {fresh} or ({remaining} == 0)) and on() {no_unknown}')
    finish=f'((time() + (({eta}) > 0)) * 1000) or (({eta}) == 0)'
    percent=f'100 * ({jobs("ok|skipped")}) / ({jobs("pending|reserved|sent|ok|skipped|unknown")} > 0)'
    p=[row('Summary reconciliation · Luna',0),
       stat('Reconciled summaries',jobs('ok'),0,1,unit='locale',description='Successful current revisions among discovered local/Luna pairs, not whole-library caption coverage. New pairs are discovered every five minutes. Earlier revisions remain in history.'),
       stat('Ready pairs still to reconcile',jobs('pending|reserved|sent'),4,1,unit='locale',description='Pending and active items with both local and Luna captions. New pairs join automatically as local descriptions arrive. Prior successes and skipped items are preserved.'),
       stat('Critical reviews for you',risk('critical'),8,1,unit='locale',thresholds=RED_IF_POS,
            description='Only material contradictions about the main person or an important life, family or work event that cannot safely be omitted. Minor details and unknown background people never require review.'),
       stat('Minor differences handled',risk('low'),12,1,unit='locale',
            description='Uncertain minor details were omitted or generalized automatically. These are not waiting for human review.'),
       stat('Skipped responses',jobs('skipped'),16,1,unit='locale',thresholds=[('text',None)],
            description='Isolated unusable responses are skipped without retrying or stopping the queue. No action required from you; originals remain intact.'),
       stat('Last progress report', 'time() - max(knowledge_index_reconciliation_updated_timestamp_seconds'+INST+')',20,1,unit='s',
            thresholds=[('green',None),('orange',180),('red',600)],description='Age of the most recent aggregate publication. A stale report does not prove either worker is running.'),
       series('Reconciliation progress',[(jobs('ok'),'Reconciled'),(jobs('pending|reserved|sent'),'Remaining'),(jobs('skipped'),'Skipped')],0,5,12,7,
              description='Current revisions only, one row per file. New policy reassessments move affected results back to pending; older results remain preserved.'),
       series('Reconciliations saved per minute',[
           ('max by(runner) (rate(knowledge_index_reconciliation_runner_finished_total'+INST+'[$__rate_interval])) * 60','{{runner}}')],12,5,12,7,decimals=1,
              description='Luna requests are submitted by still-fawn and the Mac. These are cloud text-only reconciliations, not local GPU inference. Counts completed revisions, including intentional reassessments.'),
       stat('Worker safety check', 'max(knowledge_index_reconciliation_blocked'+INST+')',0,12,w=8,
            mappings={'0':{'text':'No safety block','color':'green'},'1':{'text':'Paused — check worker','color':'orange'}},
            description='Authentication, rate-limit or usage-overrun protections pause new submissions. No safety block does not mean a worker is online or budget is available; check report age, saved/min and Luna budget available.'),
       stat('Reconciliation usage estimate', 'max(knowledge_index_reconciliation_known_usage_usd'+INST+')',8,12,w=8,unit='currencyUSD',decimals=3,
            description='Reported token usage valued at Luna API rates, including failed answers with usage and prior revisions. This is not an invoice. Excludes temporary holds and the earlier caption campaign.'),
       stat('Reserved or unreported usage', 'max(knowledge_index_reconciliation_held_usd'+INST+')',16,12,w=8,unit='currencyUSD',decimals=2,
            description='Temporary reservations for in-flight requests plus retained holds for skipped requests without usage. Released when known usage is recorded; not actual spending.'),
       series('Review decisions over time',[(risk('critical'),'Critical — needs you'),(risk('low'),'Minor — handled automatically')],0,16,24,7,
              description='Only current completed results. Aliases confirmed by you are treated as the same person. Earlier broad review flags are reassessed under the critical-only policy.')]
    shift(p[1:],4)
    estimates=[
        stat('Available pairs processed',percent,0,1,w=6,unit='percent',decimals=1,
             description='Successful or deliberately skipped files divided by discovered local/Luna pairs. New pairs are added automatically every five minutes as local captions arrive, so this percentage can fall. 100% means caught up with discovered pairs, not both models complete over the whole library. Skipped files count as processed, not successful summaries.'),
        stat('Current speed · combined',f'({pace}) * 60 and on() {fresh}',6,1,w=6,decimals=1,unit='suffix: summaries/min',
             description='Combined successful completions per minute across still-fawn and Mac, averaged over the last five minutes.'),
        stat('Estimated time remaining',eta,12,1,w=6,unit='s',decimals=0,
             description='Pending and in-flight files divided by combined five-minute completion rate. Assumes similar work and continued uptime. Hidden when blocked, reporting is over three minutes old, or no positive speed is measured.'),
        stat('Estimated finish time',finish,18,1,w=6,unit='dateTimeAsLocal',
             description='Current time plus the estimated duration, shown in browser local time. This is an estimate, not a deadline.')]
    for panel in estimates[-2:]:
        panel['fieldConfig']['defaults']['mappings']=[{'type':'value','options':{'0':{'text':'Caught up','color':'green'}}}]
    for panel,x,w in zip(estimates,(0,4,9,14),(4,5,5,5)):
        panel['gridPos'].update(x=x,w=w)
    remaining_cost=stat('Remaining cost · observed',
        f'({remaining}) * {OBSERVED_RECONCILIATION_USD_PER_SUMMARY}',19,1,w=5,
        unit='currencyUSD',decimals=2,
        description='Last reported pending and in-flight files × observed $0.869 per 1,000 successful reconciliations. Skipped files are excluded. Assumes similar work and overhead; this forecasts plan usage, not an invoice. Account usage readings remain only in the private local database. Token-based usage and reservation accounting below are separate.')
    p[1:1]=estimates
    p.insert(5,remaining_cost)
    for panel in p:
        if panel.get('title') == 'Last progress report':
            panel['title'] = 'Progress / new-pair check age'
            panel['targets'][0]['legendFormat'] = 'Progress report'
            panel['targets'].append(dict(refId='B',
                expr='time() - max(knowledge_index_reconciliation_discovery_timestamp_seconds'+INST+')',
                legendFormat='New pairs checked',instant=True,range=False))
            panel['options']['textMode'] = 'value_and_name'
            panel['description'] = 'Time since progress publication and since the last successful scan for new local/Luna pairs. Discovery runs at most every five minutes across both runners. Old successes and skipped items are not resubmitted.'
        if panel['type']=='stat':
            panel['targets'][0].update(instant=True,range=False)
            panel['fieldConfig']['defaults']['noValue']='No recent data'
        elif panel['type']=='timeseries':
            panel['fieldConfig']['defaults']['custom']={'drawStyle':'line','lineInterpolation':'linear','lineWidth':2,'fillOpacity':0,'showPoints':'never','spanNulls':False}
    for panel in estimates[-2:]:
        panel['fieldConfig']['defaults']['noValue']='Paused / no estimate'
    return p


def immich_face_panels():
    def result(kind):
        return f'max(photo_immich_face_reconciliation{{instance=~"$instance",result="{kind}"}})'
    return [row("Immich face reconciliation", 0),
            series("Imported names and remaining review", [
                (result("imported"), "Faces named from Immich"),
                (result("unreviewed"), "Unnamed current faces")],
                0, 1, 12, 7, description="Counts after the last successful refresh. Names require an unambiguous match on the same photo. Local reviews and rejections are preserved."),
            stat("Immich context refresh age", "time()-max(photo_immich_context_timestamp_seconds"+INST+")",
                 12, 1, w=6, unit="s", thresholds=[("green",None),("orange",2100),("red",4200)]),
            stat("Names saved last refresh", result("applied"), 18, 1, w=6)]


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
        (5, "Model request", "green"), (6, "Parsing answer", "light-purple"), (7, "Writing Parquet", "orange"),
        (8, "Finished", "dark-green"), (9, "Failed", "red")]}
    p = [row("Pipeline bottlenecks", 0)]
    p += [stat("Worker stage", current, 0, 1, w=6, mappings=states, legend="{{instance}} / {{enricher}}"),
          stat("Time in current stage", '(time() - media_pipeline_stage_started_timestamp_seconds' + sel + ') and (' + heartbeat + ' < 60) and (media_pipeline_running' + sel + ' == 1)',
               6, 1, w=6, unit="s", legend="{{instance}} / {{enricher}}"),
          stat("Worker telemetry age", heartbeat, 12, 1, w=6, unit="s", thresholds=[("green", None), ("orange", 30), ("red", 60)],
               description="Published every 5 s by the instrumented worker. Missing data means it has not published yet. After 60 s, the state becomes unknown rather than claiming it is still busy."),
          stat("Model requests in flight", 'sum by(enricher) (media_pipeline_in_flight' + sel[:-1] + ',stage="inference"} and on(instance,job,enricher) (' + heartbeat + ' < 60))',
               18, 1, w=6, legend="{{enricher}}", description="Requests submitted by the summary worker. Ollama may be processing or queueing them.")]
    graph = _panel("nodeGraph", "Value stream map", [], 0, 5, 24, 10,
                   description="Share of measured operation time by stage in the rate window. Concurrent stages each contribute time. Inference includes transport, server wait and model execution. Photo path skips transcription; parse loops to decode until the batch is saved. Edges show control flow.")
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
    graph["targets"][0]["expr"] += ' or ' + node('time()-max(photo_immich_context_timestamp_seconds'+INST+')','immich_metadata','Immich context refresh age (seconds)')
    graph["targets"][0]["expr"] += ' or ' + node('max(photo_immich_face_reconciliation{instance=~"$instance",result="imported"})','immich_named_faces','Faces named from Immich')
    graph["targets"][0]["expr"] += ' or ' + node('time()-min(photo_snapshot_captured_timestamp_seconds'+INST+')','photo_analytics','DuckDB snapshot age (seconds)')
    graph["targets"][0]["expr"] += ' or ' + node('histogram_quantile(0.95,sum by(le)(rate(photo_app_db_duration_seconds_bucket{service_name="photo-review",stage="duckdb.query"}[$__rate_interval])))','photo_gallery','Gallery DuckDB query p95 (seconds)')
    graph["targets"][0]["expr"] += ' or ' + node('histogram_quantile(0.95,sum by(le)(rate(photo_app_db_duration_seconds_bucket{service_name="photo-review",stage="db.query"}[$__rate_interval])))','photo_live_db','GUI PostgreSQL calls p95 (seconds)')
    graph["targets"][1]["expr"] += ' or max by(id,source,target)(photo_pipeline_edge_info'+INST+') or max by(id,source,target)(photo_review_edge_info'+INST+')'
    graph["targets"][1]["expr"] += ' or max by(id,source,target)(photo_immich_edge_info'+INST+')'
    graph["targets"][1]["expr"] += ' or max by(id,source,target)(photo_app_edge_info'+INST+')'
    context_rate='rate(photo_context_stage_seconds_total'+INST+'[$__rate_interval])'
    graph["targets"][0]["expr"] += ' or label_replace(((100 * sum by(id,title) ('+context_rate+') / scalar(sum('+context_rate+')) >= 0) or sum by(id,title)(photo_context_stage_seconds_total'+INST+') * 0), "title", "$1 (%)", "title", "(.+)")'
    graph["targets"][0]["expr"] += ' or '+node('sum(photo_context_jobs{instance=~"$instance",kind=~"ready|retry"})','photo_context_jobs','Photo context queue (photos)')
    graph["targets"][1]["expr"] += ' or max by(id,source,target)(photo_context_edge_info'+INST+')'
    # Luna's comparison queue and writer are distinct from the local Bonsai stream.
    luna_flow = [("luna_queue", 'max(knowledge_index_luna_jobs{instance=~"$instance",state="pending"})', "Piglet Luna queue (items)"),
                 ("luna_client", 'max(knowledge_index_luna_jobs{instance=~"$instance",state="reserved"})', "Luna submission client (reserved)"),
                 ("luna_cloud", 'max(knowledge_index_luna_jobs{instance=~"$instance",state="sent"})', "Enterprise Luna (submitted)"),
                 ("luna_write", 'max(knowledge_index_luna_saved'+INST+')', "Piglet Luna Parquet (captions)")]
    for index, (ident, expression, title) in enumerate(luna_flow):
        if ident in ("luna_client", "luna_cloud"):
            expression += ' and on() (time() - max(knowledge_index_luna_heartbeat_timestamp_seconds' + INST + ') < 240)'
        graph["targets"][0]["expr"] += " or " + node(expression, ident, title)
        if index:
            source = luna_flow[index - 1][0]
            edge = f'label_replace(label_replace(label_replace((({expression}) * 0 + 1), "id", "{source}-{ident}", "", ""), "source", "{source}", "", ""), "target", "{ident}", "", "")'
            graph["targets"][1]["expr"] += " or " + edge
    for backend, title in (("primary", "RTX"), ("metal", "Mac Metal")):
        rate = backend_pace(backend)
        ident = "summary_" + backend
        graph["targets"][0]["expr"] += " or " + node(rate, ident, title + " (saved/min)")
        for source, target in (("inference", ident), (ident, "write")):
            edge = f'label_replace(label_replace(label_replace((({rate}) > 0) * 0 + 1, "id", "{source}-{target}", "", ""), "source", "{source}", "", ""), "target", "{target}", "", "")'
            graph["targets"][1]["expr"] += " or " + edge
    graph["description"] += " Two RTX slots and the Mac share distinct pending items. Both paths feed one Parquet writer. Backend nodes show successful saves per minute over ten minutes. The context worker resumes when the summary queue drains. Photo context runs independently: saved person labels and cached nearby Wikipedia/Wikidata candidates go to the local vision model; PostgreSQL retains provenance and the original caption. Nearby does not mean pictured. Provider calls are serialized and budgeted; the GUI performs no external lookup."
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
    def ollama_average(labels, group):
        return (f'sum by({group})(rate(media_pipeline_ollama_seconds_total{labels}[$__rate_interval])) / '
                f'(sum by({group})(rate(media_pipeline_ollama_observations_total{labels}[$__rate_interval])) > 0)')

    ollama_avg = ollama_average(sel, 'phase,kind')

    def ollama_phase(phase):
        return ollama_average(sel[:-1] + f',phase="{phase}"' + '}', 'kind')

    ollama_remainder = f'clamp_min({ollama_phase("total")} - {ollama_phase("load")} - {ollama_phase("prompt")} - {ollama_phase("generation")}, 0)'
    tokens = ('sum by (phase, kind) (rate(media_pipeline_ollama_tokens_total' + sel + '[$__rate_interval])) / '
              '(sum by (phase, kind) (rate(media_pipeline_ollama_seconds_total' + sel + '[$__rate_interval])) > 0)')
    p += [series("Ollama: seconds per response", [(ollama_avg, "{{kind}} / {{phase}}"),
                 (ollama_remainder, "{{kind}} / server remainder")], 0, 28, 12, 7, unit="s", decimals=2,
                 description="Native Ollama API timings for Ollama runs. Server remainder subtracts load, prompt and generation from total. It can include runner wait and request processing. For client wall time, see Model request under Photo or Video: seconds per stage operation."),
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
                                {"type": "query", "name": "photo_stage", "label": "Photo processing stage",
                                 "datasource": DS, "query": 'label_values(knowledge_index_photo_stage_items{instance=~"$instance"}, stage)',
                                 "refresh": 2, "multi": True, "includeAll": True, "allValue": ".*",
                                 "current": {"text": "All", "value": "$__all"}, "options": []},
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
