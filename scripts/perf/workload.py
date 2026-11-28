#!/usr/bin/env python3
"""Prepare a shared-resource workload, check its telemetry and review a measured trial."""
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from capacity_trials import ACTION as CAPACITY_ACTION
from capacity_trials import register as register_capacity
from otel_diagnosis import attributes, digest, predict
from shared_workloads import shared_context

HERE = Path(__file__).resolve().parent
TOPOLOGY = HERE / "shared-workloads.json"
SLUG = re.compile(r"[a-z][a-z0-9_-]{0,63}")
SERIES = {"workload.verified": ("sum", "{item}"), "workload.stage.duration": ("histogram", "s")}
ASAM_SCHEMA_DIGEST = "c3f2485ee35e47fd035a67aa5eba64ff9f27263deaef98a13a839ce1fe8e9bd3"


def packets(path: Path):
    with path.open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def start(args: argparse.Namespace) -> dict:
    topology = json.loads(args.topology.read_text())
    if not SLUG.fullmatch(args.workload) or not all(SLUG.fullmatch(s) for s in args.stage):
        raise ValueError("workload and stage IDs must be stable lowercase slugs")
    if not args.run_id.strip():
        raise ValueError("empty run ID")
    pending = list(args.resource)
    resources = set()
    peers = set()
    while pending:
        resource = pending.pop()
        if resource not in topology:
            raise ValueError(f"register resource {resource} in the topology")
        if resource not in resources:
            resources.add(resource)
            peers.update(topology[resource]["workloads"])
            pending.extend(topology[resource]["uses"])
    session = dict(version=1, workload=args.workload, run_id=args.run_id, output_kind=args.output_kind,
                   stages=sorted(set(args.stage)), requested=sorted(set(args.resource)),
                   resources=sorted(resources), peers=sorted(peers - {args.workload}), topology=topology)
    if getattr(args, "native_adapter", None):
        from native_output import validate_adapter
        adapter = json.loads(args.native_adapter.read_text())
        validate_adapter(adapter, args.workload, args.output_kind)
        session.update(native_adapter=adapter, native_adapter_sha256=digest(adapter))
    if args.output_kind == "service":
        kinds = {topology[r].get("measurement_kinds", {}).get(args.workload, "indexer")
                 for r in resources if args.workload in topology[r]["workloads"]}
        if kinds != {"service"}:
            raise ValueError("service-only intake requires a registered service measurement kind")
        if not getattr(args, "service_objective", None):
            raise ValueError("service intake needs its existing service objective contract")
        objective = json.loads(args.service_objective.read_text())
        if any(not isinstance(objective.get(k), str) or not objective[k].strip()
               for k in ("metric", "contract_ref")):
            raise ValueError("declare the existing service metric and architecture/SLO contract")
        session["service_objective"] = objective
    if args.live:
        result = subprocess.check_output([sys.executable, str(HERE / "observe-shared-workloads.py")], text=True)
        session["activity"] = json.loads(result)
    with args.session.open("x") as output:
        json.dump(session, output, sort_keys=True, indent=2)
        output.write("\n")
    return dict(session=str(args.session), resources=session["resources"], registered_peers=session["peers"],
                activity=session.get("activity"), fleet_review="observe_only")


