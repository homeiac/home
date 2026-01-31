#!/usr/bin/env python3
"""
src/homelab/zfs_exporter_manager.py

Declarative management of pdf/zfs_exporter on Proxmox hosts.
Reads configuration from config/cluster.yaml and ensures idempotent operations.

zfs_exporter exposes ZFS pool health metrics (zfs_pool_health, zfs_pool_readonly,
zfs_pool_free_bytes, etc.) that the built-in node_exporter does not provide.

Usage:
    from homelab.zfs_exporter_manager import ZfsExporterManager, apply_from_config

    # Single host
    manager = ZfsExporterManager("still-fawn")
    result = manager.deploy()

    # All hosts from config (idempotent)
    results = apply_from_config()

CLI:
    poetry run homelab monitoring zfs-exporter apply
    poetry run homelab monitoring zfs-exporter status
"""

import logging
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import paramiko
import yaml

logger = logging.getLogger(__name__)

# Default config path relative to package
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "cluster.yaml"

# GitHub release URL template for pdf/zfs_exporter
GITHUB_RELEASE_URL = (
    "https://github.com/pdf/zfs_exporter/releases/download/"
    "v{version}/zfs_exporter-{version}.linux-amd64.tar.gz"
)

SYSTEMD_UNIT = """\
[Unit]
Description=ZFS Exporter for Prometheus
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={binary_path} --web.listen-address=:{port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


def load_cluster_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load cluster configuration from YAML file."""
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Cluster config not found: {path}")

    with open(path) as f:
        return yaml.safe_load(f)


