"""Tests for prometheus_targets module."""

import json
from pathlib import Path
from unittest import mock

import pytest
import yaml

from homelab.prometheus_targets import (
    apply_targets_configmap,
    generate_targets,
    generate_targets_json,
    load_cluster_config,
)


SAMPLE_CONFIG = {
    "nodes": [
        {"name": "pve", "ip": "192.168.4.122", "enabled": True},
        {"name": "still-fawn", "ip": "192.168.4.17", "enabled": True},
        {"name": "chief-horse", "ip": "192.168.4.19", "enabled": True},
        {"name": "fun-bedbug", "ip": "192.168.4.172", "enabled": True},
        {"name": "pumped-piglet", "ip": "192.168.4.175", "enabled": True},
    ],
    "monitoring": {
        "node_exporter": {
            "enabled": True,
            "port": 9100,
        },
        "zfs_exporter": {
            "enabled": True,
            "port": 9134,
            "hosts": ["still-fawn", "pumped-piglet", "pve", "chief-horse"],
        },
        "pve_exporter": {
            "enabled": True,
            "port": 9221,
            "metrics_path": "/pve",
            "host": "pve",
        },
        "extra_targets": [
            {
                "job": "crucible-node-exporter",
                "targets": [
                    {"host": "proper-raptor", "ip": "192.168.4.189", "port": 9100},
                ],
            },
        ],
    },
}


@pytest.fixture
def config_file(tmp_path):
    """Create a temporary cluster.yaml."""
    path = tmp_path / "cluster.yaml"
    path.write_text(yaml.dump(SAMPLE_CONFIG))
    return path


# --- load_cluster_config ---


def test_load_cluster_config(config_file):
    config = load_cluster_config(config_file)
    assert len(config["nodes"]) == 5
    assert config["monitoring"]["zfs_exporter"]["port"] == 9134


def test_load_cluster_config_missing():
    with pytest.raises(FileNotFoundError):
        load_cluster_config(Path("/nonexistent/cluster.yaml"))


# --- generate_targets: node-exporter ---


def test_node_exporter_targets():
    targets = generate_targets(SAMPLE_CONFIG)
    ne_targets = [t for t in targets if t["labels"]["job"] == "proxmox-node-exporter"]
    assert len(ne_targets) == 5
    hostnames = {t["labels"]["hostname"] for t in ne_targets}
    assert hostnames == {"pve", "still-fawn", "chief-horse", "fun-bedbug", "pumped-piglet"}
    for t in ne_targets:
        assert t["targets"][0].endswith(":9100")


def test_node_exporter_skips_disabled():
    config = {
        "nodes": [
            {"name": "active", "ip": "10.0.0.1", "enabled": True},
            {"name": "disabled", "ip": "10.0.0.2", "enabled": False},
        ],
        "monitoring": {"node_exporter": {"port": 9100}},
    }
    targets = generate_targets(config)
    ne_targets = [t for t in targets if t["labels"]["job"] == "proxmox-node-exporter"]
    assert len(ne_targets) == 1
    assert ne_targets[0]["labels"]["hostname"] == "active"


def test_node_exporter_default_port():
    config = {"nodes": [{"name": "h", "ip": "10.0.0.1"}], "monitoring": {}}
    targets = generate_targets(config)
    ne_targets = [t for t in targets if t["labels"]["job"] == "proxmox-node-exporter"]
    assert ne_targets[0]["targets"] == ["10.0.0.1:9100"]


# --- generate_targets: zfs-exporter ---


def test_zfs_exporter_targets():
    targets = generate_targets(SAMPLE_CONFIG)
    zfs_targets = [t for t in targets if t["labels"]["job"] == "proxmox-zfs-exporter"]
    assert len(zfs_targets) == 4
    hostnames = {t["labels"]["hostname"] for t in zfs_targets}
    assert hostnames == {"still-fawn", "pumped-piglet", "pve", "chief-horse"}
    for t in zfs_targets:
        assert t["targets"][0].endswith(":9134")


def test_zfs_exporter_disabled():
    config = {
        "nodes": [{"name": "h", "ip": "10.0.0.1"}],
        "monitoring": {"zfs_exporter": {"enabled": False, "hosts": ["h"]}},
    }
    targets = generate_targets(config)
    zfs_targets = [t for t in targets if t["labels"]["job"] == "proxmox-zfs-exporter"]
    assert len(zfs_targets) == 0


def test_zfs_exporter_unknown_host(caplog):
    config = {
        "nodes": [{"name": "known", "ip": "10.0.0.1"}],
        "monitoring": {"zfs_exporter": {"enabled": True, "hosts": ["unknown"]}},
    }
    targets = generate_targets(config)
    zfs_targets = [t for t in targets if t["labels"]["job"] == "proxmox-zfs-exporter"]
    assert len(zfs_targets) == 0
    assert "not in nodes list" in caplog.text


