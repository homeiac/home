"""Read-only serving inspection never exposes prompts or confuses missing data with idle."""

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "capacity_inspection",
    Path(__file__).resolve().parents[1] / "inspect-bonsai-capacity.py",
)
inspector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspector)


@pytest.mark.parametrize(
    "state,active", [(True, 1), (False, 0), (None, None), (1, None)]
)
def test_counts_keep_unknown_state_and_strip_request_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: object, active: int | None
) -> None:
    key = tmp_path / "key"
    key.write_text("synthetic-fixture")
    slots = [
        {"id": "private-request", "is_processing": state, "prompt": "private-media"}
    ]
    opener = MagicMock()
    opener.open.side_effect = [
        io.BytesIO(b'{"status":"ok"}'),
        io.BytesIO(json.dumps(slots).encode()),
    ]
    monkeypatch.setattr(inspector.urllib.request, "build_opener", lambda *args: opener)
    report = inspector.collect("http://fixture", key)
    assert report["serving_contexts"] == 1 and report["processing_contexts"] == active
    assert report["decision"] == "observe_only"
    assert "private" not in json.dumps(report) and "synthetic" not in json.dumps(report)
    assert all(
        call.args[0].get_method() == "GET"
        for call in opener.open.call_args_list
    )


def test_redirects_do_not_forward_runtime_access() -> None:
    assert (
        inspector.NoRedirect().redirect_request(
            None, None, 302, "", None, "https://other"
        )
        is None
    )