def get_monitoring_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract monitoring configuration from cluster config."""
    return config.get("monitoring", {})


def get_zfs_exporter_hosts(config: Dict[str, Any]) -> List[str]:
    """Get list of hosts that should have zfs_exporter from config."""
    monitoring = get_monitoring_config(config)
    ze_config = monitoring.get("zfs_exporter", {})
    return ze_config.get("hosts", [])


class ZfsExporterManager:
    """Manages pdf/zfs_exporter deployment on Proxmox hosts."""

    def __init__(
        self,
        hostname: str,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        self.hostname = hostname
        self.ssh_client: Optional[paramiko.SSHClient] = None

        # Load config
        if config:
            self._config = config
        else:
            self._config = load_cluster_config(config_path)

        # Extract zfs_exporter settings
        monitoring = get_monitoring_config(self._config)
        ze_config = monitoring.get("zfs_exporter", {})

        self.version = ze_config.get("version", "2.3.11")
        self.port = ze_config.get("port", 9134)
        self.binary_path = ze_config.get("binary_path", "/usr/local/bin/zfs_exporter")
        self.service = ze_config.get("service", "zfs-exporter")

        # Get host IP from nodes config
        self.ip = None
        for node in self._config.get("nodes", []):
            if node.get("name") == hostname:
                self.ip = node.get("ip")
                break

    def _get_ssh_client(self) -> paramiko.SSHClient:
        """Get SSH client connection to the Proxmox host."""
        if not self.ssh_client:
            import os

            ssh_user = os.getenv("SSH_USER", "root")
            ssh_key = os.path.expanduser(os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa"))

            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Try connecting with .maas suffix first, then without
            hostname = self.hostname
            if not hostname.endswith(".maas"):
                hostname = f"{self.hostname}.maas"

            try:
                resolved_ip = socket.gethostbyname(hostname)
                logger.debug(f"Resolved {hostname} -> {resolved_ip}")
                self.ssh_client.connect(
                    hostname=resolved_ip,
                    username=ssh_user,
                    key_filename=ssh_key,
                    timeout=10,
                )
            except Exception as e:
                logger.debug(f"Failed to connect to {hostname}: {e}")
                if hostname.endswith(".maas"):
                    hostname = self.hostname
                    try:
                        resolved_ip = socket.gethostbyname(hostname)
                        logger.debug(f"Resolved {hostname} -> {resolved_ip}")
                        self.ssh_client.connect(
                            hostname=resolved_ip,
                            username=ssh_user,
                            key_filename=ssh_key,
                            timeout=10,
                        )
                    except Exception as e2:
                        raise e2
                else:
                    raise

        return self.ssh_client

    def _execute_command(self, command: str) -> Tuple[str, str, int]:
        """Execute command via SSH and return stdout, stderr, and exit code."""
        ssh = self._get_ssh_client()
        stdin, stdout, stderr = ssh.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        return stdout.read().decode().strip(), stderr.read().decode().strip(), exit_code

    def is_installed(self) -> bool:
        """Check if zfs_exporter binary exists on the host."""
        stdout, stderr, exit_code = self._execute_command(
            f"test -f {self.binary_path} && echo 'installed'"
        )
        return "installed" in stdout

    def is_running(self) -> bool:
        """Check if zfs-exporter service is running."""
        stdout, stderr, exit_code = self._execute_command(
            f"systemctl is-active {self.service}"
        )
        return stdout == "active"

    def is_enabled(self) -> bool:
        """Check if zfs-exporter service is enabled."""
        stdout, stderr, exit_code = self._execute_command(
            f"systemctl is-enabled {self.service}"
        )
        return "enabled" in stdout

    def get_version(self) -> Optional[str]:
        """Get installed zfs_exporter version."""
        stdout, stderr, exit_code = self._execute_command(
            f"{self.binary_path} --version 2>&1 | head -1"
        )
        if exit_code == 0 and stdout:
            # Output format: "zfs_exporter version 2.3.11 ..."
            for part in stdout.split():
                if part and part[0].isdigit():
                    return part
        return None

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of zfs_exporter on this host."""
        status: Dict[str, Any] = {
            "hostname": self.hostname,
            "ip": self.ip,
            "installed": False,
            "running": False,
            "enabled": False,
            "version": None,
            "port": self.port,
            "metrics_available": False,
            "pools": [],
        }

        try:
            status["installed"] = self.is_installed()

            if status["installed"]:
                status["version"] = self.get_version()
                status["running"] = self.is_running()
                status["enabled"] = self.is_enabled()

                # Check if metrics endpoint is responding
                stdout, stderr, exit_code = self._execute_command(
                    f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{self.port}/metrics"
                )
                status["metrics_available"] = stdout == "200"

                # Get ZFS pool names
                stdout, stderr, exit_code = self._execute_command(
                    "zpool list -H -o name 2>/dev/null"
                )
                if exit_code == 0 and stdout:
                    status["pools"] = [p for p in stdout.split("\n") if p]

                # Get pool health if metrics are available
                if status["metrics_available"]:
                    stdout, stderr, exit_code = self._execute_command(
                        f"curl -s http://localhost:{self.port}/metrics"
                        " | grep '^zfs_pool_health'"
                    )
                    if exit_code == 0 and stdout:
                        status["pool_health_raw"] = stdout

        except Exception as e:
            logger.error(f"Failed to get status from {self.hostname}: {e}")
            status["error"] = str(e)

        return status

    def install(self) -> Dict[str, Any]:
        """Download and install zfs_exporter binary."""
        logger.info(f"Installing zfs_exporter {self.version} on {self.hostname}")

        url = GITHUB_RELEASE_URL.format(version=self.version)
        tar_name = f"zfs_exporter-{self.version}.linux-amd64.tar.gz"
        extract_dir = f"zfs_exporter-{self.version}.linux-amd64"

        # Download tarball
        stdout, stderr, exit_code = self._execute_command(
            f"curl -sL -o /tmp/{tar_name} '{url}'"
        )
        if exit_code != 0:
            return {"status": "failed", "error": f"Download failed: {stderr}"}

        # Extract binary
        stdout, stderr, exit_code = self._execute_command(
            f"tar -xzf /tmp/{tar_name} -C /tmp"
        )
        if exit_code != 0:
            return {"status": "failed", "error": f"Extract failed: {stderr}"}

        # Move binary to install path
        stdout, stderr, exit_code = self._execute_command(
            f"mv /tmp/{extract_dir}/zfs_exporter {self.binary_path} && chmod +x {self.binary_path}"
        )
        if exit_code != 0:
            return {"status": "failed", "error": f"Install failed: {stderr}"}

        # Cleanup
        self._execute_command(f"rm -rf /tmp/{tar_name} /tmp/{extract_dir}")

        logger.info(f"Successfully installed zfs_exporter on {self.hostname}")
        return {"status": "installed"}

    def configure(self) -> Dict[str, Any]:
        """Create systemd service unit for zfs_exporter."""
        logger.info(f"Configuring zfs_exporter on {self.hostname}")

        unit_content = SYSTEMD_UNIT.format(
            binary_path=self.binary_path,
            port=self.port,
        )

        # Write systemd unit file
        escaped_content = unit_content.replace("'", "'\\''")
        stdout, stderr, exit_code = self._execute_command(
            f"echo '{escaped_content}' > /etc/systemd/system/{self.service}.service"
        )
        if exit_code != 0:
            return {"status": "failed", "error": f"Failed to write unit file: {stderr}"}

        # Reload systemd
        stdout, stderr, exit_code = self._execute_command("systemctl daemon-reload")
        if exit_code != 0:
            return {"status": "failed", "error": f"systemctl daemon-reload failed: {stderr}"}

        logger.info(f"Successfully configured zfs_exporter on {self.hostname}")
        return {"status": "configured"}

    def enable_and_start(self) -> Dict[str, Any]:
        """Enable and start zfs-exporter service."""
        logger.info(f"Enabling and starting zfs_exporter on {self.hostname}")

        # Enable service
        stdout, stderr, exit_code = self._execute_command(
            f"systemctl enable {self.service}"
        )
        if exit_code != 0:
            return {"status": "failed", "error": f"systemctl enable failed: {stderr}"}

        # Restart to pick up any config changes
        stdout, stderr, exit_code = self._execute_command(
            f"systemctl restart {self.service}"
        )
        if exit_code != 0:
            return {"status": "failed", "error": f"systemctl restart failed: {stderr}"}

        logger.info(f"Successfully started zfs_exporter on {self.hostname}")
        return {"status": "started"}

    def deploy(self) -> Dict[str, Any]:
        """
        Deploy zfs_exporter in a declarative, idempotent way.

        Returns:
            Dict with deployment status and details
        """
        logger.info(f"Deploying zfs_exporter to {self.hostname}")

        result: Dict[str, Any] = {
            "hostname": self.hostname,
            "status": "unknown",
            "actions": [],
        }

        try:
            # Check current state
            if self.is_installed():
                result["actions"].append("already_installed")
                logger.info(f"zfs_exporter already installed on {self.hostname}")
            else:
                # Install
                install_result = self.install()
                if install_result["status"] == "failed":
                    result["status"] = "failed"
                    result["error"] = install_result["error"]
                    return result
                result["actions"].append("installed")

            # Configure
            config_result = self.configure()
            if config_result["status"] == "failed":
                result["status"] = "failed"
                result["error"] = config_result["error"]
                return result
            result["actions"].append("configured")

            # Enable and start
            start_result = self.enable_and_start()
            if start_result["status"] == "failed":
                result["status"] = "failed"
                result["error"] = start_result["error"]
                return result
            result["actions"].append("enabled_and_started")

            # Verify deployment
            status = self.get_status()
            result["version"] = status.get("version")
            result["metrics_available"] = status.get("metrics_available")
            result["pools"] = status.get("pools", [])

            if status["running"] and status["metrics_available"]:
                result["status"] = "success"
                logger.info(f"zfs_exporter deployed successfully on {self.hostname}")
            else:
                result["status"] = "partial"
                result["warning"] = "Service started but metrics may not be fully available"

        except Exception as e:
            logger.error(f"Failed to deploy zfs_exporter to {self.hostname}: {e}")
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    def cleanup(self) -> None:
        """Clean up SSH connections."""
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None

    def __enter__(self) -> "ZfsExporterManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit with cleanup."""
        self.cleanup()


