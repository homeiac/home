#!/usr/bin/env python3
"""Collect bounded aggregate CPU/runtime readiness, without inference or device tests."""

import argparse
import ipaddress
import json
import logging
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


class ProbeFailure(Exception):
    """Carry an allowlisted diagnostic category without private remote output."""


def host_names(inventory: Path) -> dict[str, str]:
    """Accept only physical Proxmox names from the repository source of truth."""
    section, names = "", {}
    for line in inventory.read_text().splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[proxmox]" and line and not line.startswith("#"):
            name = line.partition("#")[2].strip()
            if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
                raise ValueError("Inventory needs a unique physical hostname")
            names[name] = str(ipaddress.ip_address(line.partition("#")[0].strip()))
    return names


def cpu_sample() -> list[int] | None:
    """Read Linux aggregate accounting, excluding double-counted guest counters."""
    path = Path("/proc/stat")
    if not path.exists():
        return None
    return [int(v) for v in path.read_text().splitlines()[0].split()[1:9]]


def collect() -> dict:
    """Return aggregate host facts; missing platform metrics remain unmeasured."""
    before = cpu_sample()
    time.sleep(1)
    after = cpu_sample()
    busy = None
    if before is not None and after is not None:
        total = sum(after) - sum(before)
        idle = sum(after[3:5]) - sum(before[3:5])
        if total > 0 and 0 <= idle <= total:
            busy = round(100 * (total - idle) / total, 2)
    memory = {}
    path = Path("/proc/meminfo")
    if path.exists():
        for line in path.read_text().splitlines():
            key, value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                memory[key + "_bytes"] = int(value.split()[0]) * 1024
    pressure = {}
    for name in ("cpu", "memory", "io"):
        path = Path("/proc/pressure") / name
        if path.exists():
            pressure[name] = path.read_text().strip()
    guests = None
    if shutil.which("pvesh"):
        result = subprocess.run(
            [
                "pvesh",
                "get",
                "/cluster/resources",
                "--type",
                "vm",
                "--output-format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        rows = [
            r
            for r in json.loads(result.stdout)
            if r.get("node") == platform.node().split(".")[0]
        ]
        guests = {
            "count": len(rows),
            "running": sum(r.get("status") == "running" for r in rows),
            "configured_vcpus": sum(r.get("maxcpu", 0) for r in rows),
            "configured_memory_bytes": sum(r.get("maxmem", 0) for r in rows),
        }
    disk = shutil.disk_usage("/")
    return {
        "observed_ns": time.time_ns(),
        "system": platform.system(),
        "architecture": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "load_average": list(os.getloadavg()),
        "cpu_busy_percent_1s": busy,
        "memory": memory or None,
        "pressure": pressure or None,
        "root_disk_free_bytes": disk.free,
        "root_disk_total_bytes": disk.total,
        "runtime_on_path": {
            name: shutil.which(name) is not None
            for name in (
                "python3",
                "ffmpeg",
                "llama-server",
                "ollama",
                "whisper-cli",
                "docker",
                "containerd",
                "k3s",
                "crictl",
            )
        },
        "guest_allocations": guests,
        "decision": "readiness_only",
        "unmeasured": [
            "application_runtime_and_cgroup_limits",
            "model_fit",
            "source_access_and_transfer",
            "quality",
            "caller_attributed_progress",
            "scheduled_peer_reservations",
            "sustained_headroom",
            "network_and_storage_error_rates",
        ],
    }


def remote(host: str, inventory: Path, guest: bool = False) -> dict:
    """Run this read-only collector over bounded SSH to an inventoried physical host."""
    hosts = host_names(inventory)
    if host not in hosts:
        raise ValueError("Host is not in the physical Proxmox inventory")
    if host == "rapid-civet":
        raise ValueError("Host is intentionally offline; follow its owned revisit")
    source = Path(__file__).read_text()
    vmid = None
    if guest:
        match = re.search(
            r"#\s+k3s-vm-" + re.escape(host) + r"(?:-gpu)?\s+\(VMID\s+(\d+)",
            inventory.read_text(),
        )
        if match is None:
            raise ValueError("No matching K3s guest in inventory")
        vmid = match.group(1)
    remote_command = (
        shlex.join(
            ["qm", "guest", "exec", vmid, "--", "python3", "-c", source, "--collect"]
        )
        if guest
        else "python3 - --collect"
    )
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=1",
        "root@" + host + ".maas",
        remote_command,
    ]
    for attempt in range(2):
        try:
            result = subprocess.run(
                command,
                input=None if guest else source,
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            report = json.loads(result.stdout)
            if guest:
                if not report.get("exited") or report.get("exitcode") != 0:
                    raise ProbeFailure("guest_collector_failed")
                report = json.loads(report["out-data"])
                report["guest_vmid"] = int(vmid)
            return report
        except subprocess.CalledProcessError as error:
            categories = {
                "Could not resolve hostname": "dns_resolution",
                "Permission denied": "ssh_authentication",
                "Host key verification failed": "ssh_host_verification",
                "Connection refused": "ssh_refused",
                "No route to host": "network_route",
                "Connection timed out": "ssh_timeout",
            }
            category = next(
                (v for k, v in categories.items() if k in (error.stderr or "")),
                "remote_collector_failed",
            )
            if category == "dns_resolution" and attempt == 0:
                # Exact inventory address, same SSH alias/configuration and normal
                # host-key verification. Never guess hosts or disable trust checks.
                command[1:1] = ["-o", "HostName=" + hosts[host]]
                continue
            raise ProbeFailure(category) from None
    raise ProbeFailure("ssh_failed")


def main() -> None:
    """Keep credentials, process arguments and remote error text out of receipts/logs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host", help="physical Proxmox inventory name; omit for this computer"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--guest",
        action="store_true",
        help="inspect the inventoried K3s guest through qm guest exec",
    )
    parser.add_argument("--collect", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.collect and args.output is None:
        parser.error("--output is required")
    if args.guest and not args.host:
        parser.error("--guest requires its physical --host")
    try:
        inventory = (
            Path(__file__).resolve().parents[2] / "proxmox/inventory.txt"
            if args.host
            else None
        )
        result = remote(args.host, inventory, args.guest) if args.host else collect()
    except ProbeFailure as error:
        parser.exit(1, "Readiness inspection failed (" + str(error) + ").\n")
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        parser.exit(1, "Readiness inspection failed (" + type(error).__name__ + ").\n")
    if args.collect:
        print(json.dumps(result, sort_keys=True))
        return
    result["pool"] = (args.host or "local") + "/cpu"
    result["scope"] = "guest" if args.guest else "host"
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        "w", dir=args.output.parent, delete=False
    ) as stream:
        json.dump(result, stream, sort_keys=True)
        temporary = stream.name
    os.replace(temporary, args.output)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("%s", json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
