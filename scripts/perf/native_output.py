"""Verify workload-owned native data through saved, independently exported readback.

This module never writes an output store, performs inference, or queries a service.
Media observations retain the existing OpenLABEL verifier instead of this contract.
"""

import math
import re
from dataclasses import dataclass

from jsonschema.validators import validator_for
from otel_diagnosis import digest
from referencing import Registry
from referencing.exceptions import Unresolvable

HASH = re.compile(r"[a-f0-9]{64}")
IDENTITIES = ("source_id", "source_version", "output_id", "revision")


@dataclass(frozen=True)
class AccountingProof:
    """Internal result of native checking; never constructed from a claimed JSON summary."""

    workload: str
    run_id: str
    unit: str
    start_ns: int
    end_ns: int
    amount: float
    backend_amounts: tuple[tuple[str, float], ...]
    evidence_sha256: str
    session_sha256: str


@dataclass(frozen=True)
class VerifiedOutputs:
    """Immutable per-output bindings produced by native checking, not a JSON flag."""

    workload: str
    run_id: str
    unit: str
    start_ns: int
    end_ns: int
    outputs: tuple[tuple[tuple[str, object], ...], ...]


def require(condition: bool, message: str) -> None:
    """Fail without echoing private payloads or identifiers."""
    if not condition:
        raise ValueError(message)


def pointer(value: object, path: str) -> object:
    """Resolve an adapter's JSON Pointer; never evaluate code or fetch a URL."""
    require(isinstance(path, str) and path.startswith("/"), "invalid identity pointer")
    for part in path[1:].split("/"):
        require(re.search(r"~(?![01])", part) is None, "invalid identity pointer escape")
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            require(re.fullmatch(r"0|[1-9][0-9]*", part) is not None and int(part) < len(value),
                    "invalid identity array pointer")
            value = value[int(part)]
        else:
            require(isinstance(value, dict) and part in value, "identity pointer does not resolve")
            value = value[part]
    return value


def validate_adapter(adapter: dict, workload: str, output_kind: str) -> None:
    """Bind a reviewed adapter to its existing schema, store and native identities."""
    require(type(adapter.get("version")) is int and adapter["version"] == 1 and adapter.get("workload") == workload,
            "native adapter version or workload mismatch")
    require(output_kind == "other" and adapter.get("output_kind") == "native",
            "media must use the existing OpenLABEL verifier")
    require(isinstance(adapter.get("unit"), str) and bool(adapter["unit"].strip()),
            "native adapter needs an output unit")
    store = adapter.get("canonical_store", {})
    require(all(isinstance(store.get(k), str) and bool(store[k].strip())
                for k in ("system", "namespace", "contract_ref")),
            "declare the existing canonical store and architecture contract")
    require(store["system"] != "openlabel", "OpenLABEL needs media verification")
    provenance = adapter.get("execution_provenance", {})
    require(all(isinstance(provenance.get(k), str) and bool(provenance[k].strip())
                for k in ("system", "namespace", "contract_ref")),
            "declare the workload's existing execution provenance authority")
    require(HASH.fullmatch(adapter.get("adapter_source_sha256", "")) is not None,
            "pin the workload adapter implementation")
    paths = adapter.get("identity_paths", {})
    require(set(paths) == set(IDENTITIES) and all(isinstance(p, str) and p.startswith("/")
                                                for p in paths.values()),
            "bind native source/version/output/revision identities")
    require(all(isinstance(adapter.get(k), str) and adapter[k].startswith("/")
                for k in ("logical_first_commit_path", "backend_path")),
            "bind logical first-commit and original backend to canonical native data")
    schema = adapter.get("payload_schema")
    require(isinstance(schema, dict) and adapter.get("schema_sha256") == digest(schema),
            "native payload schema changed or missing")
    # External schema resolution is intentionally unavailable to an offline replay.
    def local_refs(value: object) -> bool:
        if isinstance(value, dict):
            return all((key not in {"$ref", "$dynamicRef", "$recursiveRef"}
                        or isinstance(item, str) and item.startswith("#"))
                       and local_refs(item) for key, item in value.items())
        return not isinstance(value, list) or all(local_refs(item) for item in value)
    require(local_refs(schema), "bundle schema references for offline verification")
    validator_for(schema).check_schema(schema)


