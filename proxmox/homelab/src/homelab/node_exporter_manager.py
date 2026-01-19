#!/usr/bin/env python3
"""
src/homelab/node_exporter_manager.py

Declarative management of Prometheus node-exporter on Proxmox hosts.
Reads configuration from config/cluster.yaml and ensures idempotent operations.

Usage:
    from homelab.node_exporter_manager import NodeExporterManager, apply_from_config

    # Single host
    manager = NodeExporterManager("still-fawn")
    result = manager.deploy()

    # All hosts from config (idempotent)
    results = apply_from_config()

CLI:
    poetry run homelab monitoring apply
    poetry run homelab monitoring status
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


def get_enabled_hosts(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get list of enabled Proxmox hosts from config."""
    nodes = config.get("nodes", [])
    return [n for n in nodes if n.get("enabled", True)]


class NodeExporterManager:
    """Manages Prometheus node-exporter deployment on Proxmox hosts."""

    def __init__(
        self,
        hostname: str,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None
    ) -> None:
        """
        Initialize NodeExporterManager for a specific Proxmox host.

        Args:
            hostname: Proxmox hostname (e.g., 'still-fawn', 'pumped-piglet')
            config: Pre-loaded cluster config (optional)
            config_path: Path to cluster.yaml (optional, uses default)
        """
        self.hostname = hostname
        self.ssh_client: Optional[paramiko.SSHClient] = None

        # Load config
        if config:
            self._config = config
        else:
            self._config = load_cluster_config(config_path)

        # Extract node-exporter settings from monitoring config
        monitoring = get_monitoring_config(self._config)
        ne_config = monitoring.get("node_exporter", {})

        self.package = ne_config.get("package", "prometheus-node-exporter")
        self.service = ne_config.get("service", "prometheus-node-exporter")
        self.port = ne_config.get("port", 9100)
        self.collectors = ne_config.get("collectors", ["hwmon", "thermal_zone"])

        # Get expected sensors for this specific host
        host_sensors = ne_config.get("host_sensors", {})
        self.expected_sensors = host_sensors.get(hostname, [])

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
                    timeout=10
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
                            timeout=10
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
        """Check if node-exporter is installed on the host."""
        stdout, stderr, exit_code = self._execute_command(
            f"dpkg -l | grep -q {self.package} && echo 'installed'"
        )
        return "installed" in stdout

    def is_running(self) -> bool:
        """Check if node-exporter service is running."""
        stdout, stderr, exit_code = self._execute_command(
            f"systemctl is-active {self.service}"
        )
        return "active" in stdout

    def is_enabled(self) -> bool:
        """Check if node-exporter service is enabled."""
        stdout, stderr, exit_code = self._execute_command(
            f"systemctl is-enabled {self.service}"
        )
        return "enabled" in stdout

    def get_version(self) -> Optional[str]:
        """Get installed node-exporter version."""
        stdout, stderr, exit_code = self._execute_command(
            f"dpkg -l {self.package} 2>/dev/null | grep -E '^ii' | awk '{{print $3}}'"
        )
        return stdout if exit_code == 0 and stdout else None

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of node-exporter on this host."""
        status = {
            "hostname": self.hostname,
            "ip": self.ip,
            "installed": False,
            "running": False,
            "enabled": False,
            "version": None,
            "port": self.port,
            "metrics_available": False,
            "hwmon_sensors": [],
            "expected_sensors": self.expected_sensors,
        }

        try:
            status["installed"] = self.is_installed()

            if status["installed"]:
                status["version"] = self.get_version()
                status["running"] = self.is_running()
                status["enabled"] = self.is_enabled()

                # Check if metrics endpoint is responding
                stdout, stderr, exit_code = self._execute_command(
                    f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{status['port']}/metrics"
                )
                status["metrics_available"] = stdout == "200"

                # Get hwmon sensors available
                stdout, stderr, exit_code = self._execute_command(
                    "cat /sys/class/hwmon/hwmon*/name 2>/dev/null | sort -u"
                )
                if exit_code == 0 and stdout:
                    status["hwmon_sensors"] = [s for s in stdout.split("\n") if s]

                # Check if expected sensors are present
                if self.expected_sensors:
                    missing = set(self.expected_sensors) - set(status["hwmon_sensors"])
                    status["missing_sensors"] = list(missing)

        except Exception as e:
            logger.error(f"Failed to get status from {self.hostname}: {e}")
            status["error"] = str(e)

        return status

    def install(self) -> Dict[str, Any]:
        """Install node-exporter package."""
        logger.info(f"Installing node-exporter on {self.hostname}")

        # Update apt cache - use --allow-releaseinfo-change and ignore enterprise repo errors
        # Proxmox hosts without subscription will have 401 errors on enterprise repos
        stdout, stderr, exit_code = self._execute_command(
            "apt-get update -qq 2>&1 | grep -v 'enterprise.proxmox.com' || true"
        )
        # Don't fail on apt-get update errors from enterprise repos

        # Install package
        stdout, stderr, exit_code = self._execute_command(
            f"DEBIAN_FRONTEND=noninteractive apt-get install -y {self.package}"
        )
        if exit_code != 0:
            return {"status": "failed", "error": f"apt-get install failed: {stderr}"}

        logger.info(f"Successfully installed node-exporter on {self.hostname}")
        return {"status": "installed", "output": stdout}

    def configure(self) -> Dict[str, Any]:
        """Configure node-exporter with optimal settings for Proxmox."""
        logger.info(f"Configuring node-exporter on {self.hostname}")

        # Create systemd override directory
        stdout, stderr, exit_code = self._execute_command(
            "mkdir -p /etc/systemd/system/prometheus-node-exporter.service.d"
        )

        # Create override config to enable extra collectors
        # Particularly hwmon for temperature sensors
        override_content = """[Service]
