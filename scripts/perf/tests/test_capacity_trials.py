"""Registration binds measured shared constraints and cannot grant live admission."""

import json
import stat
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capacity_trials import ACTION, register, validate_receipt

NOW = 1000 * 10**9
POOL, DEVICE = "fixture/slots", "fixture/device"
TARGET, PEER = "cricket-indexer", "photo"


def fixture(at_ns: int = NOW) -> tuple[dict, dict]:
    """Synthetic capacity, not production headroom or recorded live reservations."""
    topology = {
        POOL: {"uses": [DEVICE], "workloads": [TARGET, PEER]},
        DEVICE: {"uses": [], "workloads": [TARGET, PEER]},
    }
    session = {
        "workload": TARGET,
        "run_id": "fixture",
        "requested": [POOL],
        "resources": [POOL, DEVICE],
        "peers": [PEER],
        "topology": topology,
    }
    evidence = {
        "observed_ns": at_ns,
        "evidence_ref": "private/fixture",
        "evidence_sha256": "b" * 64,
    }
    spec = {
        "action": ACTION,
        "pool": POOL,
        "callers": {r: dict(workloads=[TARGET, PEER], **evidence) for r in topology},
        "allocation_evidence": dict(evidence),
        "peer_baseline_sha256": "c" * 64,
        "baseline_allocation": {TARGET: 0, PEER: 4},
        "protected_allocation": {TARGET: 0, PEER: 4},
        "rollback_allocation": {TARGET: 0, PEER: 4},
        "baseline_mode": "observed_idle",
        "fixed_inputs": {
            k + "_sha256": "a" * 64
            for k in (
                "sources",
                "cohort",
                "model",
                "prompt",
                "extraction",
                "quality",
                "environment",
            )
        },
        "constraints": [
            dict(
                resource=r,
                metric="contexts" if r == POOL else "memory",
                unit="slot" if r == POOL else "GiB",
                capacity=8,
                reserved={TARGET: 0, PEER: 4},
                per_extra_worker=1,
                **evidence,
            )
            for r in topology
        ],
        "limits": {
            "window_s": 300,
            "sample_gap_s": 15,
            "minimum_completed_items": 10,
            "no_progress_s": 60,
            "warmup_deadline_s": 60,
            "request_deadline_s": 90,
            "drain_deadline_s": 120,
            "max_peer_loss": 0.10,
            "max_peer_p95_growth": 0.10,
            "max_terminal_error_growth": 0,
        },
        "admission_deadline_ns": at_ns + 10**9,
        "completion_deadline_ns": at_ns + 3600 * 10**9,
        "candidates": [4, 3, 2, 1],
        "repeat_order": "reverse-eligible",
        "selection_tolerance": 0.05,
        "output_accounting": "fresh-evaluation-separate-from-production",
        "lease": {
            "kind": "KubernetesLease",
            "state": "planned",
            "namespace": "fixture",
            "owner": "fixture-run",
            "pools": {DEVICE: "fixture-device"},
            "duration_s": 30,
            "renew_s": 10,
        },
    }
    return session, spec


