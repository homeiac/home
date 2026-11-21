#!/usr/bin/env python3
"""Compare two Bonsai dispatch windows using existing metrics and committed Parquet rows."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request

# Run read-only on Piglet. Return totals only, never asset identifiers.
PARQUET_REPORT = """import json, sys
from datetime import datetime, timezone
from pathlib import Path
import duckdb

start, end = map(int, sys.argv[1:3])
def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).strftime('b%Y%m%dT%H%M%S')
base = Path('/local-3TB-backup/knowledge-index/summaries/gemma4-e2b-p1')
files = [str(path) for path in base.glob('*.parquet') if stamp(start) <= path.name < stamp(end)]
with duckdb.connect() as db:
    db.execute("SET TimeZone='UTC'")
    if not files:
        print(json.dumps(dict(models=[], unique_assets=0)))
        sys.exit(0)
    db.execute('''CREATE TEMP TABLE window_saves AS SELECT model,path,size_bytes,frames_sampled
                  FROM read_parquet(?) WHERE status='ok' ''', [files])
    rows = db.execute('''SELECT model, count(*), count(frames_sampled)
                        FROM window_saves GROUP BY model ORDER BY model''').fetchall()
    unique = db.execute('SELECT count(DISTINCT (path,size_bytes)) FROM window_saves').fetchone()[0]
    print(json.dumps(dict(models=[dict(model=m, saved=n, videos=v) for m,n,v in rows], unique_assets=unique)))
"""


def parse_end(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("Use a UTC timestamp ending in Z, or include an explicit offset")
    return int(parsed.timestamp())


def prometheus(port, expression, end):
    params = urllib.parse.urlencode({"query": expression, "time": end})
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/query?{params}", timeout=15) as response:
        result = json.load(response)["data"]["result"]
    return [{"labels": row["metric"], "value": float(row["value"][1])} for row in result]


def report(port, host, end, minutes):
    interval = f"[{minutes}m]"
    scope = 'instance="pumped-piglet",enricher="gemma4-e2b-p1"'
    queries = {
        "backend_saves_per_minute": f"sum by(backend)(increase(media_pipeline_backend_saved_total{{{scope}}}{interval}))/{minutes}",
        "mean_active_slots": f"avg by(backend)(avg_over_time(media_pipeline_backend_in_flight{{{scope}}}{interval}))",
        "mac_capacity_min": f"min(min_over_time(media_pipeline_mac_request_limit{{{scope}}}{interval}))",
        "active_policy": f"media_pipeline_dispatch_policy_applied_timestamp_seconds{{{scope}}}",
        "stage_seconds": f"sum by(stage)(increase(media_pipeline_stage_seconds_total{{{scope}}}{interval}))",
    }
    metrics = {name: prometheus(port, query, end) for name, query in queries.items()}
    start = end - minutes * 60
    command = f"/opt/knowledge-index/venv/bin/python - {start} {end}"
    parquet = json.loads(subprocess.check_output(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, command],
        input=PARQUET_REPORT, text=True, timeout=30,
    ))
    gpu = sum(row["value"] for row in metrics["backend_saves_per_minute"] if row["labels"]["backend"] in ("primary", "metal"))
    return dict(start_utc=datetime.fromtimestamp(start, timezone.utc).isoformat(),
                end_utc=datetime.fromtimestamp(end, timezone.utc).isoformat(),
                gpu_saves_per_minute=round(gpu, 3), metrics=metrics, parquet=parquet)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=parse_end, help="ISO 8601 end of the baseline window")
    parser.add_argument("--after", required=True, type=parse_end, help="ISO 8601 end of the candidate window")
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument("--local-port", type=int, default=29092)
    args = parser.parse_args()
    if args.minutes < 1 or args.after <= args.before:
        parser.error("Use a positive duration and an after window later than the before window")
    kubeconfig = os.environ.get("KUBECONFIG", str(Path.home() / "kubeconfig"))
    with subprocess.Popen(
        ["kubectl", "--kubeconfig", kubeconfig, "-n", "monitoring", "port-forward",
         "svc/kube-prometheus-stack-prometheus", f"{args.local_port}:9090"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ) as port_forward:
        try:
            for attempt in range(20):
                try:
                    prometheus(args.local_port, "vector(1)", args.after)
                    break
                except OSError:
                    if attempt == 19 or port_forward.poll() is not None:
                        raise
                    time.sleep(.25)
            host = os.environ["CB_HOST"]
            print(json.dumps({name: report(args.local_port, host, end, args.minutes)
                              for name, end in (("before", args.before), ("after", args.after))}, indent=2))
        finally:
            port_forward.terminate()


if __name__ == "__main__":
    main()
