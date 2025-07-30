#!/usr/bin/env python3
"""
src/homelab/uptime_kuma_client.py

Client for programmatically configuring Uptime Kuma monitors using the official API library.
Provides automated monitor setup for homelab infrastructure including Traefik ingress
and MetalLB LoadBalancer services.
"""

import logging
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from uptime_kuma_api import MonitorType, UptimeKumaApi  # type: ignore

# Load environment variables (look for .env in parent directories)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

logger = logging.getLogger(__name__)


class UptimeKumaClient:
    """Client for managing Uptime Kuma monitors using the official API library."""

    def __init__(self, base_url: str, username: str = "", password: str = ""):
        """
        Initialize Uptime Kuma client.

        Args:
            base_url: Base URL of Uptime Kuma instance (e.g., http://192.168.4.100:3001)
            username: Admin username (defaults to env UPTIME_KUMA_USERNAME)
            password: Admin password (defaults to env UPTIME_KUMA_PASSWORD)
        """
        self.base_url = base_url.rstrip("/")
        self.username = username or os.getenv("UPTIME_KUMA_USERNAME", "admin")
        self.password = password or os.getenv("UPTIME_KUMA_PASSWORD", "")
        self.api = UptimeKumaApi(self.base_url)
        self.authenticated = False

    def connect(self) -> bool:
        """
        Connect to Uptime Kuma and authenticate.

        Returns:
            bool: True if connection and authentication successful
        """
        try:
            logger.info(f"Connecting to Uptime Kuma at {self.base_url}")
            self.api.login(self.username, self.password)
            self.authenticated = True
            logger.info("✅ Authentication successful")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Uptime Kuma: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Uptime Kuma."""
        if self.authenticated:
            self.api.disconnect()
            self.authenticated = False

    def monitor_exists(self, name: str) -> bool:
        """
        Check if a monitor with the given name already exists.

        Args:
            name: Monitor name to check

        Returns:
            True if monitor exists, False otherwise
        """
        if not self.authenticated:
            logger.error("Not authenticated to Uptime Kuma")
            return False

        try:
            monitors = self.api.get_monitors()
            for monitor in monitors:
                if monitor.get("name") == name:
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking if monitor exists: {e}")
            return False

    def create_homelab_monitors(self, is_secondary_instance: bool = False) -> List[Dict[str, Any]]:
        """
        Create comprehensive monitoring setup for homelab infrastructure.
        Based on actual Traefik ingress and MetalLB services from GitOps config.

        Args:
            is_secondary_instance: If True, adds 10-minute delay to all monitors
                                 for secondary alerting (prevents alert storms)

        Returns:
            List of created monitor results
        """
        if not self.authenticated:
            logger.error("Not authenticated to Uptime Kuma")
            return []

        results = []

        # Secondary instance settings (10-minute delay for redundant alerting)
        base_interval_multiplier = 2 if is_secondary_instance else 1
        base_retry_delay = 600 if is_secondary_instance else 60  # 10 minutes vs 1 minute
        instance_suffix = " (Secondary)" if is_secondary_instance else ""

        # Define homelab monitors based on actual services
        monitors_config = [
            # Core Infrastructure
            {
                "name": f"OPNsense Gateway{instance_suffix}",
                "type": MonitorType.PING,
                "hostname": "192.168.4.1",
                "interval": 60 * base_interval_multiplier,
                "maxretries": 3,
                "retryInterval": base_retry_delay,
                "description": "OPNsense firewall/router gateway connectivity",
            },
            {
                "name": f"MAAS Server{instance_suffix}",
                "type": MonitorType.HTTP,
                "url": "http://192.168.4.2:5240/MAAS/",
                "method": "GET",
                "interval": 300 * base_interval_multiplier,
                "maxretries": 2,
                "retryInterval": base_retry_delay * 2,
                "description": "MAAS bare metal provisioning server",
            },
            # Proxmox Nodes
            {
                "name": f"Proxmox pve Node{instance_suffix}",
                "type": MonitorType.PING,
                "hostname": "pve.maas",
                "interval": 120 * base_interval_multiplier,
                "maxretries": 3,
                "retryInterval": base_retry_delay,
                "description": "Proxmox pve node connectivity",
            },
            {
                "name": f"Proxmox still-fawn Node{instance_suffix}",
                "type": MonitorType.PING,
                "hostname": "still-fawn.maas",
                "interval": 120 * base_interval_multiplier,
                "maxretries": 3,
                "retryInterval": base_retry_delay,
                "description": "Proxmox still-fawn node connectivity",
            },
            {
                "name": f"Proxmox fun-bedbug Node{instance_suffix}",
                "type": MonitorType.PING,
                "hostname": "fun-bedbug.maas",
                "interval": 120 * base_interval_multiplier,
                "maxretries": 3,
                "retryInterval": base_retry_delay,
                "description": "Proxmox fun-bedbug node connectivity",
            },
            # Kubernetes Services via Traefik Ingress (from actual ingress configs)
            {
                "name": f"Ollama GPU Server{instance_suffix}",
                "type": MonitorType.HTTP,
                "url": "http://ollama.app.homelab",
                "method": "GET",
                "interval": 300 * base_interval_multiplier,
                "maxretries": 2,
                "retryInterval": base_retry_delay * 2,
                "description": "Ollama AI model server via Traefik ingress",
            },
            {
                "name": f"Stable Diffusion WebUI{instance_suffix}",
                "type": MonitorType.HTTP,
                "url": "http://stable-diffusion.app.homelab",
                "method": "GET",
                "interval": 300 * base_interval_multiplier,
                "maxretries": 2,
                "retryInterval": base_retry_delay * 2,
                "description": "Stable Diffusion WebUI via Traefik ingress",
            },
            # MetalLB LoadBalancer Services (based on actual service configs)
            {
                "name": f"Samba File Server{instance_suffix}",
                "type": MonitorType.PORT,
                "hostname": "192.168.4.120",  # Fixed IP from metallb annotation
                "port": 445,
                "interval": 300 * base_interval_multiplier,
                "maxretries": 2,
                "retryInterval": base_retry_delay * 2,
                "description": "Samba SMB file server via MetalLB LoadBalancer",
            },
            # K3s VM Health
            {
                "name": f"K3s VM - still-fawn{instance_suffix}",
                "type": MonitorType.PING,
                "hostname": "k3s-vm-still-fawn",
                "interval": 120 * base_interval_multiplier,
                "maxretries": 3,
                "retryInterval": base_retry_delay,
                "description": "K3s VM on still-fawn node",
            },
            # External Connectivity
            {
                "name": f"Internet - Google DNS{instance_suffix}",
                "type": MonitorType.PING,
                "hostname": "8.8.8.8",
                "interval": 120 * base_interval_multiplier,
                "maxretries": 3,
                "retryInterval": base_retry_delay,
                "description": "Internet connectivity via Google DNS",
            },
            {
                "name": f"Internet - Cloudflare DNS{instance_suffix}",
                "type": MonitorType.PING,
                "hostname": "1.1.1.1",
                "interval": 120 * base_interval_multiplier,
                "maxretries": 3,
                "retryInterval": base_retry_delay,
                "description": "Internet connectivity via Cloudflare DNS",
            },
            {
                "name": f"DNS Resolution Test{instance_suffix}",
                "type": MonitorType.DNS,
                "hostname": "google.com",
                "dns_resolve_server": "8.8.8.8",
                "interval": 300 * base_interval_multiplier,
                "maxretries": 2,
                "retryInterval": base_retry_delay * 2,
                "description": "External DNS resolution capability",
            },
        ]

        # Create monitors
        for monitor_config in monitors_config:
            monitor_name = monitor_config["name"]

            # Check if monitor already exists
            if self.monitor_exists(monitor_name):
                logger.info(f"Monitor '{monitor_name}' already exists, skipping")
                results.append({"name": monitor_name, "status": "already_exists", "monitor_id": None})
                continue

            # Create the monitor
            logger.info(f"Creating monitor: {monitor_name}")
            try:
                # Remove 'name' from config since it's passed separately
                config = monitor_config.copy()
                config.pop("name")

                result = self.api.add_monitor(name=monitor_name, **config)

                if result and result.get("monitorID"):
                    monitor_id = result["monitorID"]
                    logger.info(f"✅ Successfully created monitor '{monitor_name}' with ID {monitor_id}")
                    results.append({"name": monitor_name, "status": "created", "monitor_id": monitor_id})
                else:
                    logger.error(f"❌ Failed to create monitor '{monitor_name}': {result}")
                    results.append({"name": monitor_name, "status": "failed", "monitor_id": None})

            except Exception as e:
                logger.error(f"❌ Error creating monitor '{monitor_name}': {e}")
                results.append({"name": monitor_name, "status": "failed", "monitor_id": None})

        return results

    def __enter__(self) -> "UptimeKumaClient":
        """Context manager entry."""
        if not self.connect():
            raise RuntimeError("Failed to connect to Uptime Kuma")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit with cleanup."""
        self.disconnect()


