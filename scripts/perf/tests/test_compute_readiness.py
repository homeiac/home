"""Preflight stays on known physical hosts and never mistakes failed probes for idle."""

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "readiness", Path(__file__).resolve().parents[1] / "inspect-compute-readiness.py"
)
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


@pytest.mark.parametrize("host", ["unknown", "k3s-vm-test", "rapid-civet"])
def test_no_probes_to_guessed_guests_or_intentionally_offline_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    inventory = tmp_path / "inventory"
    inventory.write_text(
        "[proxmox]\n192.0.2.10 # known\n192.0.2.11 # rapid-civet\n[k3s-vms]\n192.0.2.12 # k3s-vm-test\n"
    )
    run = Mock()
    monkeypatch.setattr(readiness.subprocess, "run", run)
    with pytest.raises(ValueError):
        readiness.remote(host, inventory)
    run.assert_not_called()


def test_dns_failure_uses_exact_inventory_address_without_disabling_trust(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = tmp_path / "inventory"
    inventory.write_text("[proxmox]\n192.0.2.10 # known\n")
    calls = []

    def run(command: list, **kwargs) -> subprocess.CompletedProcess:
        calls.append(list(command))
        assert kwargs["timeout"] == 15 and command[-1] == "python3 - --collect"
        if len(calls) == 1:
            raise subprocess.CalledProcessError(
                255, command, stderr="Could not resolve hostname"
            )
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"decision": "readiness_only"}), ""
        )

    monkeypatch.setattr(readiness.subprocess, "run", run)
    assert readiness.remote("known", inventory)["decision"] == "readiness_only"
    assert "HostName=192.0.2.10" in calls[1]
    assert all("StrictHostKeyChecking=no" not in call for call in calls)


@pytest.mark.parametrize("exited,exitcode", [(1, 0), (0, None), (1, 1)])
def test_guest_probe_uses_owning_host_and_checks_guest_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exited: int, exitcode: int | None
) -> None:
    inventory = tmp_path / "inventory"
    inventory.write_text(
        "[proxmox]\n192.0.2.10 # known\n[k3s-vms]\n192.0.2.12 # k3s-vm-known (VMID 108)\n"
    )
    envelope = {
        "exited": exited,
        "exitcode": exitcode,
        "out-data": json.dumps({"decision": "readiness_only"}),
    }
    run = Mock(
        return_value=subprocess.CompletedProcess([], 0, json.dumps(envelope), "")
    )
    monkeypatch.setattr(readiness.subprocess, "run", run)
    if exited and exitcode == 0:
        assert readiness.remote("known", inventory, guest=True)["guest_vmid"] == 108
    else:
        with pytest.raises(readiness.ProbeFailure, match="guest_collector_failed"):
            readiness.remote("known", inventory, guest=True)
    command = run.call_args.args[0]
    assert command[-2] == "root@known.maas"
    assert command[-1].startswith("qm guest exec 108 -- python3 -c ")
    assert run.call_args.kwargs["input"] is None


def test_remote_failure_is_sanitized_and_not_a_zero_capacity_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = tmp_path / "inventory"
    inventory.write_text("[proxmox]\n192.0.2.10 # known\n")
    monkeypatch.setattr(
        readiness.subprocess,
        "run",
        Mock(
            side_effect=subprocess.CalledProcessError(
                255, [], stderr="Permission denied; private remote detail"
            )
        ),
    )
    with pytest.raises(readiness.ProbeFailure, match="^ssh_authentication$"):
        readiness.remote("known", inventory)
