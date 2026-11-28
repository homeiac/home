#!/usr/bin/env python3
"""Read aggregate caller activity from the homelab Prometheus for a fixed evaluation time."""
import argparse
import hashlib
import json
import math
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

PROXY = "/api/v1/namespaces/monitoring/services/http:kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?"
# Each mapping selects numeric observations; a missing series remains unknown.
REGISTRY = Path(__file__).with_name("shared-workload-observers.json")
SERIES = json.loads(REGISTRY.read_text())["workloads"]


def registry(path: Path) -> dict:
    """Load declarative metric mappings without importing workload execution code."""
    value = json.loads(path.read_text())
    if type(value.get("version")) is not int or value["version"] != 1 or not isinstance(value.get("workloads"), dict) or not value["workloads"]:
        raise ValueError("invalid observer registry")
    metric = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")
    selector = re.compile(r'(?:[a-zA-Z_][a-zA-Z0-9_]*="[^"\\]*")(?:,[a-zA-Z_][a-zA-Z0-9_]*="[^"\\]*")*')
    for fields in value["workloads"].values():
        if not isinstance(fields, dict) or "heartbeat" not in fields:
            raise ValueError("every observer needs a source heartbeat")
        for point in fields.values():
            if (not isinstance(point, list) or len(point) != 2
                    or not all(isinstance(v, str) for v in point)
                    or not metric.fullmatch(point[0])
                    or point[1] and not selector.fullmatch(point[1])):
                raise ValueError("invalid observer metric or exact-label selector")
            labels = re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"\\]*)"', point[1])
            if len(labels) != len({k for k, _ in labels}):
                raise ValueError("duplicate observer selector label")
    return value["workloads"]



def collect(at: int, kubeconfig: Path, mappings: dict | None = None, response: dict | None = None) -> dict:
    mappings = SERIES if mappings is None else mappings
    names = sorted({name for fields in mappings.values() for name, _ in fields.values()})
    # One snapshot from Prometheus; expose only the numeric fields requested.
    query = '{__name__=~"' + "|".join(names) + '"}'
    endpoint = PROXY + urlencode({"query": query, "time": at})
    if response is None:
        out = subprocess.check_output(["kubectl", "--kubeconfig", str(kubeconfig), "--request-timeout=8s",
                                       "get", "--raw", endpoint], timeout=12)
        answer = json.loads(out)
    else:
        answer = response
    if answer["status"] != "success":
        raise ValueError("Prometheus query failed")
    raw = {name: [] for name in names}
    for row in answer["data"]["result"]:
        if row["metric"]["__name__"] not in raw:
            continue
        value = float(row["value"][1])
        if math.isfinite(value):
            raw[row["metric"]["__name__"]].append((row["metric"], value))
    result = {}
    for workload, fields in mappings.items():
        # Identify disagreement between replicas instead of adding duplicate reports.
        values = {}
        for key, (name, selector) in fields.items():
            required = dict(re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"\\]*)"', selector))
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
    def fingerprint(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return dict(as_of_unix_s=at, workloads=result, observer_contract_sha256=fingerprint(mappings),
                response_sha256=fingerprint(answer))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--at", type=int, help="fixed Unix evaluation time in seconds")
    parser.add_argument("--kubeconfig", type=Path, default=Path.home() / "kubeconfig")
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--input", type=Path, help="replay a saved Prometheus response without network access")
    args = parser.parse_args()
    if args.input and args.at is None:
        parser.error("offline replay requires an explicit --at cutoff")
    print(json.dumps(collect(args.at if args.at is not None else int(time.time()), args.kubeconfig,
                             registry(args.registry), json.loads(args.input.read_text()) if args.input else None),
                     indent=2, sort_keys=True))