def setup_monitoring_for_instance(uptime_kuma_url: str, is_secondary: bool = False) -> List[Dict[str, Any]]:
    """
    Set up comprehensive monitoring for a single Uptime Kuma instance.
    Uses environment variables for authentication.

    Args:
        uptime_kuma_url: URL of Uptime Kuma instance
        is_secondary: If True, configures as secondary instance with delayed alerts

    Returns:
        List of monitor creation results
    """
    logger.info(f"Setting up monitoring for {uptime_kuma_url}")

    try:
        with UptimeKumaClient(uptime_kuma_url) as client:
            results = client.create_homelab_monitors(is_secondary_instance=is_secondary)

            # Summary
            created_count = len([r for r in results if r["status"] == "created"])
            existing_count = len([r for r in results if r["status"] == "already_exists"])
            failed_count = len([r for r in results if r["status"] == "failed"])

            logger.info(
                f"Monitor setup complete: {created_count} created, {existing_count} existing, {failed_count} failed"
            )

            return results

    except Exception as e:
        logger.error(f"Failed to setup monitoring for {uptime_kuma_url}: {e}")
        return []


def setup_monitoring_for_all_instances() -> Dict[str, List[Dict[str, Any]]]:
    """
    Set up monitoring for all Uptime Kuma instances from environment.

    Returns:
        Dictionary of instance name to monitor creation results
    """
    # Get instance URLs from environment
    instances = []

    pve_url = os.getenv("UPTIME_KUMA_PVE_URL")
    funbedbug_url = os.getenv("UPTIME_KUMA_FUNBEDBUG_URL")

    if pve_url:
        instances.append({"url": pve_url, "name": "pve", "is_secondary": False})
    if funbedbug_url:
        instances.append({"url": funbedbug_url, "name": "fun-bedbug", "is_secondary": True})

    if not instances:
        logger.warning("No Uptime Kuma instance URLs found in environment")
        return {}

    logger.info(f"Found {len(instances)} Uptime Kuma instances in environment")

    results = {}
    for instance in instances:
        logger.info(f"Setting up monitors for {instance['name']} at {instance['url']}")
        try:
            instance_results = setup_monitoring_for_instance(str(instance["url"]), bool(instance["is_secondary"]))
            results[str(instance["name"])] = instance_results
        except Exception as e:
            logger.error(f"Failed to setup monitoring for {instance['name']}: {e}")
            results[str(instance["name"])] = []

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== Uptime Kuma Monitor Configuration ===")
    print("Using official uptime-kuma-api library")
    print("Configuring monitors for Traefik ingress and MetalLB services")
    print("")

    # Check environment setup
    username = os.getenv("UPTIME_KUMA_USERNAME", "admin")
    password = os.getenv("UPTIME_KUMA_PASSWORD", "")

    if not password:
        print("❌ UPTIME_KUMA_PASSWORD not set in .env file")
        print("Please add your Uptime Kuma credentials to .env:")
        print("UPTIME_KUMA_USERNAME=gshiva")
        print("UPTIME_KUMA_PASSWORD=your_password_here")
        exit(1)

    print(f"✅ Using credentials: {username} / {'*' * len(password)}")
    print("")

    # Auto-configure all instances
    print("=== Configuring all instances ===")
    all_results = setup_monitoring_for_all_instances()

    if not all_results:
        print("❌ No instances found in environment variables")
        exit(1)

    # Display results
    print(f"\n=== Configuration Results ===")
    total_created = 0
    total_existing = 0
    total_failed = 0

    for instance_name, results in all_results.items():
        print(f"\n{instance_name.upper()}:")
        for result in results:
            status_icon = (
                "✅" if result["status"] == "created" else ("ℹ️" if result["status"] == "already_exists" else "❌")
            )
            print(f"  {status_icon} {result['name']}: {result['status']}")

            if result["status"] == "created":
                total_created += 1
            elif result["status"] == "already_exists":
                total_existing += 1
            elif result["status"] == "failed":
                total_failed += 1

    print(f"\n🎉 Monitor configuration complete!")
    print(f"📊 Summary: {total_created} created, {total_existing} existing, {total_failed} failed")
    print(f"\n📝 Next steps:")
    print("1. Verify monitors are working in Uptime Kuma web interfaces")
    print("2. ✅ Home Assistant notifications already configured")
    print("3. ✅ Yahoo email notifications already configured")
    print("4. Test alert notifications by stopping a service")
    print("5. Monitor MetalLB LoadBalancer IP assignments")
    print("6. Check Traefik ingress routing health")
