#!/usr/bin/env python3
"""
src/homelab/infrastructure_orchestrator.py

Idempotent infrastructure orchestrator that reads from .env and ensures:
1. K3s VMs are provisioned and registered in MAAS
2. Critical services (Uptime Kuma) are registered in MAAS  
3. Monitoring is synchronized across all instances
4. Documentation is generated from current state

This is the "single script" that maintains homelab consistency.
"""

import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv

from homelab.config import Config
from homelab.uptime_kuma_client import UptimeKumaClient
from homelab.vm_manager import VMManager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class InfrastructureOrchestrator:
    """
    Orchestrates complete homelab infrastructure in an idempotent way.

    Workflow:
    1. Provision K3s VMs (existing vm_manager logic)
    2. Register K3s VMs in MAAS for persistent IPs
    3. Register critical services in MAAS
    4. Update monitoring to use persistent hostnames
    5. Generate documentation from current state
    """

    def __init__(self) -> None:
        self.maas_host = "192.168.4.53"
        self.maas_user = os.getenv("MAAS_USER", "gshiva")
        self.maas_password = os.getenv("MAAS_PASSWORD", "elder137berry")

        # Critical services from .env
        self.critical_services = self._load_critical_services_from_env()

    def _load_critical_services_from_env(self) -> List[Dict[str, str]]:
        """Load critical services configuration from .env file."""
        services = []

        # Load Uptime Kuma instances
        uptime_services = [
            {
                "name": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_NAME", "uptime-kuma-pve"),
                "mac": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_MAC", "BC:24:11:B3:D0:40"),
                "host_node": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_HOST_NODE", "pve"),
                "lxc_id": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_LXC_ID", "100"),
                "current_ip": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_CURRENT_IP", "192.168.4.194"),
                "port": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_PORT", "3001"),
                "type": "uptime_kuma",
            },
            {
                "name": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_NAME", "uptime-kuma-fun-bedbug"),
                "mac": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_MAC", "BC:24:11:5F:CD:81"),
                "host_node": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_HOST_NODE", "fun-bedbug"),
                "lxc_id": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_LXC_ID", "112"),
                "current_ip": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_CURRENT_IP", "192.168.4.224"),
                "port": os.getenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_PORT", "3001"),
                "type": "uptime_kuma",
            },
        ]

        services.extend(uptime_services)
        return services

    def _run_maas_command(self, command: str) -> Dict[str, Any]:
        """Execute MAAS CLI command via SSH."""
        ssh_cmd = ["ssh", f"{self.maas_user}@{self.maas_host}", f"echo '{self.maas_password}' | {command}"]

        try:
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"MAAS command failed: {result.stderr}")
                return {}

            if result.stdout.strip():
                import json

                parsed_result: Dict[str, Any] = json.loads(result.stdout)
                return parsed_result
            return {}
        except Exception as e:
            logger.error(f"MAAS command failed: {e}")
            return {}

    def _get_vm_mac_address(self, node_name: str, vm_name: str) -> Optional[str]:
        """Get MAC address of a VM by connecting to Proxmox host."""
        try:
            # Use SSH to get VM MAC address from Proxmox
            ssh_cmd = [
                "ssh",
                f"root@{node_name}.maas",
                f"qm config $(qm list | grep '{vm_name}' | awk '{{print $1}}') | grep 'net0:' | grep -o 'macaddr=[^,]*' | cut -d'=' -f2",
            ]

            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0 and result.stdout.strip():
                mac = result.stdout.strip().upper()
                logger.info(f"Found MAC address for {vm_name}: {mac}")
                return mac
        except Exception as e:
            logger.warning(f"Could not get MAC address for {vm_name}: {e}")

        return None

    def _check_maas_device_exists(self, hostname: str) -> bool:
        """Check if device already exists in MAAS."""
        devices_result: Union[Dict[str, Any], List[Dict[str, Any]]] = self._run_maas_command("maas admin devices read")
        if not devices_result:
            return False

        # MAAS returns a list of device dictionaries
        if isinstance(devices_result, list):
            devices = devices_result
        else:
            # If devices_result is a dict, it's likely an error response
            return False

        for device in devices:
            if device.get("hostname") == hostname:
                return True
        return False

    def _register_device_in_maas(self, name: str, mac_address: str, description: str = "") -> bool:
        """Register a device in MAAS for persistent IP/DNS."""
        if self._check_maas_device_exists(name):
            logger.info(f"Device {name} already exists in MAAS")
            return True

        logger.info(f"Registering device in MAAS: {name} ({mac_address})")

        command = f"maas admin devices create " f"hostname={name} " f"mac_addresses={mac_address} " f"domain=0"

        result = self._run_maas_command(command)

        if result and result.get("hostname") == name:
            logger.info(f"✅ Successfully registered {name} in MAAS")
            if description:
                # Try to update description
                system_id = result.get("system_id")
                if system_id:
                    desc_cmd = f"maas admin device update {system_id} description='{description}'"
                    self._run_maas_command(desc_cmd)
            return True
        else:
            logger.error(f"❌ Failed to register {name} in MAAS")
            return False

    def step1_provision_k3s_vms(self) -> Dict[str, Any]:
        """Step 1: Provision K3s VMs using existing vm_manager logic."""
        logger.info("🚀 Step 1: Provisioning K3s VMs...")

        try:
            # Use existing VMManager to create K3s VMs
            VMManager.create_or_update_vm()

            # Get list of created/existing VMs
            k3s_vms = []
            for node in Config.get_nodes():
                vm_name = Config.VM_NAME_TEMPLATE.format(node=node["name"])
                k3s_vms.append(
                    {"name": vm_name, "node": node["name"], "hostname": vm_name}  # This will become FQDN in MAAS
                )

            logger.info(f"✅ Step 1 complete: {len(k3s_vms)} K3s VMs processed")
            return {"k3s_vms": k3s_vms, "status": "success"}

        except Exception as e:
            logger.error(f"❌ Step 1 failed: {e}")
            return {"status": "failed", "error": str(e)}

    def step2_register_k3s_vms_in_maas(self, k3s_vms: List[Dict[str, str]]) -> Dict[str, Any]:
        """Step 2: Register K3s VMs in MAAS for persistent IPs."""
        logger.info("📝 Step 2: Registering K3s VMs in MAAS...")

        registered = 0
        failed = 0

        for vm_info in k3s_vms:
            vm_name = vm_info["name"]
            node_name = vm_info["node"]

            # Get MAC address of the VM
            mac_address = self._get_vm_mac_address(node_name, vm_name)
            if not mac_address:
                logger.warning(f"Could not get MAC address for {vm_name}, skipping MAAS registration")
                failed += 1
                continue

            # Register in MAAS
            description = f"K3s VM on {node_name} node (auto-registered)"
            if self._register_device_in_maas(vm_name, mac_address, description):
                registered += 1
            else:
                failed += 1

        logger.info(f"✅ Step 2 complete: {registered} VMs registered, {failed} failed")
        return {"registered": registered, "failed": failed, "status": "success"}

    def step3_register_critical_services_in_maas(self) -> Dict[str, Any]:
        """Step 3: Register critical services (Uptime Kuma) in MAAS."""
        logger.info("🔧 Step 3: Registering critical services in MAAS...")

        registered = 0
        failed = 0

        for service in self.critical_services:
            name = service["name"]
            mac = service["mac"]
            service_type = service["type"]
            host_node = service["host_node"]

            description = f"{service_type.title()} service on {host_node} (auto-registered)"

            if self._register_device_in_maas(name, mac, description):
                registered += 1
            else:
                failed += 1

        logger.info(f"✅ Step 3 complete: {registered} services registered, {failed} failed")
        return {"registered": registered, "failed": failed, "status": "success"}

    def step4_update_monitoring(self) -> Dict[str, Any]:
        """Step 4: Update monitoring to use persistent hostnames."""
        logger.info("📊 Step 4: Updating monitoring configuration...")

        # Get Uptime Kuma instance URLs (now using .maas hostnames)
        uptime_instances = []
        for service in self.critical_services:
            if service["type"] == "uptime_kuma":
                hostname = f"{service['name']}.maas"
                port = service["port"]
                url = f"http://{hostname}:{port}"
                uptime_instances.append(url)

        updated_instances = 0
        failed_instances = 0

        # Update each Uptime Kuma instance
        for url in uptime_instances:
            try:
                logger.info(f"Updating monitoring for {url}")
                client = UptimeKumaClient(url)

                if client.connect():
                    # Run idempotent monitor creation/update
                    results = client.create_homelab_monitors(is_secondary_instance=False)

                    # Count results
                    created = len([r for r in results if r.get("status") == "created"])
                    updated = len([r for r in results if r.get("status") == "updated"])
                    up_to_date = len([r for r in results if r.get("status") == "up_to_date"])

                    logger.info(f"  - {created} monitors created, {updated} updated, {up_to_date} up-to-date")
                    client.disconnect()
                    updated_instances += 1
                else:
                    logger.error(f"Could not connect to {url}")
                    failed_instances += 1

            except Exception as e:
                logger.error(f"Failed to update monitoring for {url}: {e}")
                failed_instances += 1

        logger.info(f"✅ Step 4 complete: {updated_instances} instances updated, {failed_instances} failed")
        return {"updated": updated_instances, "failed": failed_instances, "status": "success"}

    def step5_generate_documentation(self) -> Dict[str, Any]:
        """Step 5: Generate documentation from current infrastructure state."""
        logger.info("📚 Step 5: Generating documentation...")

        # This is a placeholder for documentation generation
        # In the future, this would:
        # 1. Scan current infrastructure state
        # 2. Generate network diagrams
        # 3. Update service inventory
        # 4. Create deployment documentation

        logger.info("✅ Step 5 complete: Documentation generation (placeholder}")
        return {"status": "success", "generated_docs": 0}

    def orchestrate(self) -> Dict[str, Any]:
        """
        Main orchestration method - runs all steps in sequence.
        This is the single script that maintains homelab consistency.
        """
        logger.info("🎯 Starting Infrastructure Orchestration...")
        logger.info("=" * 60)

        start_time = time.time()
        results = {}

        try:
            # Step 1: Provision K3s VMs
            step1_result = self.step1_provision_k3s_vms()
            results["step1_k3s_provisioning"] = step1_result

            if step1_result["status"] != "success":
                logger.error("Step 1 failed, stopping orchestration")
                return results

            # Step 2: Register K3s VMs in MAAS
            k3s_vms = step1_result.get("k3s_vms", [])
            step2_result = self.step2_register_k3s_vms_in_maas(k3s_vms)
            results["step2_k3s_maas_registration"] = step2_result

            # Step 3: Register critical services in MAAS
            step3_result = self.step3_register_critical_services_in_maas()
            results["step3_critical_services_maas"] = step3_result

            # Step 4: Update monitoring
            step4_result = self.step4_update_monitoring()
            results["step4_monitoring_update"] = step4_result

            # Step 5: Generate documentation
            step5_result = self.step5_generate_documentation()
            results["step5_documentation"] = step5_result

            # Calculate summary
            elapsed_time = time.time() - start_time
            results["orchestration_summary"] = {
                "status": "success",
                "elapsed_time_seconds": round(elapsed_time, 2),
                "total_steps_completed": 5,
            }

            logger.info("=" * 60)
            logger.info(f"🎉 Infrastructure Orchestration Complete! ({elapsed_time:.1f}s)")
            logger.info("📋 Summary:")
            logger.info(f"   - K3s VMs: {len(k3s_vms)} processed")
            logger.info(
                f"   - MAAS registrations: {step2_result.get('registered', 0) + step3_result.get('registered', 0)}"
            )
            logger.info(f"   - Monitoring instances: {step4_result.get('updated', 0)} updated")

        except Exception as e:
            logger.error(f"❌ Orchestration failed: {e}")
            results["orchestration_summary"] = {
                "status": "failed",
                "error": str(e),
                "elapsed_time_seconds": time.time() - start_time,
            }

        return results


def main() -> None:
    """Main entry point for infrastructure orchestration."""
    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run":
        logger.info("🔍 DRY RUN MODE - would execute orchestration")
        return

    orchestrator = InfrastructureOrchestrator()
    results = orchestrator.orchestrate()

    # Exit with error code if orchestration failed
    if results.get("orchestration_summary", {}).get("status") != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
