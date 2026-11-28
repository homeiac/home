"""Native IDs/schema/store remain workload-owned, and retries never inflate output."""

import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_output import (
    accounting_proof,
    check_native,
    digest,
    pointer,
    validate_adapter,
)


def fixture() -> tuple:
    schema = {"type": "object", "properties": {
        "doc": {"type": "string"}, "source": {"type": "string"},
        "version": {"type": "string"}, "revision": {"type": "integer"},
        "created_ns": {"type": "integer"}, "backend": {"type": "string"}},
        "required": ["doc", "source", "version", "revision", "created_ns", "backend"], "additionalProperties": False}
    adapter = {"version": 1, "workload": "document-index", "output_kind": "native",
               "unit": "document_versions", "adapter_source_sha256": "a" * 64,
               "canonical_store": {"system": "postgresql", "namespace": "existing-index",
                                   "contract_ref": "fixture/native-data-architecture"},
               "execution_provenance": {"system": "existing-execution-ledger", "namespace": "native-writes",
                                        "contract_ref": "fixture/execution-provenance-architecture"},
               "identity_paths": {"source_id": "/source", "source_version": "/version",
                                  "output_id": "/doc", "revision": "/revision"},
               "logical_first_commit_path": "/created_ns", "backend_path": "/backend",
               "payload_schema": schema, "schema_sha256": digest(schema)}
    session = {"workload": "document-index", "run_id": "fixture", "output_kind": "other"}
    payload = {"doc": "fixture-document", "source": "fixture-source", "version": "v1", "revision": 1,
               "created_ns": 200, "backend": "cpu"}
    ref = {"workload": session["workload"], "run_id": session["run_id"],
           "source_id": payload["source"], "source_version": "v1", "output_id": payload["doc"],
           "revision": 1, "unit": "document_versions", "amount": 1, "backend": "cpu",
           "purpose": "production", "content_sha256": digest(payload), "writer_id": "native-writer"}
    row = {k: ref[k] for k in ("source_id", "source_version", "output_id", "revision")}
    row.update(canonical_store=adapter["canonical_store"], schema_sha256=adapter["schema_sha256"],
               first_committed_ns=200, observed_ns=320, reader_id="separate-native-reader", payload=payload)
    row["execution_provenance"] = {k: ref[k] for k in
        ("source_id", "source_version", "output_id", "revision", "workload", "run_id", "purpose", "content_sha256", "backend")}
    row["execution_provenance"].update(authority=adapter["execution_provenance"],
                                        evidence_ref="fixture/independent-execution-export",
                                        evidence_sha256="e" * 64, recorded_ns=250)
    return adapter, session, ref, row


def test_native_integer_revision_preserved_and_duplicate_retry_counted_once() -> None:
    adapter, session, ref, row = fixture()
    result = check_native([ref, deepcopy(ref)], [row], adapter, session, 100, 300, 350)
    assert result["new_verified_amount"] == result["new_output_items"] == 1
    assert result["resolved_references"] == 1
    assert row["payload"]["revision"] == 1


@pytest.mark.parametrize("mode", ["old", "evaluation"])
def test_old_or_evaluation_output_resolves_without_new_production_credit(mode) -> None:
    adapter, session, ref, row = fixture()
    if mode == "old":
        row["first_committed_ns"] = 50
        row["payload"]["created_ns"] = 50
        ref["content_sha256"] = digest(row["payload"])
        row["execution_provenance"]["content_sha256"] = ref["content_sha256"]
    else:
        ref["purpose"] = "evaluation"
        row["execution_provenance"]["purpose"] = "evaluation"
    assert check_native([ref], [row], adapter, session, 100, 300, 350)["new_output_items"] == 0