# --- generate_targets: pve-exporter ---


def test_pve_exporter_target():
    targets = generate_targets(SAMPLE_CONFIG)
    pve_targets = [t for t in targets if t["labels"]["job"] == "proxmox-pve-exporter"]
    assert len(pve_targets) == 1
    assert pve_targets[0]["targets"] == ["192.168.4.122:9221"]
    assert pve_targets[0]["labels"]["hostname"] == "pve"


def test_pve_exporter_disabled():
    config = {
        "nodes": [{"name": "pve", "ip": "10.0.0.1"}],
        "monitoring": {"pve_exporter": {"enabled": False, "host": "pve"}},
    }
    targets = generate_targets(config)
    pve_targets = [t for t in targets if t["labels"]["job"] == "proxmox-pve-exporter"]
    assert len(pve_targets) == 0


def test_pve_exporter_unknown_host(caplog):
    config = {
        "nodes": [],
        "monitoring": {"pve_exporter": {"enabled": True, "host": "ghost"}},
    }
    targets = generate_targets(config)
    pve_targets = [t for t in targets if t["labels"]["job"] == "proxmox-pve-exporter"]
    assert len(pve_targets) == 0
    assert "not in nodes list" in caplog.text


# --- generate_targets: extra targets ---


def test_extra_targets():
    targets = generate_targets(SAMPLE_CONFIG)
    extra = [t for t in targets if t["labels"]["job"] == "crucible-node-exporter"]
    assert len(extra) == 1
    assert extra[0]["targets"] == ["192.168.4.189:9100"]
    assert extra[0]["labels"]["hostname"] == "proper-raptor"


def test_extra_targets_empty():
    config = {"nodes": [], "monitoring": {"extra_targets": []}}
    targets = generate_targets(config)
    assert len(targets) == 0


def test_no_monitoring_section():
    config = {"nodes": [{"name": "h", "ip": "10.0.0.1"}]}
    targets = generate_targets(config)
    assert len(targets) == 1
    assert targets[0]["labels"]["job"] == "proxmox-node-exporter"


# --- generate_targets: full config counts ---


def test_full_config_target_count():
    targets = generate_targets(SAMPLE_CONFIG)
    # 5 node-exporter + 4 zfs-exporter + 1 pve-exporter + 1 crucible = 11
    assert len(targets) == 11


def test_all_targets_have_required_labels():
    targets = generate_targets(SAMPLE_CONFIG)
    for t in targets:
        assert "targets" in t
        assert isinstance(t["targets"], list)
        assert len(t["targets"]) == 1
        assert "labels" in t
        assert "job" in t["labels"]
        assert "hostname" in t["labels"]


# --- generate_targets_json ---


def test_generate_targets_json(config_file):
    result = generate_targets_json(config_file)
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) == 11


def test_generate_targets_json_valid_json(config_file):
    result = generate_targets_json(config_file)
    parsed = json.loads(result)
    for entry in parsed:
        assert "targets" in entry
        assert "labels" in entry


# --- apply_targets_configmap ---


def test_apply_configmap_dry_run(config_file):
    result = apply_targets_configmap(config_file, dry_run=True)
    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["targets_count"] == 11
    parsed = json.loads(result["targets_json"])
    assert len(parsed) == 11


def test_apply_configmap_success(config_file):
    create_result = mock.MagicMock()
    create_result.stdout = "apiVersion: v1\nkind: ConfigMap\n"
    create_result.returncode = 0

    apply_result = mock.MagicMock()
    apply_result.stdout = "configmap/prometheus-scrape-targets configured"
    apply_result.returncode = 0

    with mock.patch("subprocess.run", side_effect=[create_result, apply_result]) as mock_run:
        result = apply_targets_configmap(config_file, kubeconfig="/tmp/kubeconfig")

    assert result["success"] is True
    assert result["targets_count"] == 11
    # Verify kubeconfig is passed
    create_call = mock_run.call_args_list[0]
    assert "--kubeconfig" in create_call[0][0]
    assert "/tmp/kubeconfig" in create_call[0][0]


def test_apply_configmap_kubectl_failure(config_file):
    import subprocess as sp

    with mock.patch("subprocess.run", side_effect=sp.CalledProcessError(1, "kubectl", stderr="connection refused")):
        result = apply_targets_configmap(config_file, kubeconfig="/tmp/kc")

    assert result["success"] is False
    assert "connection refused" in result["error"]
