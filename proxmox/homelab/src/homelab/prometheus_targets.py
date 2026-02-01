"""Generate Prometheus file_sd_configs targets from cluster.yaml.

Reads the cluster configuration and produces a JSON target list suitable
for Prometheus file_sd_configs.  Each target group contains a single
host:port with labels for ``job`` and ``hostname`` so that Prometheus
job-level ``relabel_configs`` can filter by the ``job`` label.

Usage (library)::

    from homelab.prometheus_targets import generate_targets_json
    print(generate_targets_json("config/cluster.yaml"))

Usage (CLI)::

    poetry run homelab monitoring generate-targets
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def load_cluster_config(config_path: Path | str) -> dict[str, Any]:
    """Load and return the parsed cluster.yaml."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def _node_ip_map(config: dict[str, Any]) -> dict[str, str]:
    """Build a name -> ip lookup from the nodes list."""
    return {
        node["name"]: node["ip"]
        for node in config.get("nodes", [])
        if node.get("enabled", True)
    }


def generate_targets(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Produce file_sd target groups from a parsed cluster config.

    Returns a list of dicts, each with ``targets`` (list of host:port)
    and ``labels`` (dict with at least ``job`` and ``hostname``).
    """
    targets: list[dict[str, Any]] = []
    ip_map = _node_ip_map(config)
    monitoring = config.get("monitoring", {})

    # --- proxmox-node-exporter: all enabled nodes ---
    node_exporter = monitoring.get("node_exporter", {})
    ne_port = node_exporter.get("port", 9100)
    for name, ip in ip_map.items():
        targets.append({
            "targets": [f"{ip}:{ne_port}"],
            "labels": {"job": "proxmox-node-exporter", "hostname": name},
        })

    # --- proxmox-zfs-exporter: only configured hosts ---
    zfs_cfg = monitoring.get("zfs_exporter", {})
    if zfs_cfg.get("enabled", False):
        zfs_port = zfs_cfg.get("port", 9134)
        for host_name in zfs_cfg.get("hosts", []):
            ip = ip_map.get(host_name)
            if ip is None:
                logger.warning("zfs_exporter host %r not in nodes list, skipping", host_name)
                continue
            targets.append({
                "targets": [f"{ip}:{zfs_port}"],
                "labels": {"job": "proxmox-zfs-exporter", "hostname": host_name},
            })

    # --- proxmox-pve-exporter: single host ---
    pve_cfg = monitoring.get("pve_exporter", {})
    if pve_cfg.get("enabled", False):
        pve_host = pve_cfg.get("host")
        pve_port = pve_cfg.get("port", 9221)
        if pve_host:
            ip = ip_map.get(pve_host)
            if ip is None:
                logger.warning("pve_exporter host %r not in nodes list, skipping", pve_host)
            else:
                targets.append({
                    "targets": [f"{ip}:{pve_port}"],
                    "labels": {"job": "proxmox-pve-exporter", "hostname": pve_host},
                })

    # --- extra targets: explicit host/ip/port entries ---
    for extra in monitoring.get("extra_targets", []):
        job_name = extra.get("job", "extra")
        for t in extra.get("targets", []):
            ip = t.get("ip", "")
            port = t.get("port", 9100)
            host_name = t.get("host", ip)
            if ip:
                targets.append({
                    "targets": [f"{ip}:{port}"],
                    "labels": {"job": job_name, "hostname": host_name},
                })

    return targets


def generate_targets_json(config_path: Path | str) -> str:
    """Return a JSON string of file_sd target groups."""
    config = load_cluster_config(config_path)
    targets = generate_targets(config)
    return json.dumps(targets, indent=2)


def apply_targets_configmap(
    config_path: Path | str,
    kubeconfig: str | None = None,
    namespace: str = "monitoring",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generate targets and apply as a Kubernetes ConfigMap.

    Creates/updates ``prometheus-scrape-targets`` ConfigMap in the
    given namespace containing ``targets.json``.

    Returns a dict with ``success``, ``targets_count``, and optionally
    ``error``.
    """
    targets_json = generate_targets_json(config_path)
    targets = json.loads(targets_json)

    if dry_run:
        return {
            "success": True,
            "targets_count": len(targets),
            "targets_json": targets_json,
            "dry_run": True,
        }

    # Build kubectl command: create configmap --dry-run=client | kubectl apply
    create_cmd = [
        "kubectl", "create", "configmap", "prometheus-scrape-targets",
        f"--from-literal=targets.json={targets_json}",
        f"--namespace={namespace}",
        "--dry-run=client",
        "-o", "yaml",
    ]
    apply_cmd = ["kubectl", "apply", "-f", "-"]

    if kubeconfig:
        create_cmd.extend(["--kubeconfig", kubeconfig])
        apply_cmd.extend(["--kubeconfig", kubeconfig])

    try:
        create_proc = subprocess.run(
            create_cmd, capture_output=True, text=True, check=True,
        )
        apply_proc = subprocess.run(
            apply_cmd, input=create_proc.stdout,
            capture_output=True, text=True, check=True,
        )
        logger.info("ConfigMap applied: %s", apply_proc.stdout.strip())
        return {
            "success": True,
            "targets_count": len(targets),
            "output": apply_proc.stdout.strip(),
        }
    except subprocess.CalledProcessError as exc:
        error_msg = exc.stderr.strip() if exc.stderr else str(exc)
        logger.error("kubectl failed: %s", error_msg)
        return {
            "success": False,
            "targets_count": len(targets),
            "error": error_msg,
        }
