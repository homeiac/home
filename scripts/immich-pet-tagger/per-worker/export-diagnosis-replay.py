#!/usr/bin/env python3
"""Project pre-intervention Waffles measurements into OTLP log records for offline replay."""
import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PRE = "3511a2c8c81a5d8794a4e2d000b3c3f62a5edc44"
SNAPS = ROOT / "docs/experiments/waffles/2026-11-27-gpu-backtest-snapshots.json"


def attrs(values: dict) -> list:
    kinds = {bool: "boolValue", int: "intValue", float: "doubleValue", str: "stringValue"}
    return [{"key": k, "value": {kinds[type(v)]: str(v) if type(v) is int else v}}
            for k, v in sorted(values.items())]


def nanos(stamp: str) -> int:
    value = datetime.fromisoformat(stamp)
    return int(value.timestamp()) * 10**9 + value.microsecond * 1000


def event(name: str, timestamp: int, **data) -> dict:
    return {"timeUnixNano": str(timestamp), "eventName": name, "attributes": attrs(data)}


def write(path: Path, run: str, events: list) -> None:
    resource = attrs({"service.name": "immich-pet-tagger", "host.name": "mac",
                      "workload.run.id": run})
    packet = {"resourceLogs": [{"resource": {"attributes": resource}, "scopeLogs": [
        {"scope": {"name": "waffles.archived-measurements"}, "logRecords": events}]}]}
    path.write_text(json.dumps(packet, separators=(",", ":"), sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before_fifo", type=Path, help="original before-only bottleneck report")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    q = json.loads(args.before_fifo.read_text())
    if q["at"] != "2026-11-27T06:56:19.537344+00:00":
        raise ValueError("expected the archived pre-intervention queue observation")
    stamp = nanos(q["at"])
    cycle = next(c for c in q["queue"]["base_cycles"] if c["worker"] == "mac")
    explain = q["claim"]["mac-base"][0]
    plan = explain["Plan"]
    sort = next(child for child in plan["Plans"] if child["Parent Relationship"] == "Outer")
    if sort["Node Type"] != "Sort" or sort["Actual Loops"] != 1:
        raise ValueError("unexpected archived claim plan")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write(args.output_dir / "queue.otlp.jsonl", "queue-window", [
        event("worker.cycle", stamp, samples=cycle["intervals"],
              cycle_s=float(cycle["completion_cycle_mean"]), processing_s=cycle["processing_mean"]),
        event("db.claim.plan", stamp, latency_ms=explain["Execution Time"],
              returned=plan["Actual Rows"], order_keys=", ".join(sort["Sort Key"]),
              sort_input_rows=sort["Plans"][0]["Actual Rows"])])
    archive = json.loads(subprocess.check_output(
        ["git", "show", f"{PRE}:docs/reference/waffles-matched-worker-analysis.json"], cwd=ROOT))
    run = "mac-mps-serial-repeat"
    measurements = []
    for p in archive["trials"][run]["passes"]:
        m = p["means"]
        measurements.append(event("worker.profile", nanos(archive["at"]), samples=p["photos"],
                                  accelerator_stage_fraction=(m["detect"] + m["embed"]) / m["total"]))
    for snap in json.loads(SNAPS.read_text())[run]:
        measurements.append(event("device.sample", round(snap["observed_at_unix_s"] * 10**9),
                                  utilization_pct=snap["gpu_percent"], worker_present=snap["worker_present"]))
    write(args.output_dir / "gpu.otlp.jsonl", "device-window", measurements)


if __name__ == "__main__":
    main()
