#!/usr/bin/env python3
"""Read aggregate caller activity from the homelab Prometheus for a fixed evaluation time."""
import argparse
import json
import math
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

PROXY = "/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?"
# Backlog alone cannot be attributed to a device. Keep the labels separate.
SERIES = {
    "cricket-indexer": {
        "heartbeat": ("cricket_heartbeat_timestamp_seconds", ""),
        "mac_active_workers": ("cricket_workers", 'backend="mac",kind="active"'),
        "mac_desired_workers": ("cricket_workers", 'backend="mac",kind="desired"'),
        "queued_jobs_all_backends": ("cricket_jobs", 'state="queued"')},
    "knowledge-index": {
        "heartbeat": ("knowledge_index_last_run_timestamp_seconds", ""),
        "export_ok": ("knowledge_index_exporter_success", ""),
        "summary_enricher_active": ("knowledge_index_enrich_active", ""),
        "saved_captions_last_ten_min_all_backends": ("knowledge_index_caption_first_saved_last_ten_minutes", "")},
    "knowledge-index/caption-recovery": {
        "heartbeat": ("knowledge_index_caption_recovery_snapshot_seconds", ""),
        "mac_saved_captions_per_min": ("knowledge_index_caption_recovery_saved_per_minute", 'backend="Mac Metal"'),
        "pending_recovery_assets_all_backends": ("knowledge_index_caption_recovery_assets", 'state="pending"')},
    "immich-pet-tagger": {
        "heartbeat": ("waffles_queue_report_timestamp_seconds", ""),
        "mac_active_workers": ("waffles_worker_active_instances", 'worker="mac"')},
    "knowledge-index/media-summary": {
        "heartbeat": ("media_pipeline_heartbeat_timestamp_seconds", ""),
        "running": ("media_pipeline_running", ""),
        "pending_from_worker_scan": ("media_pipeline_queue", ""),
        "mac_in_flight": ("media_pipeline_backend_in_flight", 'backend="metal"'),
        "primary_in_flight": ("media_pipeline_backend_in_flight", 'backend="primary"'),
        "mac_parquet_writes_process_total": ("media_pipeline_backend_saved_total", 'backend="metal"'),
        "primary_parquet_writes_process_total": ("media_pipeline_backend_saved_total", 'backend="primary"'),
        "cache_parquet_writes_process_total": ("media_pipeline_backend_saved_total", 'backend="cache"'),
        "mac_offered_requests": ("media_pipeline_mac_request_limit", ""),
    },
    "knowledge-index/library-face-observations": {
        "heartbeat": ("knowledge_index_photo_stage_updated_timestamp_seconds", 'stage="library-face-observations"'),
        "pending_checkpoints": ("knowledge_index_photo_stage_items", 'stage="library-face-observations",state="pending"'),
        "running_checkpoints": ("knowledge_index_photo_stage_items", 'stage="library-face-observations",state="running"'),
        "complete_checkpoints": ("knowledge_index_photo_stage_items", 'stage="library-face-observations",state="complete"'),
        "failed_checkpoints": ("knowledge_index_photo_stage_items", 'stage="library-face-observations",state="failed"'),
        "mac_complete_checkpoints": ("knowledge_index_photo_stage_backend_completed", 'stage="library-face-observations",backend="mac-metal"'),
        "rtx_complete_checkpoints": ("knowledge_index_photo_stage_backend_completed", 'stage="library-face-observations",backend="rtx3070"'),
        "historical_model_request_p95_s": ("knowledge_index_photo_stage_phase_p95_seconds", 'stage="library-face-observations",phase="model_request"'),
    },
    "frigate": {
        "heartbeat": ("photo_frigate_last_poll_timestamp_seconds", ""),
        "stats_endpoint_up": ("photo_frigate_service_up", 'id="frigate_service"'),
        "detector_rolling_mean_ms": ("photo_frigate_processing_milliseconds", 'kind="detector"'),
        "object_detection_fps": ("photo_frigate_frames_per_second", 'kind="objects"'),
        "face_recognition_fps": ("photo_frigate_frames_per_second", 'kind="faces"'),
    },
    "immich": {
        "heartbeat": ("immich_observer_last_success_timestamp_seconds", 'source="queues"'),
        "queue_observer_up": ("immich_observer_source_up", 'source="queues"'),
        **{queue + "_" + state: ("immich_queue_jobs", f'queue="{queue}",state="{state}"')
           for queue in ("face_detection", "facial_recognition")
           for state in ("waiting", "active", "delayed", "prioritized", "failed", "paused")},
    },
}


def collect(at: int, kubeconfig: Path) -> dict:
    names = sorted({name for fields in SERIES.values() for name, _ in fields.values()})
    # One snapshot from Prometheus; expose only the numeric fields requested.
    query = '{__name__=~"' + "|".join(names) + '"}'
    endpoint = PROXY + urlencode({"query": query, "time": at})
    out = subprocess.check_output(["kubectl", "--kubeconfig", str(kubeconfig), "--request-timeout=8s",
                                   "get", "--raw", endpoint], timeout=12)
    answer = json.loads(out)
    if answer["status"] != "success":
        raise ValueError("Prometheus query failed")
    raw = {name: [] for name in names}
    for row in answer["data"]["result"]:
        value = float(row["value"][1])
        if math.isfinite(value):
            raw[row["metric"]["__name__"]].append((row["metric"], value))
    result = {}
    for workload, fields in SERIES.items():
        # Identify disagreement between replicas instead of adding duplicate reports.
        values = {}
        for key, (name, selector) in fields.items():
            required = dict(part.replace('"', '').split('=') for part in selector.split(',') if part)
            selected = [(labels, v) for labels, v in raw[name] if required.items() <= labels.items()]
            matches = [v for _, v in selected]
            # Distinct enrichers are distinct callers, even if their numbers
            # happen to match. Do not mistake them for duplicate scrape replicas.
            streams = {labels.get("enricher") for labels, _ in selected}
            values[key] = matches[0] if matches and min(matches) == max(matches) and len(streams) == 1 else None
        stamp = values.pop("heartbeat")
        fresh = stamp is not None and 0 <= at - stamp <= 180
        result[workload] = dict(source_age_s=round(at - stamp, 1) if stamp else None,
                                fresh=fresh, observations=values if fresh else {})
    return dict(as_of_unix_s=at, workloads=result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--at", type=int, help="fixed Unix evaluation time in seconds")
    parser.add_argument("--kubeconfig", type=Path, default=Path.home() / "kubeconfig")
    args = parser.parse_args()
    print(json.dumps(collect(args.at if args.at is not None else int(time.time()), args.kubeconfig),
                     indent=2, sort_keys=True))
