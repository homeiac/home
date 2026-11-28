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
FACE_STAGE = 'stage="library-face-observations"'
FACE_ITEMS = "knowledge_index_photo_stage_items"
FACE_SAVED = "knowledge_index_photo_stage_backend_completed"
SERIES = {
    "library-face-observations": {
        "heartbeat": ("knowledge_index_photo_stage_updated_timestamp_seconds", FACE_STAGE),
        "pending_faces": (FACE_ITEMS, FACE_STAGE + ',state="pending"'),
        "running_faces": (FACE_ITEMS, FACE_STAGE + ',state="running"'),
        "reused_faces": (FACE_ITEMS, FACE_STAGE + ',state="reused"'),
        "withheld_faces": (FACE_ITEMS, FACE_STAGE + ',state="withheld"'),
        "mac_saved_faces": (FACE_SAVED, FACE_STAGE + ',backend="mac-metal"'),
        "rtx_saved_faces": (FACE_SAVED, FACE_STAGE + ',backend="rtx3070"')},
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
            matches = [v for labels, v in raw[name] if required.items() <= labels.items()]
            values[key] = matches[0] if matches and min(matches) == max(matches) else None
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
