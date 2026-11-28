"""Summarize a workload adapter's saved attempt envelope without live collection."""

import math
import re

from native_output import VerifiedOutputs

HASH = re.compile(r"[a-f0-9]{64}")


def summarize(records: list[dict], verified_outputs: VerifiedOutputs | None, *, workload: str, run_id: str, unit: str,
              profile_sha256: str, start_ns: int, end_ns: int) -> dict:
    """Deduplicate attempts/outputs and combine latency observations, never p95s.

    Workload-owned exporters hash native identities only in this private evidence
    envelope. Canonical output IDs and payloads stay in their original stores.
    Verification refs must come from the existing media checker or native reader.
    This summary does not replace quality, sampling, ownership or publication gates.
    """
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    def number(value: object) -> bool:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0

    require(type(start_ns) is int and type(end_ns) is int and 0 < start_ns < end_ns,
            "invalid output-summary window")
    require(isinstance(profile_sha256, str) and HASH.fullmatch(profile_sha256) is not None,
            "pin the measured adapter/model/prompt profile")
    require(verified_outputs is None or isinstance(verified_outputs, VerifiedOutputs),
            "verification must be produced by the native checker, not claimed hashes")
    if verified_outputs is not None:
        require((verified_outputs.workload, verified_outputs.run_id, verified_outputs.unit, verified_outputs.start_ns, verified_outputs.end_ns)
                == (workload, run_id, unit, start_ns, end_ns), "verification scope differs from output summary")
    proofs = ({dict(row)["verification_ref_sha256"]: dict(row) for row in verified_outputs.outputs}
              if verified_outputs else {})
    attempts, outputs = {}, {}
    evaluation, dispositions, latencies, backends = 0, {}, [], {}
    for row in records:
        require((row.get("workload"), row.get("run_id"), row.get("unit"), row.get("profile_sha256")) ==
                (workload, run_id, unit, profile_sha256), "mixed workload, originating run, unit or immutable profile")
        require(all(isinstance(row.get(k), str) and HASH.fullmatch(row[k])
                    for k in ("job_sha256", "source_version_sha256", "execution_sha256")),
                "missing hashed source/version/execution identity")
        require(isinstance(row.get("backend"), str) and bool(row["backend"])
                and isinstance(row.get("inference_mode"), str) and bool(row["inference_mode"])
                and all(type(row.get(k)) is bool for k in
                        ("retained_stage", "retained_action", "model_called")),
                "missing backend, mode or retained-stage attribution")
        require(row.get("purpose") in {"production", "evaluation"}
                and row.get("disposition") in {"complete", "withheld", "failed", "cache"},
                "unknown attempt purpose or disposition")
        stamp = row.get("finished_ns")
        require(type(stamp) is int and stamp > 0 and number(row.get("seconds")),
                "invalid attempt timestamp or duration")
        execution = row["execution_sha256"]
        require(execution not in attempts or attempts[execution] == row,
                "one execution ID has conflicting observations")
        if execution in attempts:
            continue
        attempts[execution] = row
        if not start_ns < stamp <= end_ns:
            continue
        if row["purpose"] == "evaluation":
            evaluation += 1
            continue
        dispositions[row["disposition"]] = dispositions.get(row["disposition"], 0) + 1
        latencies.append(row["seconds"])
        if row["disposition"] != "complete":
            continue
        first = row.get("first_committed_ns")
        require(type(first) is int and 0 < first <= stamp and number(row.get("amount"))
                and row["amount"] > 0, "production completion lacks first-commit accounting")
        if not start_ns < first <= end_ns:
            continue
        proof = proofs.get(row.get("verification_ref_sha256"))
        if proof is not None:
            require(all(row.get(k) == proof[k] for k in
                        ("job_sha256", "source_version_sha256", "first_committed_ns", "backend", "amount")),
                    "output attribution differs from authoritative native readback")
        logical = row["job_sha256"], row["source_version_sha256"]
        if logical in outputs:
            previous = outputs[logical]
            require((previous["first_committed_ns"], previous["amount"]) == (first, row["amount"]),
                    "conflicting logical-output accounting")
            # Source ordering cannot move a duplicate completion between backends.
            if (row.get("verification_ref_sha256") not in proofs, stamp, row["backend"], execution) >= (
                    previous.get("verification_ref_sha256") not in proofs,
                    previous["finished_ns"], previous["backend"], previous["execution_sha256"]):
                continue
        outputs[logical] = row
    verified, fresh = (0, 0) if verified_outputs is not None else (None, None)
    for row in outputs.values():
        backend = backends.setdefault(row["backend"], {"unique_production_completed": 0,
                                                       "verified_production_completed": 0 if verified_outputs is not None else None})
        backend["unique_production_completed"] += row["amount"]
        if row.get("verification_ref_sha256") in proofs:
            backend["verified_production_completed"] += row["amount"]
            verified += row["amount"]
            fresh += int(row["model_called"])
    latencies.sort()
    return {"workload": workload, "run_id": run_id, "unit": unit, "profile_sha256": profile_sha256,
            "start_ns": start_ns, "end_ns": end_ns, "completed_items": len(outputs),
            "unique_production_completed": sum(row["amount"] for row in outputs.values()),
            "verified_production_completed": verified, "fresh_inference_items": fresh,
            "backends": dict(sorted(backends.items())), "evaluation_attempts_excluded": evaluation,
            "production_attempt_dispositions": dict(sorted(dispositions.items())),
            "p95_s": latencies[math.ceil(.95 * len(latencies)) - 1] if latencies else None,
            "latency_scope": "raw distinct production attempts across all backends",
            "decision": "summary_only_not_qualification"}