def check_native(references: list[dict], readback: list[dict], adapter: dict,
                 session: dict, start_ns: int, end_ns: int, cutoff_ns: int | None = None) -> dict:
    """Resolve native refs and count first commits once, excluding old/replayed data.

    Readback is an export made by the workload's independent native reader. Its
    source implementation and artifact hashes belong in the experiment manifest;
    this checker validates consistency, not the honesty of an arbitrary exporter.
    """
    validate_adapter(adapter, session["workload"], session["output_kind"])
    cutoff_ns = end_ns if cutoff_ns is None else cutoff_ns
    require(type(cutoff_ns) is int and cutoff_ns >= end_ns, "invalid native readback cutoff")
    require(0 < start_ns < end_ns, "invalid native verification window")
    require(bool(references), "native output references missing")
    index = {}
    for row in readback:
        require(all(type(row.get(k)) in (str, int) and row[k] != "" for k in IDENTITIES),
                "invalid native readback identity")
        key = tuple(row[k] for k in IDENTITIES)
        require(key not in index or index[key] == row, "conflicting native readback")
        index[key] = row
    # An explicit empty registry cannot retrieve a missing schema over the network.
    validator = validator_for(adapter["payload_schema"])(adapter["payload_schema"], registry=Registry())
    new, evidence, verified_refs, verified_outputs = {}, set(), set(), {}
    for ref in references:
        require((ref.get("workload"), ref.get("run_id")) ==
                (session["workload"], session["run_id"]), "native reference run mismatch")
        require(ref.get("unit") == adapter["unit"], "native output unit mismatch")
        require(all(type(ref.get(k)) in (str, int) and ref[k] != "" for k in IDENTITIES),
                "missing native identity")
        require(ref.get("purpose") in {"production", "evaluation"}, "native output purpose missing")
        key = tuple(ref[k] for k in IDENTITIES)
        row = index.get(key)
        require(isinstance(row, dict), "native output missing independent readback")
        require(row.get("canonical_store") == adapter["canonical_store"]
                and row.get("schema_sha256") == adapter["schema_sha256"],
                "readback store or native schema differs")
        require(isinstance(ref.get("writer_id"), str) and bool(ref["writer_id"])
                and isinstance(row.get("reader_id"), str) and bool(row["reader_id"])
                and row["reader_id"] != ref["writer_id"], "independent native reader required")
        value = row.get("payload")
        require(not isinstance(value, dict) or not isinstance(value.get("openlabel"), dict),
                "media scenes must use the existing OpenLABEL verifier")
        try:
            errors = list(validator.iter_errors(value))
        except Unresolvable:
            raise ValueError("native schema reference is unresolved") from None
        require(not errors, "native payload failed its schema")
        require(digest(value) == ref.get("content_sha256"), "native content digest differs")
        require(all(type(pointer(value, adapter["identity_paths"][k])) is type(ref[k])
                    and pointer(value, adapter["identity_paths"][k]) == ref[k] for k in IDENTITIES),
                "native identity does not match saved payload")
        first, observed = row.get("first_committed_ns"), row.get("observed_ns")
        require(type(first) is int and type(observed) is int and 0 < first <= observed <= cutoff_ns,
                "invalid or future native commit/readback timestamp")
        logical_first = pointer(value, adapter["logical_first_commit_path"])
        require(type(logical_first) is int and logical_first == first,
                "first commit must be the native logical output's creation, not its revision timestamp")
        backend = pointer(value, adapter["backend_path"])
        require(isinstance(backend, str) and bool(backend) and ref.get("backend") == backend,
                "backend provenance differs from native readback")
        origin = row.get("execution_provenance", {})
        require(origin.get("authority") == adapter["execution_provenance"]
                and all(origin.get(k) == ref[k] for k in
                        (*IDENTITIES, "workload", "run_id", "purpose", "content_sha256", "backend"))
                and isinstance(origin.get("evidence_sha256"), str)
                and HASH.fullmatch(origin["evidence_sha256"]) is not None
                and isinstance(origin.get("evidence_ref"), str) and bool(origin["evidence_ref"])
                and type(origin.get("recorded_ns")) is int and 0 < origin["recorded_ns"] <= observed,
                "originating run/purpose/output needs independent saved execution provenance")
        amount = ref.get("amount")
        require(type(amount) in (int, float) and math.isfinite(amount) and amount > 0,
                "invalid native output amount")
        amount_path = adapter.get("amount_path")
        expected = pointer(value, amount_path) if amount_path is not None else 1
        require(type(expected) in (int, float) and expected == amount, "native amount differs")
        evidence.add(key)
        if start_ns < first <= end_ns and ref.get("purpose") == "production":
            logical = key[:3]  # Corrections/revisions do not become another new source output.
            require(logical not in new or new[logical] == (amount, backend), "conflicting native accounting")
            new[logical] = amount, backend
            verified_refs.add(digest(ref))
            verified_outputs[digest(ref)] = {
                "verification_ref_sha256": digest(ref),
                "job_sha256": digest({"source_id": ref["source_id"], "output_id": ref["output_id"]}),
                "source_version_sha256": digest(ref["source_version"]),
                "first_committed_ns": first, "backend": backend, "amount": amount,
            }
    backends = {}
    for amount, backend in new.values():
        backends[backend] = backends.get(backend, 0) + amount
    return {"protocol": "native-output-v1", "unit": adapter["unit"],
            "resolved_references": len(evidence), "new_output_items": len(new),
            "new_verified_amount": sum(amount for amount, _ in new.values()),
            "backend_verified_amounts": dict(sorted(backends.items())),
            "verified_reference_sha256": sorted(verified_refs),
            "verified_outputs": [verified_outputs[k] for k in sorted(verified_outputs)]}


def accounting_proof(references: list[dict], readback: list[dict], adapter: dict,
                     session: dict, start_ns: int, end_ns: int, cutoff_ns: int) -> AccountingProof:
    """Create typed accounting only after executing the native checker."""
    report = check_native(references, readback, adapter, session, start_ns, end_ns, cutoff_ns)
    return AccountingProof(session["workload"], session["run_id"], report["unit"],
                           start_ns, end_ns, report["new_verified_amount"],
                           tuple(report["backend_verified_amounts"].items()),
                           digest({"references": references, "readback": readback, "adapter": adapter}),
                           digest(session))


def output_proof(references: list[dict], readback: list[dict], adapter: dict,
                 session: dict, start_ns: int, end_ns: int, cutoff_ns: int) -> VerifiedOutputs:
    """Bind source hashes, original backend, first commit and amount after native validation."""
    report = check_native(references, readback, adapter, session, start_ns, end_ns, cutoff_ns)
    return VerifiedOutputs(session["workload"], session["run_id"], report["unit"], start_ns, end_ns,
                           tuple(tuple(sorted(row.items())) for row in report["verified_outputs"]))
