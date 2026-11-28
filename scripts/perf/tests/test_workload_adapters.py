"""Different owners plug into the same safety/collection/aggregation code."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

PERF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PERF))
from native_output import digest, output_proof
from test_native_output import fixture as native_fixture
from workload_measurements import summarize


def attempt(index=0, **updates) -> dict:
    row = {"workload": "document-index", "run_id": "fixture", "unit": "document_versions",
           "profile_sha256": "a" * 64, "job_sha256": f"{index + 1:064x}",
           "source_version_sha256": "b" * 64, "execution_sha256": f"{index + 1:064x}",
           "backend": "gpu", "inference_mode": "two_pass", "retained_stage": False,
           "retained_action": False, "model_called": True, "purpose": "production",
           "disposition": "complete", "first_committed_ns": 150 + index,
           "finished_ns": 200 + index, "seconds": 1, "amount": 1}
    return dict(row, **updates)


def summary(rows, proof=None):
    return summarize(rows, proof, workload="document-index", run_id="fixture", unit="document_versions",
                     profile_sha256="a" * 64, start_ns=100, end_ns=300)


def test_retries_replays_and_withheld_are_not_added_to_new_production() -> None:
    row = attempt()
    result = summary([row, deepcopy(row), attempt(1, purpose="evaluation"),
                      attempt(2, disposition="withheld"), attempt(3, disposition="cache")])
    assert result["completed_items"] == 1
    assert result["verified_production_completed"] is None
    assert result["evaluation_attempts_excluded"] == 1
    assert result == summary([attempt(3, disposition="cache"), attempt(2, disposition="withheld"),
                              attempt(1, purpose="evaluation"), row, deepcopy(row)])


def test_combined_latency_uses_raw_attempts_not_average_backend_percentiles() -> None:
    rows = [attempt(i) for i in range(20)] + [attempt(20, backend="cpu", seconds=100),
                                              attempt(21, backend="cpu", seconds=100)]
    result = summary(rows)
    assert result["p95_s"] == 100
    assert result["unique_production_completed"] == 22
    assert result["backends"]["gpu"]["unique_production_completed"] == 20


def test_cross_backend_retry_attribution_is_order_independent_and_old_output_excluded() -> None:
    first = attempt()
    retry = dict(first, execution_sha256="c" * 64, backend="cpu", finished_ns=250)
    old = attempt(2, first_committed_ns=50)
    outside = attempt(3, first_committed_ns=50, finished_ns=90)
    result = summary([first, retry, old, outside])
    assert result == summary([outside, old, retry, first])
    assert result["completed_items"] == 1
    assert result["backends"] == {"gpu": {"unique_production_completed": 1,
                                            "verified_production_completed": None}}
    with pytest.raises(ValueError, match="logical-output"):
        summary([first, dict(retry, first_committed_ns=151)])


def test_authoritative_native_binding_prevents_backend_or_job_relabelling() -> None:
    adapter, session, ref, readback = native_fixture()
    proof = output_proof([ref], [readback], adapter, session, 100, 300, 350)
    record = attempt(job_sha256=digest({"source_id": ref["source_id"], "output_id": ref["output_id"]}),
                     source_version_sha256=digest(ref["source_version"]),
                     first_committed_ns=200, backend="cpu", verification_ref_sha256=digest(ref))
    assert summary([record], proof)["verified_production_completed"] == 1
    with pytest.raises(ValueError, match="attribution"):
        summary([dict(record, backend="gpu")], proof)
    with pytest.raises(ValueError, match="not claimed hashes"):
        summary([record], [digest(ref)])
    with pytest.raises(ValueError, match="profile"):
        summary([dict(record, profile_sha256="c" * 64)], proof)




def test_native_adapter_cli_freezes_architecture_and_verifies_existing_data(tmp_path: Path) -> None:
    adapter, session, ref, readback = native_fixture()
    topology = tmp_path / "topology.json"
    topology.write_text(json.dumps({"fixture/cpu": {"uses": [], "workloads": [session["workload"]]}}))
    contract = tmp_path / "adapter.json"
    contract.write_text(json.dumps(adapter))
    run = tmp_path / "session.json"
    command = [sys.executable, str(PERF / "workload.py")]
    subprocess.check_output([*command, "start", "--session", str(run), "--workload", session["workload"],
                             "--run-id", session["run_id"], "--output-kind", "other", "--stage", "write",
                             "--resource", "fixture/cpu", "--topology", str(topology), "--native-adapter", str(contract)])
    refs, saved = tmp_path / "refs.jsonl", tmp_path / "readback.jsonl"
    # CLI windows are seconds, while the tiny source timestamps in unit fixtures
    # are nanoseconds; use a correspondingly shifted immutable fixture here.
    ref = deepcopy(ref)
    readback = deepcopy(readback)
    readback.update(first_committed_ns=2 * 10**9, observed_ns=3 * 10**9)
    readback["payload"]["created_ns"] = 2 * 10**9
    ref["content_sha256"] = digest(readback["payload"])
    readback["execution_provenance"].update(content_sha256=ref["content_sha256"], recorded_ns=2 * 10**9)
    refs.write_text(json.dumps(ref) + "\n")
    saved.write_text(json.dumps(readback) + "\n")
    original = saved.read_bytes()
    report = json.loads(subprocess.check_output([*command, "verify-native", "--session", str(run),
                                                "--references", str(refs), "--readback", str(saved),
                                                "--at-ns", str(3 * 10**9), "--window", "2"]))
    assert report["new_verified_amount"] == 1
    assert saved.read_bytes() == original
    frozen = json.loads(run.read_text())
    frozen["native_adapter"]["unit"] = "different_unit"
    run.write_text(json.dumps(frozen))
    result = subprocess.run([*command, "verify-native", "--session", str(run), "--references", str(refs),
                             "--readback", str(saved), "--at-ns", str(3 * 10**9)], capture_output=True, check=False)
    assert result.returncode != 0