def test_registration_is_private_immutable_and_not_admission(tmp_path: Path) -> None:
    session, spec = fixture()
    path = tmp_path / "capacity-trial.json"
    report = register(session, spec, NOW, path)
    assert report["decision"] == "registered_not_admitted"
    assert report["ceiling"] == 4
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    receipt = json.loads(path.read_text())
    derived = validate_receipt(session, receipt)
    assert derived["candidate_allocations"] == [
        {TARGET: n, PEER: 4} for n in [4, 3, 2, 1]
    ]
    with pytest.raises(FileExistsError):
        register(session, spec, NOW, path)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: s["constraints"].pop(),
        lambda s: s["constraints"][0].update(capacity=4),
        lambda s: s["constraints"][0].update(capacity=float("nan")),
        lambda s: s["constraints"][0].update(per_extra_worker=0),
        lambda s: s["constraints"][0]["reserved"].pop(PEER),
        lambda s: s["constraints"][0]["reserved"].update(photo=0),
        lambda s: s["constraints"][0].pop("evidence_sha256"),
        lambda s: s["constraints"][0].update(observed_ns=NOW - 16 * 10**9),
        lambda s: s["callers"][DEVICE].update(observed_ns=NOW + 1),
        lambda s: s["callers"][DEVICE]["workloads"].append("unknown-client"),
        lambda s: s["baseline_allocation"].update(photo=3),
        lambda s: s["rollback_allocation"].update(photo=3),
        lambda s: s["baseline_allocation"].update(photo=True),
        lambda s: s.update(candidates=[3, 2, 1]),
        lambda s: s.update(candidates=[1, 2, 3, 4]),
        lambda s: s.update(candidates=[4, 4]),
        lambda s: s.update(candidates=[4, False]),
        lambda s: s["limits"].update(max_peer_loss=0.11),
        lambda s: s["limits"].update(sample_gap_s=16),
        lambda s: s["limits"].update(minimum_completed_items=9),
        lambda s: s["limits"].update(drain_deadline_s=30),
        lambda s: s.update(admission_deadline_ns=NOW + 16 * 10**9),
        lambda s: s.update(completion_deadline_ns=NOW + 100 * 10**9),
        lambda s: s["fixed_inputs"].pop("prompt_sha256"),
        lambda s: s.update(output_accounting="cached-production"),
        lambda s: s["lease"].update(state="acquired"),
        lambda s: s["lease"].update(pools={}),
        lambda s: s["lease"].update(renew_s=11),
    ],
)
def test_unmeasured_or_unsafe_contract_creates_no_receipt(
    tmp_path: Path, mutation
) -> None:
    session, spec = fixture()
    mutation(spec)
    with pytest.raises(ValueError):
        register(session, spec, NOW, tmp_path / "receipt")
    assert not (tmp_path / "receipt").exists()


def test_tightest_resource_sets_ceiling_after_incumbent_and_scheduled_reservations(
    tmp_path: Path,
) -> None:
    session, spec = fixture()
    spec["baseline_mode"] = "active"
    for vector in (
        "baseline_allocation",
        "protected_allocation",
        "rollback_allocation",
    ):
        spec[vector][TARGET] = 1
    for constraint in spec["constraints"]:
        constraint["reserved"][TARGET] = 1
    spec["constraints"][1]["per_extra_worker"] = 1.5
    spec["candidates"] = [3, 2]
    result = register(session, spec, NOW, tmp_path / "receipt")
    assert result["ceiling"] == 3  # one incumbent + floor((8 - 4 - 1) / 1.5)


def test_receipt_rejects_changed_session_policy_and_measured_facts(
    tmp_path: Path,
) -> None:
    session, spec = fixture()
    register(session, spec, NOW, tmp_path / "receipt")
    original = json.loads((tmp_path / "receipt").read_text())
    for key in ("receipt_sha256", "session_sha256", "validator_sha256"):
        receipt = deepcopy(original)
        receipt[key] = "b" * 64
        with pytest.raises(ValueError):
            validate_receipt(session, receipt)
    receipt = deepcopy(original)
    receipt["spec"]["constraints"][0]["capacity"] = 100
    with pytest.raises(ValueError):
        validate_receipt(session, receipt)
    session["run_id"] = "another-run"
    with pytest.raises(ValueError):
        validate_receipt(session, original)


def test_changed_peer_assessment_source_invalidates_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, spec = fixture()
    register(session, spec, NOW, tmp_path / "receipt")
    receipt = json.loads((tmp_path / "receipt").read_text())
    original = Path.read_bytes

    def changed(path: Path) -> bytes:
        raw = original(path)
        return (
            raw + b"\n# changed policy\n" if path.name == "service_budgets.py" else raw
        )

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError, match="integrity changed"):
        validate_receipt(session, receipt)


def test_cli_registers_without_model_requests_or_ownership(tmp_path: Path) -> None:
    session, spec = fixture(time.time_ns())
    (tmp_path / "session.json").write_text(json.dumps(session))
    (tmp_path / "spec.json").write_text(json.dumps(spec))
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "workload.py"),
            "register-capacity",
            "--session",
            str(tmp_path / "session.json"),
            "--spec",
            str(tmp_path / "spec.json"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["decision"] == "registered_not_admitted"
    assert {p.name for p in tmp_path.iterdir()} == {
        "session.json",
        "spec.json",
        "capacity-trial.json",
    }