ExecStart=
ExecStart=/usr/bin/prometheus-node-exporter \\
    --collector.filesystem.mount-points-exclude='^/(sys|proc|dev|host|etc)($$|/)' \\
    --collector.hwmon \\
    --web.listen-address=:9100
"""

        # Write override file
        escaped_content = override_content.replace("'", "'\\''")
        stdout, stderr, exit_code = self._execute_command(
            f"echo '{escaped_content}' > /etc/systemd/system/prometheus-node-exporter.service.d/override.conf"
        )
        if exit_code != 0:
            return {"status": "failed", "error": f"Failed to write override: {stderr}"}

        # Reload systemd
        stdout, stderr, exit_code = self._execute_command("systemctl daemon-reload")
        if exit_code != 0:
            return {"status": "failed", "error": f"systemctl daemon-reload failed: {stderr}"}

        logger.info(f"Successfully configured node-exporter on {self.hostname}")
        return {"status": "configured"}

    def enable_and_start(self) -> Dict[str, Any]:
        """Enable and start node-exporter service."""
        logger.info(f"Enabling and starting node-exporter on {self.hostname}")

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

        logger.info(f"Successfully started node-exporter on {self.hostname}")
        return {"status": "started"}

    def deploy(self) -> Dict[str, Any]:
        """
        Deploy node-exporter in a declarative, idempotent way.

        Returns:
            Dict with deployment status and details
        """
        logger.info(f"Deploying node-exporter to {self.hostname}")

        result = {
            "hostname": self.hostname,
            "status": "unknown",
            "actions": [],
        }

        try:
            # Check current state
            if self.is_installed():
                result["actions"].append("already_installed")
                logger.info(f"node-exporter already installed on {self.hostname}")
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
            result["hwmon_sensors"] = status.get("hwmon_sensors", [])

            if status["running"] and status["metrics_available"]:
                result["status"] = "success"
                logger.info(f"node-exporter deployed successfully on {self.hostname}")
            else:
                result["status"] = "partial"
                result["warning"] = "Service started but metrics may not be fully available"

        except Exception as e:
            logger.error(f"Failed to deploy node-exporter to {self.hostname}: {e}")
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    def cleanup(self) -> None:
        """Clean up SSH connections."""
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None

    def __enter__(self) -> "NodeExporterManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit with cleanup."""
        self.cleanup()