@pytest.mark.parametrize("mutation", [
    lambda a, s, r, b: r.update(content_sha256="b" * 64),
    lambda a, s, r, b: r.update(run_id="another-run"),
    lambda a, s, r, b: r.update(unit="faces"),
    lambda a, s, r, b: r.update(amount=2),
    lambda a, s, r, b: b.update(reader_id=r["writer_id"]),
    lambda a, s, r, b: b.update(observed_ns=351),
    lambda a, s, r, b: b["payload"].update(revision="1"),
    lambda a, s, r, b: b.update(canonical_store={}),
    lambda a, s, r, b: a.update(schema_sha256="b" * 64),
    lambda a, s, r, b: s.update(output_kind="media"),
])
def test_native_proof_cannot_change_identity_store_schema_or_scope(mutation) -> None:
    adapter, session, ref, row = fixture()
    mutation(adapter, session, ref, row)
    with pytest.raises((ValueError, KeyError, TypeError)):
        check_native([ref], [row], adapter, session, 100, 300, 350)


def test_external_schema_fetch_and_missing_readback_are_refused() -> None:
    adapter, session, ref, _row = fixture()
    with pytest.raises(ValueError, match="missing independent readback"):
        check_native([ref], [], adapter, session, 100, 300, 350)
    adapter["payload_schema"]["$dynamicRef"] = "https://example.invalid/schema"
    adapter["schema_sha256"] = digest(adapter["payload_schema"])
    with pytest.raises(ValueError, match="offline"):
        validate_adapter(adapter, session["workload"], session["output_kind"])


def test_revision_of_preexisting_output_cannot_become_new_production() -> None:
    adapter, session, ref, row = fixture()
    row["payload"].update(revision=2, created_ns=50)
    row["revision"] = ref["revision"] = 2
    ref["content_sha256"] = digest(row["payload"])
    row["execution_provenance"].update(revision=2, content_sha256=ref["content_sha256"])
    # A revision commit at 200 cannot replace the logical output's creation at 50.
    with pytest.raises(ValueError, match="logical output"):
        check_native([ref], [row], adapter, session, 100, 300, 350)
    row["first_committed_ns"] = 50
    assert check_native([ref], [row], adapter, session, 100, 300, 350)["new_verified_amount"] == 0


def test_reference_cannot_relabel_evaluation_or_reuse_another_originating_run() -> None:
    adapter, session, ref, row = fixture()
    ref["purpose"] = row["execution_provenance"]["purpose"] = "evaluation"
    assert check_native([ref], [row], adapter, session, 100, 300, 350)["new_output_items"] == 0
    ref["purpose"] = "production"
    with pytest.raises(ValueError, match="originating run/purpose"):
        check_native([ref], [row], adapter, session, 100, 300, 350)
    adapter, session, ref, row = fixture()
    ref["run_id"] = session["run_id"] = "new-trial"
    with pytest.raises(ValueError, match="originating run/purpose"):
        check_native([ref], [row], adapter, session, 100, 300, 350)


def test_accounting_is_bound_to_checked_native_backend_and_frozen_session() -> None:
    adapter, session, ref, row = fixture()
    proof = accounting_proof([ref], [row], adapter, session, 100, 300, 350)
    assert proof.amount == 1 and dict(proof.backend_amounts) == {"cpu": 1}
    assert proof.session_sha256 == digest(session)
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        proof.amount = 99


def test_native_pointers_preserve_arrays_and_escaped_keys_without_negative_indexing() -> None:
    assert pointer({"native/rows": [{"~id": "existing-id"}]}, "/native~1rows/0/~0id") == "existing-id"
    for path in ("/native~1rows/-1", "/native~1rows/01", "/native~1rows/3", "/bad~2escape"):
        with pytest.raises(ValueError):
            pointer({"native/rows": [1]}, path)


def test_unresolvable_bundled_schema_fails_without_network(monkeypatch) -> None:
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("offline verifier used network"))
    adapter, session, ref, row = fixture()
    adapter["payload_schema"]["properties"]["doc"] = {"$ref": "#/$defs/missing"}
    adapter["schema_sha256"] = digest(adapter["payload_schema"])
    row["schema_sha256"] = adapter["schema_sha256"]
    with pytest.raises(ValueError, match="unresolved"):
        check_native([ref], [row], adapter, session, 100, 300, 350)