def valid_id(value: str, width: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[a-fA-F0-9]{{{width}}}", value)) and int(value, 16) != 0


def check_traces(session: dict, path: Path, begin: int, end: int) -> dict:
    stages = set()
    hosts = set()
    identities = {}
    for packet in packets(path):
        for resource in packet.get("resourceSpans", []):
            labels = attributes(resource["resource"].get("attributes", []))
            for group in resource.get("scopeSpans", []):
                for span in group.get("spans", []):
                    if not begin < int(span["startTimeUnixNano"]) < int(span["endTimeUnixNano"]) <= end:
                        continue
                    if (labels.get("service.name"), labels.get("workload.run.id")) != (session["workload"], session["run_id"]):
                        raise ValueError("trace workload or run differs from the session")
                    if not labels.get("host.name"):
                        raise ValueError("trace missing host.name")
                    hosts.add(labels["host.name"])
                    trace, sid, parent = span["traceId"], span["spanId"], span.get("parentSpanId")
                    if not valid_id(trace, 32) or not valid_id(sid, 16) or (parent and not valid_id(parent, 16)):
                        raise ValueError("invalid OTLP trace or span identifier")
                    fields = attributes(span.get("attributes", []))
                    stage = fields.get("workload.stage.id")
                    if stage not in session["stages"]:
                        raise ValueError("undeclared or missing workload.stage.id")
                    stages.add(stage)
                    key = trace.lower(), sid.lower()
                    if key in identities and identities[key] != span:
                        raise ValueError("conflicting span ID within trace")
                    identities[key] = span
    if len(hosts) != 1:
        raise ValueError("provide a closed trace capture for one host with at least one completed stage")
    return dict(host=hosts.pop(), stages=sorted(stages), spans=len(identities))


def check_metrics(session: dict, path: Path, begin: int, end: int) -> list:
    seen = set()
    for packet in packets(path):
        for resource in packet.get("resourceMetrics", []):
            for group in resource.get("scopeMetrics", []):
                for metric in group.get("metrics", []):
                    name = metric["name"]
                    if name not in SERIES:
                        continue
                    kind, unit = SERIES[name]
                    series = metric.get(kind, {})
                    if metric.get("unit") != unit or (kind == "sum" and series.get("isMonotonic") is not True):
                        raise ValueError(f"wrong metric type, unit or monotonicity for {name}")
                    for point in series.get("dataPoints", []):
                        if not begin < int(point["timeUnixNano"]) <= end:
                            continue
                        res = resource.get("resource", {}).get("attributes", [])
                        if any(a["key"] not in ("service.name", "host.name") for a in res):
                            raise ValueError("unexpected resource label on shared-workload metrics")
                        if attributes(res).get("service.name", session["workload"]) != session["workload"]:
                            raise ValueError("metric resource workload differs from session")
                        raw = point.get("attributes", [])
                        if sorted(a["key"] for a in raw) != ["backend", "stage_id", "workload"]:
                            raise ValueError(f"unexpected metric labels for {name}")
                        labels = attributes(raw)
                        if (labels["workload"] != session["workload"] or labels["stage_id"] not in session["stages"]
                                or labels["backend"] not in session["resources"]):
                            raise ValueError("metric labels differ from the declared workload, stage or backend")
                        if kind == "sum":
                            fields = [key for key in ("asDouble", "asInt") if key in point]
                            if len(fields) != 1:
                                raise ValueError("verified counter requires one numeric value")
                            value = float(point[fields[0]])
                            if not math.isfinite(value) or value < 0 or not value.is_integer():
                                raise ValueError("verified count must be a nonnegative item count")
                        else:
                            count = int(point["count"])
                            buckets = [int(n) for n in point.get("bucketCounts", [])]
                            bounds = point.get("explicitBounds", [])
                            if (count < 0 or any(n < 0 for n in buckets)
                                    or (buckets or bounds) and (len(buckets) != len(bounds) + 1 or sum(buckets) != count)):
                                raise ValueError("invalid duration histogram count or buckets")
                        seen.add(name)
    if seen != SERIES.keys():
        raise ValueError(f"missing metric series in window: {sorted(SERIES.keys() - seen)}")
    return sorted(seen)


def capture_window(args: argparse.Namespace, session: dict) -> tuple:
    directory = args.session.parent
    args.capture = args.capture or directory / "traces-and-logs.jsonl"
    if args.at_ns is None:
        args.at_ns = int((directory / "watermark-ns").read_text().strip())
    if args.window <= 0:
        raise ValueError("window must be positive")
    begin = args.at_ns - args.window * 10**9
    traces = check_traces(session, args.capture, begin, args.at_ns)
    diagnosis = predict(args.capture, args.at_ns, args.window)
    if diagnosis["scope"] and tuple(diagnosis["scope"]) != (session["workload"], traces["host"], session["run_id"]):
        raise ValueError("diagnostic facts differ from the trace scope")
    return begin, traces, diagnosis


def diagnose(args: argparse.Namespace, session: dict) -> dict:
    _, _, receipt = capture_window(args, session)
    if receipt["decision"]["state"] == "trial_proposed":
        with (args.session.parent / "prediction.json").open("x") as output:
            json.dump(receipt, output, sort_keys=True)
            output.write("\n")
    return receipt


def review(args: argparse.Namespace, session: dict) -> dict:
    directory = args.session.parent
    begin, traces, diagnosis = capture_window(args, session)
    args.metrics = args.metrics or directory / "metrics.jsonl"
    native = session["output_kind"] != "media"
    for option, name in (("comparison", "comparison.json"),
                         ("references", "native-observations.jsonl" if native else "observations.jsonl"),
                         ("readback", "native-readback.jsonl" if native else "scene-readback.jsonl")):
        if getattr(args, option) is None and (directory / name).is_file():
            setattr(args, option, directory / name)
    if args.schema is None and os.environ.get("ASAM_OPENLABEL_1_0_SCHEMA"):
        args.schema = Path(os.environ["ASAM_OPENLABEL_1_0_SCHEMA"])
    metrics = check_metrics(session, args.metrics, begin, args.at_ns)
    checkpoint = {"topology": session["topology"]}
    if args.comparison:
        comparison = json.loads(args.comparison.read_text())
        if comparison.get("action") == CAPACITY_ACTION:
            raise ValueError("capacity registration is not admission; capacity phase review is not implemented yet")
        if comparison["subject"] != session["workload"] or set(comparison["resources"]) != set(session["requested"]):
            raise ValueError("comparison subject or affected resources differ from the session")
        checkpoint["comparison"] = comparison
    fleet = shared_context(checkpoint, args.at_ns)
    registered = None
    if args.comparison and (directory / "prediction.json").is_file():
        registered = json.loads((directory / "prediction.json").read_text())
        checksum = registered.pop("receipt_sha256")
        if (checksum != digest(registered) or registered["policy_sha256"] != diagnosis["policy_sha256"]
                or registered["scope"] != [session["workload"], traces["host"], session["run_id"]]
                or registered["decision"]["state"] != "trial_proposed"
                or int(registered["as_of_unix_ns"]) > comparison["trial"]["start_ns"]
                or registered["decision"]["action"] != comparison.get("action")):
            raise ValueError("prediction does not match the trial action, scope, policy or start time")
        registered = checksum
    if fleet["decision"] == "eligible" and registered is None:
        fleet.update(decision="hold", reasons=["missing matching pre-change prediction"])
    publication = None
    if session["output_kind"] == "media":
        if args.references and args.readback and args.schema:
            publication = verify_media(args, session)
        else:
            if fleet["decision"] != "rollback":
                fleet["decision"] = "hold"
            fleet["reasons"].append("media publication needs run references, independent readback and OpenLABEL schema")
    elif session["output_kind"] == "service":
        kinds = {session["topology"][r].get("measurement_kinds", {}).get(session["workload"], "indexer")
                 for r in session["resources"] if session["workload"] in session["topology"][r]["workloads"]}
        if (kinds != {"service"} or not session.get("service_objective")
                or not args.comparison or comparison.get("service_objective") != session["service_objective"]):
            if fleet["decision"] != "rollback":
                fleet["decision"] = "hold"
            fleet["reasons"].append("service objective differs from its frozen intake")
    else:
        if session.get("native_adapter") and args.references and args.readback:
            native_window = (comparison["trial"]["start_ns"], comparison["trial"]["end_ns"]) if args.comparison else (begin, args.at_ns)
            publication = verify_native(args, session, native_window)
            if args.comparison and publication["new_verified_amount"] != comparison["trial"]["workloads"][session["workload"]]["verified"]:
                raise ValueError("native readback does not substantiate claimed verified output")
        else:
            if fleet["decision"] != "rollback":
                fleet["decision"] = "hold"
            fleet["reasons"].append("native output needs a frozen architecture adapter and independent readback")
    return dict(telemetry=dict(traces=traces, metrics=metrics), diagnosis=diagnosis, fleet_review=fleet,
                media_readback=publication if not native else None,
                native_readback=publication if native else None, registered_prediction=registered)


def verify_native(args: argparse.Namespace, session: dict, window: tuple | None = None) -> dict:
    """Keep nonmedia schemas/stores native while verifying their immutable export."""
    from native_output import check_native
    adapter = session.get("native_adapter")
    if not adapter or digest(adapter) != session.get("native_adapter_sha256"):
        raise ValueError("native adapter missing or changed after intake")
    start, end = window or (args.at_ns - args.window * 10**9, args.at_ns)
    return check_native(list(packets(args.references)), list(packets(args.readback)),
                        adapter, session, start, end, args.at_ns)


def verify_media(args: argparse.Namespace, session: dict) -> dict:
    sys.path.insert(0, str(HERE.parent / "knowledge-index"))
    from check_media_observations import check
    from jsonschema.exceptions import ValidationError
    refs = list(packets(args.references))
    if not refs or any((r["workload"], r["run_id"]) != (session["workload"], session["run_id"]) for r in refs):
        raise ValueError("supply media references for this workload and run")
    try:
        definition = json.loads(args.schema.read_text())
        encoded = json.dumps(definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        if hashlib.sha256(encoded).hexdigest() != ASAM_SCHEMA_DIGEST:
            raise ValueError("expected the pinned ASAM OpenLABEL 1.0.0 schema")
        return check(refs, list(packets(args.readback)), definition)
    except ValidationError:
        raise ValueError("media reference or scene failed schema validation") from None


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="command", required=True)
    init = sub.add_parser("start", help="resolve the affected resources and create a run contract")
    init.add_argument("--workload", required=True)
    init.add_argument("--run-id", required=True)
    init.add_argument("--output-kind", required=True, choices=["media", "other", "service"])
    init.add_argument("--stage", required=True, action="append")
    init.add_argument("--resource", required=True, action="append")
    init.add_argument("--topology", type=Path, default=TOPOLOGY)
    init.add_argument("--live", action="store_true", help="also collect current Prometheus activity")
    init.add_argument("--native-adapter", type=Path, help="freeze a workload-owned nonmedia schema/store contract")
    init.add_argument("--service-objective", type=Path, help="existing SLO metric/contract for a service-only target")
    audit = sub.add_parser("review", help="validate OTLP and compute the diagnostic and fleet decisions")
    probe = sub.add_parser("diagnose", help="request the next probe or seal a pre-change prediction")
    capacity = sub.add_parser("register-capacity", help="seal a bounded experiment without admitting or changing capacity")
    capacity.add_argument("--spec", type=Path, required=True)
    qualify = sub.add_parser("qualify-capacity", help="offline qualification and finish-time evidence; never actuates")
    qualify.add_argument("--registration", type=Path, required=True)
    qualify.add_argument("--comparison", type=Path, required=True)
    qualify.add_argument("--at-ns", type=int, required=True)
    qualify.add_argument("--references", type=Path, help="native production refs; no claimed accounting summaries")
    qualify.add_argument("--readback", type=Path, help="independent native reader export")
    projection = sub.add_parser("project-completion", help="replay fixed-remaining-work ETA; never admits capacity")
    projection.add_argument("--objective", type=Path, required=True)
    projection.add_argument("--at-ns", type=int, required=True)
    summary = sub.add_parser("summarize-outputs", help="offline workload-neutral deduplication and combined raw latency")
    summary.add_argument("--records", type=Path, required=True)
    summary.add_argument("--session", type=Path, help="frozen native adapter for independent verification")
    summary.add_argument("--references", type=Path)
    summary.add_argument("--readback", type=Path)
    summary.add_argument("--at-ns", type=int, help="readback cutoff; defaults to window end")
    summary.add_argument("--workload", required=True)
    summary.add_argument("--run-id", required=True)
    summary.add_argument("--unit", required=True)
    summary.add_argument("--profile-sha256", required=True)
    summary.add_argument("--start-ns", type=int, required=True)
    summary.add_argument("--end-ns", type=int, required=True)
    audit.add_argument("--metrics", type=Path, help="defaults to metrics.jsonl beside session")
    for command in (audit, probe):
        command.add_argument("--capture", type=Path, help="defaults to traces-and-logs.jsonl beside session")
        command.add_argument("--at-ns", type=int, help="defaults to the watermark-ns file beside session")
        command.add_argument("--window", type=int, default=600, help="window in seconds")
    audit.add_argument("--comparison", type=Path)
    media = sub.add_parser("verify-media", help="check this run's references against independently exported scenes")
    native_check = sub.add_parser("verify-native", help="verify native data without converting it to OpenLABEL")
    native_check.add_argument("--at-ns", type=int, required=True)
    native_check.add_argument("--window", type=int, default=600)
    native_check.add_argument("--references", type=Path, required=True)
    native_check.add_argument("--readback", type=Path, required=True)
    for field in ("references", "readback", "schema"):
        media.add_argument("--" + field, required=True, type=Path)
        audit.add_argument("--" + field, type=Path)
    for parser in (init, audit, probe, media, capacity, qualify, native_check):
        parser.add_argument("--session", required=True, type=Path)
    args = cli.parse_args()
    try:
        if args.command == "project-completion":
            from completion_objective import project
            result = project(json.loads(args.objective.read_text()), args.at_ns)
        elif args.command == "summarize-outputs":
            from workload_measurements import summarize
            proof = None
            if any((args.session, args.references, args.readback)):
                if not all((args.session, args.references, args.readback)):
                    raise ValueError("native summary needs session, references and independent readback together")
                from native_output import output_proof
                session = json.loads(args.session.read_text())
                adapter = session.get("native_adapter")
                if not adapter or digest(adapter) != session.get("native_adapter_sha256"):
                    raise ValueError("native adapter missing or changed")
                proof = output_proof(list(packets(args.references)), list(packets(args.readback)),
                                     adapter, session, args.start_ns, args.end_ns,
                                     args.at_ns if args.at_ns is not None else args.end_ns)
            result = summarize(list(packets(args.records)), proof,
                               workload=args.workload, run_id=args.run_id, unit=args.unit, profile_sha256=args.profile_sha256,
                               start_ns=args.start_ns, end_ns=args.end_ns)
        elif args.command == "start":
            result = start(args)
        else:
            session = json.loads(args.session.read_text())
            if args.command == "register-capacity":
                result = register_capacity(session, json.loads(args.spec.read_text()), time.time_ns(),
                                           args.session.parent / "capacity-trial.json")
            elif args.command == "qualify-capacity":
                from capacity_qualification import qualify as qualify_candidate
                comparison = json.loads(args.comparison.read_text())
                proofs = None
                if args.references and args.readback and session.get("native_adapter"):
                    from native_output import accounting_proof
                    adapter = session["native_adapter"]
                    if digest(adapter) != session.get("native_adapter_sha256"):
                        raise ValueError("native adapter changed after intake")
                    refs, saved = list(packets(args.references)), list(packets(args.readback))
                    proofs = {name: accounting_proof(refs, saved, adapter, session,
                                                     comparison[name]["start_ns"], comparison[name]["end_ns"],
                                                     args.at_ns) for name in ("baseline", "trial")}
                result = qualify_candidate(session, json.loads(args.registration.read_text()),
                                           comparison, args.at_ns, production_proofs=proofs)
            else:
                result = {"diagnose": diagnose, "review": review, "verify-media": verify_media,
                          "verify-native": verify_native}[args.command](args, session)
    except (OSError, KeyError, ValueError, TypeError, subprocess.SubprocessError) as error:
        cli.exit(2, f"Workload check failed: {error}\n")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