def apply_from_config(config_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Deploy zfs_exporter to all configured hosts from cluster.yaml.

    This is the main idempotent entry point - safe to run multiple times.

    Args:
        config_path: Optional path to cluster.yaml

    Returns:
        List of deployment results per host
    """
    config = load_cluster_config(config_path)
    monitoring = get_monitoring_config(config)

    # Check if zfs_exporter is enabled in config
    ze_config = monitoring.get("zfs_exporter", {})
    if not ze_config.get("enabled", True):
        logger.info("zfs_exporter disabled in config, skipping")
        return [{"status": "skipped", "reason": "disabled in config"}]

    # Get hosts that should have zfs_exporter
    hosts = get_zfs_exporter_hosts(config)
    if not hosts:
        logger.info("No hosts configured for zfs_exporter")
        return [{"status": "skipped", "reason": "no hosts configured"}]

    results = []

    for hostname in hosts:
        logger.info(f"Applying zfs_exporter to {hostname}")

        try:
            with ZfsExporterManager(hostname, config=config) as manager:
                result = manager.deploy()
                results.append(result)
        except Exception as e:
            logger.error(f"Failed to deploy to {hostname}: {e}")
            results.append({
                "hostname": hostname,
                "status": "failed",
                "error": str(e),
            })

    return results


def get_status_from_config(config_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Get zfs_exporter status from all configured hosts.

    Args:
        config_path: Optional path to cluster.yaml

    Returns:
        List of status dicts per host
    """
    config = load_cluster_config(config_path)
    hosts = get_zfs_exporter_hosts(config)
    results = []

    for hostname in hosts:
        try:
            with ZfsExporterManager(hostname, config=config) as manager:
                status = manager.get_status()
                results.append(status)
        except Exception as e:
            logger.error(f"Failed to get status from {hostname}: {e}")
            # Look up IP from config
            ip = None
            for node in config.get("nodes", []):
                if node.get("name") == hostname:
                    ip = node.get("ip")
                    break
            results.append({
                "hostname": hostname,
                "ip": ip,
                "error": str(e),
            })

    return results


def print_status_table(results: List[Dict[str, Any]]) -> None:
    """Print status results as a formatted table."""
    print("\n" + "=" * 90)
    print(f"{'Host':<20} {'IP':<16} {'Status':<10} {'Version':<12} {'Pools'}")
    print("=" * 90)

    for r in results:
        hostname = r.get("hostname", "unknown")
        ip = r.get("ip", "N/A")

        if r.get("error"):
            print(f"{hostname:<20} {ip:<16} {'ERROR':<10} {'-':<12} {r['error']}")
        elif r.get("running"):
            version = (r.get("version") or "?")[:10]
            pools = ", ".join(r.get("pools", []))[:30]
            print(f"{hostname:<20} {ip:<16} {'OK':<10} {version:<12} {pools}")
        elif r.get("installed"):
            print(f"{hostname:<20} {ip:<16} {'STOPPED':<10} {(r.get('version') or '?'):<12} -")
        else:
            print(f"{hostname:<20} {ip:<16} {'MISSING':<10} {'-':<12} -")

    print("=" * 90)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Manage zfs_exporter on Proxmox hosts (reads config/cluster.yaml)"
    )
    parser.add_argument(
        "action",
        choices=["apply", "status"],
        help="apply: deploy to all hosts, status: show current state",
    )
    parser.add_argument("--host", "-H", help="Specific host (default: all from config)")
    parser.add_argument("--config", "-c", help="Path to cluster.yaml")

    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None

    if args.action == "apply":
        if args.host:
            with ZfsExporterManager(args.host, config_path=config_path) as manager:
                result = manager.deploy()
                print(f"\n{args.host}: {result['status']}")
                if result.get("pools"):
                    print(f"  pools: {', '.join(result['pools'])}")
                if result.get("error"):
                    print(f"  error: {result['error']}")
        else:
            print("Applying zfs_exporter to all hosts from config...")
            results = apply_from_config(config_path)
            print_status_table(results)

            success = sum(1 for r in results if r.get("status") == "success")
            failed = sum(1 for r in results if r.get("status") == "failed")
            print(f"\nSummary: {success} success, {failed} failed, {len(results)} total")

    elif args.action == "status":
        if args.host:
            with ZfsExporterManager(args.host, config_path=config_path) as manager:
                status = manager.get_status()
                print(f"\n{args.host}:")
                print(f"  ip: {status.get('ip', 'N/A')}")
                print(f"  installed: {status['installed']}")
                print(f"  running: {status['running']}")
                print(f"  version: {status.get('version', 'N/A')}")
                print(f"  metrics: {status['metrics_available']}")
                print(f"  pools: {', '.join(status.get('pools', []))}")
        else:
            results = get_status_from_config(config_path)
            print_status_table(results)
