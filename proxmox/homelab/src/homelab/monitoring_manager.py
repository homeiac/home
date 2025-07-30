#!/usr/bin/env python3
"""
src/homelab/monitoring_manager.py

Declarative management of monitoring infrastructure including Uptime Kuma deployments.
Ensures idempotent operations - running multiple times won't create duplicate instances.
"""

import json
import logging
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import paramiko
import requests

from homelab.config import Config
from homelab.proxmox_api import ProxmoxClient

logger = logging.getLogger(__name__)


def check_network_connectivity() -> bool:
    """
    Check if the current host is connected to the homelab network (192.168.4.x).
    
    Returns:
        bool: True if connected to homelab network, False otherwise
    """
    try:
        # Get all network interfaces and their IP addresses
        result = subprocess.run(['ifconfig'], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            # Try alternative command on Linux
            result = subprocess.run(['ip', 'addr'], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.warning("Could not determine network interfaces")
                return False
        
        output = result.stdout
        
        # Check if any interface has a 192.168.4.x IP address
        import re
        ip_pattern = r'inet (?:addr:)?(\d+\.\d+\.\d+\.\d+)'
        matches = re.findall(ip_pattern, output)
        
        homelab_ips = [ip for ip in matches if ip.startswith('192.168.4.')]
        
        if homelab_ips:
            logger.info(f"Found homelab network IPs: {homelab_ips}")
            return True
        else:
            logger.warning(f"No homelab network (192.168.4.x) IPs found. Available IPs: {matches}")
            return False
            
    except Exception as e:
        logger.error(f"Error checking network connectivity: {e}")
        return False


def validate_network_prerequisites() -> None:
    """
    Validate that all network prerequisites are met before attempting deployment.
    
    Raises:
        RuntimeError: If network prerequisites are not met
    """
    logger.info("Checking network prerequisites...")
    
    if not check_network_connectivity():
        error_msg = """
❌ NETWORK CONNECTIVITY ERROR ❌

The MonitoringManager requires connection to the homelab network (192.168.4.x) 
to communicate with Proxmox nodes.

Current situation:
- No network interface found with IP address in 192.168.4.x range
- Cannot reach Proxmox nodes (pve.maas, fun-bedbug.maas, etc.)

PREREQUISITES:
1. Connect to the homelab network (192.168.4.x subnet)
2. Ensure you can reach Proxmox nodes:
   - ping pve.maas
   - ping fun-bedbug.maas
3. Verify SSH access:
   - ssh root@pve.maas
   - ssh root@fun-bedbug.maas

ALTERNATIVE DEPLOYMENT:
If you cannot connect to the homelab network, you can deploy directly 
on each Proxmox node using the deployment script:

1. Copy script to Proxmox node:
   scp proxmox/homelab/scripts/deploy_uptime_kuma.sh root@NODE:/tmp/
   
2. Run on each node:
   # On pve:
   /tmp/deploy_uptime_kuma.sh 100
   
   # On fun-bedbug:
   /tmp/deploy_uptime_kuma.sh 112

Please resolve network connectivity and try again.
"""
        logger.error("Network prerequisites not met")
        raise RuntimeError(error_msg.strip())
    
    logger.info("✅ Network prerequisites satisfied")


class MonitoringManager:
    """Manages monitoring infrastructure deployment across Proxmox nodes."""

    # Container configuration for monitoring services
    UPTIME_KUMA_CONFIG = {
        "image": "louislam/uptime-kuma:1",
        "name": "uptime-kuma",
        "port": 3001,
        "volume": "uptime-kuma-data",
        "restart_policy": "unless-stopped",
        "healthcheck_path": "/",
        "memory_limit": "512m",
    }

    DOCKER_LXC_CONFIG = {
        "template": "local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst",
        "hostname_template": "docker-{node}",
        "memory": 4096,  # 4GB RAM
        "cores": 2,
        "rootfs_size": "32G",
        "features": ["nest=1", "keyctl=1"],  # Required for Docker
        "unprivileged": True,
        "startup_script": """#!/bin/bash
# Install Docker in LXC container
apt-get update
apt-get install -y ca-certificates curl gnupg lsb-release
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable docker
systemctl start docker
""",
    }

    def __init__(self, node_name: str) -> None:
        """Initialize MonitoringManager for a specific node."""
        self.node_name = node_name
        self.client = ProxmoxClient(node_name)
        self.ssh_client: Optional[paramiko.SSHClient] = None

    def _get_ssh_client(self) -> paramiko.SSHClient:
        """Get SSH client connection to the Proxmox node."""
        if not self.ssh_client:
            import os
            import socket

            ssh_user = os.getenv("SSH_USER", "root")
            ssh_key = os.path.expanduser(os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa"))

            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Try connecting with .maas suffix first, then without
            hostname = self.node_name
            if not hostname.endswith('.maas'):
                hostname = f"{self.node_name}.maas"
                
            try:
                # Resolve hostname to IP for better paramiko compatibility
                resolved_ip = socket.gethostbyname(hostname)
                logger.debug(f"Resolved {hostname} -> {resolved_ip}")
                self.ssh_client.connect(hostname=resolved_ip, username=ssh_user, key_filename=ssh_key, timeout=10)
            except Exception as e:
                logger.debug(f"Failed to connect to {hostname}: {e}")
                # Try without .maas suffix
                if hostname.endswith('.maas'):
                    hostname = self.node_name
                    try:
                        resolved_ip = socket.gethostbyname(hostname)
                        logger.debug(f"Resolved {hostname} -> {resolved_ip}")
                        self.ssh_client.connect(hostname=resolved_ip, username=ssh_user, key_filename=ssh_key, timeout=10)
                    except Exception as e2:
                        logger.debug(f"Failed to connect to {hostname}: {e2}")
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

    def _find_docker_lxc(self) -> Optional[int]:
        """Find existing Docker LXC container on the node using direct SSH approach."""
        return self._find_docker_lxc_ssh_simple()
    
    def _find_docker_lxc_ssh(self) -> Optional[int]:
        """Find Docker LXC container using SSH commands as fallback."""
        try:
            # First ensure we have a working SSH connection
            ssh_client = self._get_ssh_client()
            
            # Get list of all LXC containers
            stdout, stderr, exit_code = self._execute_command("pct list | grep -v VMID | awk '{print $1, $4}'")
            if exit_code != 0:
                logger.warning(f"Failed to list LXC containers via SSH: {stderr}")
                return None
                
            # Check each running container for Docker
            for line in stdout.split('\n'):
                if not line.strip():
                    continue
                    
                parts = line.split()
                if len(parts) >= 2:
                    vmid = parts[0]
                    status = parts[1] if len(parts) > 1 else ""
                    
                    # Only check running containers
                    if status == "running":
                        # Check if Docker is installed
                        docker_stdout, docker_stderr, docker_exit = self._execute_command(
                            f"pct exec {vmid} -- which docker 2>/dev/null"
                        )
                        if docker_exit == 0:
                            logger.info(f"Found Docker in LXC container {vmid}")
                            return int(vmid)
                            
                        # Also check for docker in container name/hostname
                        name_stdout, name_stderr, name_exit = self._execute_command(
                            f"pct config {vmid} | grep hostname | cut -d: -f2 | tr -d ' '"
                        )
                        if name_exit == 0 and "docker" in name_stdout.lower():
                            logger.info(f"Found Docker LXC by hostname: {vmid}")
                            return int(vmid)
                            
        except Exception as e:
            logger.warning(f"SSH-based Docker LXC search failed: {e}")
            
        return None

    def _create_docker_lxc(self) -> int:
        """Create a new Docker LXC container."""
        vmid = self._get_next_available_vmid()
        hostname = self.DOCKER_LXC_CONFIG["hostname_template"].format(node=self.node_name)
        
        logger.info(f"Creating Docker LXC container {vmid} on {self.node_name}")
        
        # Create LXC container
        self.client.proxmox.nodes(self.node_name).lxc.create(
            vmid=vmid,
            ostemplate=self.DOCKER_LXC_CONFIG["template"],
            hostname=hostname,
            memory=self.DOCKER_LXC_CONFIG["memory"],
            cores=self.DOCKER_LXC_CONFIG["cores"],
            rootfs=f"local-zfs:subvol-{vmid}-disk-0,size={self.DOCKER_LXC_CONFIG['rootfs_size']}",
            net0="name=eth0,bridge=vmbr0,dhcp=1",
            features=",".join(self.DOCKER_LXC_CONFIG["features"]),
            unprivileged=1 if self.DOCKER_LXC_CONFIG["unprivileged"] else 0,
        )
        
        # Start the container
        self.client.proxmox.nodes(self.node_name).lxc(vmid).status.start.post()
        
        # Wait for container to be ready
        self._wait_for_container_ready(vmid)
        
        # Install Docker
        self._install_docker_in_lxc(vmid)
        
        return vmid

    def _get_next_available_vmid(self) -> int:
        """Find the next available VMID for LXC containers."""
        used = set()
        for vm in self.client.proxmox.nodes(self.node_name).qemu.get():
            used.add(int(vm["vmid"]))
        for ct in self.client.proxmox.nodes(self.node_name).lxc.get():
            used.add(int(ct["vmid"]))
            
        for candidate in range(100, 999):
            if candidate not in used:
                return candidate
                
        raise RuntimeError("No available VMIDs found")

    def _wait_for_container_ready(self, vmid: int, timeout: int = 300) -> None:
        """Wait for LXC container to be ready for operations."""
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            try:
                status = self.client.proxmox.nodes(self.node_name).lxc(vmid).status.current.get()
                if status.get("status") == "running":
                    # Additional check: can we execute commands?
                    stdout, stderr, exit_code = self._execute_command(f"pct exec {vmid} -- echo 'ready'")
                    if exit_code == 0 and "ready" in stdout:
                        logger.info(f"Container {vmid} is ready")
                        return
            except Exception as e:
                logger.debug(f"Container {vmid} not ready yet: {e}")
                
            time.sleep(5)
            
        raise RuntimeError(f"Container {vmid} did not become ready within {timeout} seconds")

    def _install_docker_in_lxc(self, vmid: int) -> None:
        """Install Docker in the LXC container."""
        logger.info(f"Installing Docker in container {vmid}")
        
        commands = [
            "apt-get update",
            "apt-get install -y ca-certificates curl gnupg lsb-release",
            "mkdir -p /etc/apt/keyrings",
            "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
            'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null',
            "apt-get update",
            "apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin",
            "systemctl enable docker",
            "systemctl start docker",
        ]
        
        for cmd in commands:
            stdout, stderr, exit_code = self._execute_command(f"pct exec {vmid} -- {cmd}")
            if exit_code != 0:
                logger.error(f"Failed to execute '{cmd}': {stderr}")
                raise RuntimeError(f"Docker installation failed at: {cmd}")
                
        # Verify Docker installation
        stdout, stderr, exit_code = self._execute_command(f"pct exec {vmid} -- docker --version")
        if exit_code != 0:
            raise RuntimeError("Docker installation verification failed")
            
        logger.info(f"Docker installed successfully in container {vmid}: {stdout}")

    def _container_exists(self, vmid: int, container_name: str) -> bool:
        """Check if a Docker container exists in the LXC container."""
        stdout, stderr, exit_code = self._execute_command(
            f"pct exec {vmid} -- docker ps -a --filter name={container_name} --format '{{{{.Names}}}}'"
        )
        return exit_code == 0 and container_name in stdout

    def _container_is_running(self, vmid: int, container_name: str) -> bool:
        """Check if a Docker container is running in the LXC container."""
        stdout, stderr, exit_code = self._execute_command(
            f"pct exec {vmid} -- docker ps --filter name={container_name} --format '{{{{.Names}}}}'"
        )
        return exit_code == 0 and container_name in stdout

    def _get_container_ip(self, vmid: int) -> Optional[str]:
        """Get the IP address of the LXC container."""
        try:
            stdout, stderr, exit_code = self._execute_command(
                f"pct exec {vmid} -- ip addr show eth0 | grep 'inet ' | awk '{{print $2}}' | cut -d/ -f1"
            )
            if exit_code == 0 and stdout:
                return stdout
        except Exception as e:
            logger.warning(f"Could not get container IP: {e}")
        return None

    def deploy_uptime_kuma(self) -> Dict[str, Any]:
        """Deploy Uptime Kuma in a declarative, idempotent way using SSH-only approach."""
        logger.info(f"Deploying Uptime Kuma on {self.node_name}")
        
        # Use simplified approach to find Docker LXC container
        docker_vmid = self._find_docker_lxc()
        if not docker_vmid:
            raise RuntimeError(f"No Docker LXC container found on {self.node_name}")
            
        logger.info(f"Found Docker LXC {docker_vmid} on {self.node_name}")

        config = self.UPTIME_KUMA_CONFIG
        container_name = config["name"]
        
        # Check if Uptime Kuma container already exists and is running
        if self._container_exists(docker_vmid, container_name):
            if self._container_is_running(docker_vmid, container_name):
                logger.info(f"Uptime Kuma already running in container {docker_vmid}")
                ip = self._get_container_ip(docker_vmid)
                return {
                    "status": "already_running",
                    "vmid": docker_vmid,
                    "container_ip": ip,
                    "url": f"http://{ip}:{config['port']}" if ip else None,
                }
            else:
                # Container exists but not running, start it
                logger.info(f"Starting existing Uptime Kuma container in {docker_vmid}")
                stdout, stderr, exit_code = self._execute_command(f"pct exec {docker_vmid} -- docker start {container_name}")
                if exit_code != 0:
                    logger.error(f"Failed to start container: {stderr}")
        else:
            # Create and start new Uptime Kuma container
            logger.info(f"Creating new Uptime Kuma container in {docker_vmid}")
            docker_cmd = (
                f"docker run -d "
                f"--name {container_name} "
                f"--restart {config['restart_policy']} "
                f"-p {config['port']}:{config['port']} "
                f"-v {config['volume']}:/app/data "
                f"--memory {config['memory_limit']} "
                f"{config['image']}"
            )
            
            stdout, stderr, exit_code = self._execute_command(f"pct exec {docker_vmid} -- {docker_cmd}")
            if exit_code != 0:
                raise RuntimeError(f"Failed to create Uptime Kuma container: {stderr}")
                
            logger.info(f"Uptime Kuma container started: {stdout[:12]}")

        # Wait for container to be healthy
        self._wait_for_uptime_kuma_ready(docker_vmid, config["port"])
        
        ip = self._get_container_ip(docker_vmid)
        return {
            "status": "deployed",
            "vmid": docker_vmid,  
            "container_ip": ip,
            "url": f"http://{ip}:{config['port']}" if ip else None,
        }
    
    def _find_docker_lxc_ssh_simple(self) -> Optional[int]:
        """Simplified SSH-based Docker LXC discovery using known container IDs."""
        # Known Docker LXC containers based on homelab setup
        known_docker_containers = {
            "pve": 100,
            "fun-bedbug": 112,
        }
        
        if self.node_name in known_docker_containers:
            expected_vmid = known_docker_containers[self.node_name]
            logger.info(f"Checking expected Docker LXC {expected_vmid} on {self.node_name}")
            
            try:
                # Check if the container exists and has Docker
                stdout, stderr, exit_code = self._execute_command(f"pct status {expected_vmid}")
                if exit_code == 0 and "running" in stdout:
                    # Verify Docker is installed
                    docker_stdout, docker_stderr, docker_exit = self._execute_command(
                        f"pct exec {expected_vmid} -- which docker 2>/dev/null"
                    )
                    if docker_exit == 0:
                        logger.info(f"Confirmed Docker LXC {expected_vmid} on {self.node_name}")
                        return expected_vmid
                        
            except Exception as e:
                logger.warning(f"Failed to verify expected Docker LXC {expected_vmid}: {e}")
        
        # Fallback to general discovery if known container not found
        return self._find_docker_lxc_ssh()

    def _wait_for_uptime_kuma_ready(self, vmid: int, port: int, timeout: int = 120) -> None:
        """Wait for Uptime Kuma to be ready to accept connections."""
        deadline = time.time() + timeout
        ip = self._get_container_ip(vmid)
        
        if not ip:
            logger.warning("Could not determine container IP for health check")
            time.sleep(30)  # Give it some time to start
            return
            
        url = f"http://{ip}:{port}"
        logger.info(f"Waiting for Uptime Kuma to be ready at {url}")
        
        while time.time() < deadline:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code in [200, 302]:  # 302 is normal for setup redirect
                    logger.info("Uptime Kuma is ready")
                    return
            except requests.RequestException as e:
                logger.debug(f"Uptime Kuma not ready yet: {e}")
                
            time.sleep(5)
            
        logger.warning(f"Uptime Kuma may not be fully ready after {timeout} seconds")

    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current status of monitoring infrastructure on this node."""
        status = {
            "node": self.node_name,
            "docker_lxc": None,
            "uptime_kuma": None,
        }
        
        # Check for Docker LXC
        docker_vmid = self._find_docker_lxc()
        if docker_vmid:
            container_ip = self._get_container_ip(docker_vmid)
            status["docker_lxc"] = {
                "vmid": docker_vmid,
                "ip": container_ip,
                "status": "running",
            }
            
            # Check Uptime Kuma status
            container_name = self.UPTIME_KUMA_CONFIG["name"]
            if self._container_exists(docker_vmid, container_name):
                is_running = self._container_is_running(docker_vmid, container_name)
                port = self.UPTIME_KUMA_CONFIG["port"]
                status["uptime_kuma"] = {
                    "container_name": container_name,
                    "running": is_running,
                    "url": f"http://{container_ip}:{port}" if container_ip and is_running else None,
                }
        
        return status

    def cleanup(self) -> None:
        """Clean up SSH connections."""
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None

    def __enter__(self) -> "MonitoringManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit with cleanup."""
        self.cleanup()


def deploy_monitoring_to_all_nodes() -> List[Dict[str, Any]]:
    """Deploy monitoring infrastructure to all configured nodes."""
    # Check network prerequisites first
    validate_network_prerequisites()
    
    results = []
    
    for node_config in Config.get_nodes():
        node_name = node_config["name"]
        logger.info(f"Deploying monitoring to {node_name}")
        
        try:
            with MonitoringManager(node_name) as manager:
                result = manager.deploy_uptime_kuma()
                result["node"] = node_name
                results.append(result)
                logger.info(f"Successfully deployed to {node_name}: {result['status']}")
        except Exception as e:
            logger.error(f"Failed to deploy monitoring to {node_name}: {e}")
            results.append({
                "node": node_name,
                "status": "failed",
                "error": str(e),
            })
    
    return results


def deploy_monitoring_to_docker_nodes() -> List[Dict[str, Any]]:
    """Deploy monitoring infrastructure specifically to nodes with Docker LXC containers."""
    # Check network prerequisites first
    validate_network_prerequisites()
    
    results = []
    
    # Known Docker LXC deployments based on homelab setup
    docker_nodes = [
        {"name": "pve", "expected_lxc": 100},
        {"name": "fun-bedbug", "expected_lxc": 112},
    ]
    
    for node_config in docker_nodes:
        node_name = node_config["name"]
        logger.info(f"Deploying monitoring to Docker node {node_name}")
        
        try:
            with MonitoringManager(node_name) as manager:
                result = manager.deploy_uptime_kuma()
                result["node"] = node_name
                result["expected_lxc"] = node_config["expected_lxc"]
                results.append(result)
                logger.info(f"Successfully deployed to {node_name}: {result['status']}")
        except Exception as e:
            logger.error(f"Failed to deploy monitoring to {node_name}: {e}")
            results.append({
                "node": node_name,
                "status": "failed",
                "error": str(e),
                "expected_lxc": node_config["expected_lxc"],
            })
    
    return results


def get_monitoring_status_all_nodes() -> List[Dict[str, Any]]:
    """Get monitoring status from all configured nodes."""
    results = []
    
    for node_config in Config.get_nodes():
        node_name = node_config["name"]
        
        try:
            with MonitoringManager(node_name) as manager:
                status = manager.get_monitoring_status()
                results.append(status)
        except Exception as e:
            logger.error(f"Failed to get status from {node_name}: {e}")
            results.append({
                "node": node_name,
                "error": str(e),
            })
    
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=== Uptime Kuma Deployment Manager ===")
    print("")
    print("This script attempts to deploy Uptime Kuma to Docker LXC containers")
    print("across the homelab infrastructure using SSH connections.")
    print("")
    
    # Deploy to Docker nodes specifically (pve and fun-bedbug)
    print("=== Attempting Deployment to Docker Nodes ===")
    results = deploy_monitoring_to_docker_nodes()
    
    print("\n=== Deployment Results ===")
    failed_nodes = []
    for result in results:
        print(f"Node: {result['node']} - Status: {result['status']}")
        if result.get("url"):
            print(f"  URL: {result['url']}")
        if result.get("vmid"):
            print(f"  Docker LXC: {result['vmid']}")
        if result.get("error"):
            print(f"  Error: {result['error']}")
            failed_nodes.append(result['node'])
    
    # Provide alternative deployment instructions if network connectivity fails
    if failed_nodes:
        print(f"\n⚠️  Network connectivity issues detected for nodes: {', '.join(failed_nodes)}")
        print("\n=== Alternative Deployment Method ===")
        print("If SSH connectivity from this machine is limited, you can deploy directly")
        print("on each Proxmox node using the deployment script:")
        print("")
        print("1. Copy the deployment script to each Proxmox node:")
        print("   scp proxmox/homelab/scripts/deploy_uptime_kuma.sh root@NODE.maas:/tmp/")
        print("")
        print("2. Run the script on each node:")
        for node in failed_nodes:
            expected_lxc = {"pve": 100, "fun-bedbug": 112}.get(node, "???")
            print(f"   # On {node}:")
            print(f"   chmod +x /tmp/deploy_uptime_kuma.sh")
            print(f"   /tmp/deploy_uptime_kuma.sh {expected_lxc}")
            print("")
        
        print("3. The script will:")
        print("   - Verify Docker LXC container is running")
        print("   - Deploy/start Uptime Kuma container") 
        print("   - Provide access URL for web interface")
        print("   - Give next steps for configuration")
    else:
        print("\n✅ All deployments successful!")
        
    print(f"\n=== MonitoringManager Class Available ===")
    print("You can also use the MonitoringManager class directly:")
    print("")
    print("from homelab.monitoring_manager import MonitoringManager")
    print("with MonitoringManager('node-name') as manager:")
    print("    result = manager.deploy_uptime_kuma()")
    print("    print(f'Deployed: {result}')")