def apply_from_config(config_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Deploy node-exporter to all enabled hosts from cluster.yaml config.

    This is the main idempotent entry point - safe to run multiple times.

    Args:
        config_path: Optional path to cluster.yaml

    Returns:
        List of deployment results per host
    """
    config = load_cluster_config(config_path)
    monitoring = get_monitoring_config(config)

    # Check if node_exporter is enabled in config
    ne_config = monitoring.get("node_exporter", {})
    if not ne_config.get("enabled", True):
        logger.info("node_exporter disabled in config, skipping")
        return [{"status": "skipped", "reason": "disabled in config"}]

    # Get enabled hosts
    hosts = get_enabled_hosts(config)
    results = []

    for host in hosts:
        hostname = host["name"]
        logger.info(f"Applying node-exporter to {hostname}")

        try:
            with NodeExporterManager(hostname, config=config) as manager:
                result = manager.deploy()
                results.append(result)
        except Exception as e:
            logger.error(f"Failed to deploy to {hostname}: {e}")
            results.append({
                "hostname": hostname,
                "status": "failed",
                "error": str(e)
            })

    return results


def get_status_from_config(config_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Get node-exporter status from all enabled hosts in config.

    Args:
        config_path: Optional path to cluster.yaml

    Returns:
        List of status dicts per host
    """
    config = load_cluster_config(config_path)
    hosts = get_enabled_hosts(config)
    results = []

    for host in hosts:
        hostname = host["name"]
        try:
            with NodeExporterManager(hostname, config=config) as manager:
                status = manager.get_status()
                results.append(status)
        except Exception as e:
            logger.error(f"Failed to get status from {hostname}: {e}")
            results.append({
                "hostname": hostname,
                "ip": host.get("ip"),
                "error": str(e)
            })

    return results


def print_status_table(results: List[Dict[str, Any]]) -> None:
    """Print status results as a formatted table."""
    print("\n" + "=" * 80)
    print(f"{'Host':<20} {'IP':<16} {'Status':<10} {'Version':<12} {'Sensors'}")
    print("=" * 80)

    for r in results:
        hostname = r.get("hostname", "unknown")
        ip = r.get("ip", "N/A")

        if r.get("error"):
            print(f"{hostname:<20} {ip:<16} {'ERROR':<10} {'-':<12} {r['error']}")
        elif r.get("running"):
            version = r.get("version", "?")[:10]
            sensors = ", ".join(r.get("hwmon_sensors", []))[:30]
            print(f"{hostname:<20} {ip:<16} {'✅ OK':<10} {version:<12} {sensors}")
        elif r.get("installed"):
            print(f"{hostname:<20} {ip:<16} {'⚠️ STOPPED':<10} {r.get('version', '?'):<12} -")
        else:
            print(f"{hostname:<20} {ip:<16} {'❌ MISSING':<10} {'-':<12} -")

    print("=" * 80)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Manage node-exporter on Proxmox hosts (reads config/cluster.yaml)"
    )
    parser.add_argument(
        "action",
        choices=["apply", "status"],
        help="apply: deploy to all hosts, status: show current state"
    )
    parser.add_argument("--host", "-H", help="Specific host (default: all from config)")
    parser.add_argument("--config", "-c", help="Path to cluster.yaml")

    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None

    if args.action == "apply":
        if args.host:
            # Single host
            with NodeExporterManager(args.host, config_path=config_path) as manager:
                result = manager.deploy()
                print(f"\n{args.host}: {result['status']}")
                if result.get("hwmon_sensors"):
                    print(f"  sensors: {', '.join(result['hwmon_sensors'])}")
                if result.get("error"):
                    print(f"  error: {result['error']}")
        else:
            # All hosts from config
            print("Applying node-exporter to all hosts from config...")
            results = apply_from_config(config_path)
            print_status_table(results)

            # Summary
            success = sum(1 for r in results if r.get("status") == "success")
            failed = sum(1 for r in results if r.get("status") == "failed")
            print(f"\nSummary: {success} success, {failed} failed, {len(results)} total")

    elif args.action == "status":
        if args.host:
            with NodeExporterManager(args.host, config_path=config_path) as manager:
                status = manager.get_status()
                print(f"\n{args.host}:")
                print(f"  ip: {status.get('ip', 'N/A')}")
                print(f"  installed: {status['installed']}")
                print(f"  running: {status['running']}")
                print(f"  version: {status.get('version', 'N/A')}")
                print(f"  metrics: {status['metrics_available']}")
                print(f"  sensors: {', '.join(status.get('hwmon_sensors', []))}")
                if status.get("missing_sensors"):
                    print(f"  missing: {', '.join(status['missing_sensors'])}")
        else:
            results = get_status_from_config(config_path)
            print_status_table(results)
