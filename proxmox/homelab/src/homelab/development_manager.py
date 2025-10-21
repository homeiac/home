#!/usr/bin/env python3
"""
src/homelab/development_manager.py

Manages development environment deployments including Webtop containers.
Provides declarative configuration and idempotent deployment of development services.
"""

import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from homelab.config import Config
from homelab.proxmox_api import ProxmoxAPI

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class DevelopmentManager:
    """
    Manages development environment deployments in a declarative way.
    
    Handles:
    - LXC container verification (assumes already created)
    - ZFS dataset configuration for external storage
    - Docker container deployment with proper volume mappings
    - Development tool installation and configuration
    """

    def __init__(self) -> None:
        """Initialize DevelopmentManager with configuration from environment."""
        self.proxmox_api = ProxmoxAPI()
        
        # Webtop configuration from environment
        self.webtop_config = {
            'lxc_id': os.getenv('WEBTOP_LXC_ID', '104'),
            'hostname': os.getenv('WEBTOP_HOSTNAME', 'docker-webtop'),
            'proxmox_node': os.getenv('WEBTOP_PROXMOX_NODE', 'still-fawn'),
            'zfs_dataset': os.getenv('WEBTOP_ZFS_DATASET', 'local-2TB-zfs/dev-workspace'),
            'zfs_mount': os.getenv('WEBTOP_ZFS_MOUNT', '/data/dev-workspace'),
            'lxc_mount': os.getenv('WEBTOP_LXC_MOUNT', '/home/devdata'),
            'docker_image': os.getenv('WEBTOP_DOCKER_IMAGE', 'lscr.io/linuxserver/webtop:ubuntu-xfce'),
            'timezone': os.getenv('WEBTOP_TIMEZONE', 'America/Los_Angeles'),
            'http_port': os.getenv('WEBTOP_HTTP_PORT', '3000'),
            'https_port': os.getenv('WEBTOP_HTTPS_PORT', '3001'),
            'puid': os.getenv('WEBTOP_PUID', '1000'),
            'pgid': os.getenv('WEBTOP_PGID', '1000'),
        }

    def _run_ssh_command(self, node: str, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute command via SSH on Proxmox node."""
        ssh_cmd = ['ssh', f'root@{node}.maas', command]
        
        try:
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
            return {
                'returncode': result.returncode,
                'stdout': result.stdout.strip(),
                'stderr': result.stderr.strip(),
                'success': result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            logger.error(f"SSH command timeout after {timeout}s: {command}")
            return {'returncode': -1, 'stdout': '', 'stderr': 'Timeout', 'success': False}
        except Exception as e:
            logger.error(f"SSH command failed: {e}")
            return {'returncode': -1, 'stdout': '', 'stderr': str(e), 'success': False}

    def verify_lxc_container(self) -> Dict[str, Any]:
        """
        Verify that the LXC container exists and is properly configured.
        This assumes the container was already created using PVE Helper Scripts.
        """
        logger.info(f"🔍 Verifying LXC container {self.webtop_config['lxc_id']}...")
        
        node = self.webtop_config['proxmox_node']
        lxc_id = self.webtop_config['lxc_id']
        
        # Check if container exists
        result = self._run_ssh_command(node, f"pct status {lxc_id}")
        if not result['success']:
            logger.error(f"❌ LXC container {lxc_id} not found on {node}")
            return {'status': 'failed', 'error': f'Container {lxc_id} not found'}
        
        # Check if container is running
        if 'running' not in result['stdout']:
            logger.info(f"🔄 Starting LXC container {lxc_id}...")
            start_result = self._run_ssh_command(node, f"pct start {lxc_id}")
            if not start_result['success']:
                logger.error(f"❌ Failed to start container {lxc_id}")
                return {'status': 'failed', 'error': f'Failed to start container {lxc_id}'}
            
            # Wait for container to start
            time.sleep(5)
        
        # Verify Docker is available in container
        docker_check = self._run_ssh_command(node, f"pct exec {lxc_id} -- docker --version")
        if not docker_check['success']:
            logger.error(f"❌ Docker not available in container {lxc_id}")
            return {'status': 'failed', 'error': 'Docker not available in container'}
        
        logger.info(f"✅ LXC container {lxc_id} verified and running")
        return {'status': 'success', 'container_id': lxc_id}

    def configure_zfs_storage(self) -> Dict[str, Any]:
        """Configure ZFS dataset and mount points for external storage."""
        logger.info(f"💾 Configuring ZFS storage for development data...")
        
        node = self.webtop_config['proxmox_node']
        dataset = self.webtop_config['zfs_dataset']
        mount_point = self.webtop_config['zfs_mount']
        lxc_id = self.webtop_config['lxc_id']
        lxc_mount = self.webtop_config['lxc_mount']
        
        # Check if ZFS dataset exists
        zfs_check = self._run_ssh_command(node, f"zfs list {dataset}")
        if not zfs_check['success']:
            logger.info(f"📁 Creating ZFS dataset {dataset}...")
            create_result = self._run_ssh_command(
                node, 
                f"zfs create -o mountpoint={mount_point} {dataset}"
            )
            if not create_result['success']:
                logger.error(f"❌ Failed to create ZFS dataset: {create_result['stderr']}")
                return {'status': 'failed', 'error': f'Failed to create ZFS dataset: {create_result["stderr"]}'}
        
        # Create directory structure
        logger.info(f"📂 Setting up directory structure...")
        mkdir_result = self._run_ssh_command(
            node,
            f"mkdir -p {mount_point}/{{webtop-config,webtop-home,projects,shared}}"
        )
        if not mkdir_result['success']:
            logger.warning(f"⚠️ Directory creation warning: {mkdir_result['stderr']}")
        
        # Set proper ownership for LXC UID mapping (100000 + 1000 = 101000)
        chown_result = self._run_ssh_command(
            node,
            f"chown -R 101000:101000 {mount_point}/"
        )
        if not chown_result['success']:
            logger.warning(f"⚠️ Ownership setting warning: {chown_result['stderr']}")
        
        # Check if LXC mount point is configured
        config_check = self._run_ssh_command(node, f"pct config {lxc_id} | grep 'mp0:'")
        if not config_check['success'] or lxc_mount not in config_check['stdout']:
            logger.info(f"🔗 Configuring LXC mount point...")
            
            # Stop container to modify config
            self._run_ssh_command(node, f"pct stop {lxc_id}")
            
            # Add mount point
            mount_result = self._run_ssh_command(
                node,
                f"pct set {lxc_id} -mp0 {mount_point},mp={lxc_mount},shared=1"
            )
            if not mount_result['success']:
                logger.error(f"❌ Failed to set mount point: {mount_result['stderr']}")
                return {'status': 'failed', 'error': f'Failed to set mount point: {mount_result["stderr"]}'}
            
            # Start container
            start_result = self._run_ssh_command(node, f"pct start {lxc_id}")
            if not start_result['success']:
                logger.error(f"❌ Failed to restart container: {start_result['stderr']}")
                return {'status': 'failed', 'error': f'Failed to restart container: {start_result["stderr"]}'}
            
            # Wait for container to start
            time.sleep(5)
        
        # Verify mount is accessible inside container
        mount_verify = self._run_ssh_command(node, f"pct exec {lxc_id} -- ls -la {lxc_mount}/")
        if not mount_verify['success']:
            logger.error(f"❌ Mount point not accessible in container")
            return {'status': 'failed', 'error': 'Mount point not accessible in container'}
        
        logger.info(f"✅ ZFS storage configured successfully")
        return {'status': 'success', 'dataset': dataset, 'mount_point': mount_point}

    def deploy_webtop_container(self) -> Dict[str, Any]:
        """Deploy Webtop Docker container with proper configuration."""
        logger.info(f"🚀 Deploying Webtop container...")
        
        node = self.webtop_config['proxmox_node']
        lxc_id = self.webtop_config['lxc_id']
        lxc_mount = self.webtop_config['lxc_mount']
        
        # Check if Webtop container already exists
        container_check = self._run_ssh_command(
            node, 
            f"pct exec {lxc_id} -- docker ps -a --format '{{{{.Names}}}}' | grep '^webtop$'"
        )
        
        if container_check['success'] and 'webtop' in container_check['stdout']:
            logger.info(f"🔍 Webtop container already exists, checking status...")
            
            # Check if it's running
            running_check = self._run_ssh_command(
                node,
                f"pct exec {lxc_id} -- docker ps --format '{{{{.Names}}}}' | grep '^webtop$'"
            )
            
            if running_check['success'] and 'webtop' in running_check['stdout']:
                logger.info(f"✅ Webtop container already running")
                return {'status': 'success', 'action': 'already_running'}
            else:
                logger.info(f"🔄 Starting existing Webtop container...")
                start_result = self._run_ssh_command(
                    node,
                    f"pct exec {lxc_id} -- docker start webtop"
                )
                if start_result['success']:
                    logger.info(f"✅ Webtop container started")
                    return {'status': 'success', 'action': 'started'}
                else:
                    logger.warning(f"⚠️ Failed to start existing container, will recreate")
                    # Remove failed container
                    self._run_ssh_command(node, f"pct exec {lxc_id} -- docker rm webtop")
        
        # Deploy new Webtop container
        logger.info(f"📦 Creating new Webtop container...")
        
        docker_run_cmd = f'''pct exec {lxc_id} -- docker run -d \\
  --name=webtop \\
  --security-opt seccomp=unconfined \\
  -e PUID={self.webtop_config['puid']} \\
  -e PGID={self.webtop_config['pgid']} \\
  -e TZ={self.webtop_config['timezone']} \\
  -e SUBFOLDER=/ \\
  -e TITLE=Webtop \\
  -p {self.webtop_config['http_port']}:{self.webtop_config['http_port']} \\
  -p {self.webtop_config['https_port']}:{self.webtop_config['https_port']} \\
  -v {lxc_mount}/webtop-config:/config \\
  -v {lxc_mount}/webtop-home:/home/abc \\
  -v {lxc_mount}/projects:/home/abc/projects \\
  -v {lxc_mount}/shared:/home/abc/shared \\
  --restart unless-stopped \\
  {self.webtop_config['docker_image']}'''
        
        deploy_result = self._run_ssh_command(node, docker_run_cmd, timeout=120)
        if not deploy_result['success']:
            logger.error(f"❌ Failed to deploy Webtop container: {deploy_result['stderr']}")
            return {'status': 'failed', 'error': f'Failed to deploy container: {deploy_result["stderr"]}'}
        
        # Wait for container to start
        logger.info(f"⏳ Waiting for Webtop to initialize...")
        time.sleep(15)
        
        # Verify container is running
        verify_result = self._run_ssh_command(
            node,
            f"pct exec {lxc_id} -- docker ps --format '{{{{.Names}}}}' | grep '^webtop$'"
        )
        
        if not verify_result['success'] or 'webtop' not in verify_result['stdout']:
            logger.error(f"❌ Webtop container failed to start")
            # Get logs for debugging
            logs_result = self._run_ssh_command(node, f"pct exec {lxc_id} -- docker logs webtop --tail 20")
            logger.error(f"Container logs: {logs_result['stdout']}")
            return {'status': 'failed', 'error': 'Container failed to start'}
        
        logger.info(f"✅ Webtop container deployed and running")
        return {'status': 'success', 'action': 'deployed'}

    def verify_webtop_access(self) -> Dict[str, Any]:
        """Verify that Webtop is accessible via HTTPS."""
        logger.info(f"🌐 Verifying Webtop web access...")
        
        hostname = f"{self.webtop_config['hostname']}.maas"
        https_port = self.webtop_config['https_port']
        url = f"https://{hostname}:{https_port}"
        
        # Test HTTPS access
        curl_cmd = f"curl -k -I -m 10 {url}"
        curl_result = self._run_ssh_command(self.webtop_config['proxmox_node'], curl_cmd)
        
        if curl_result['success'] and 'HTTP' in curl_result['stdout']:
            if '200 OK' in curl_result['stdout']:
                logger.info(f"✅ Webtop accessible at {url}")
                return {'status': 'success', 'url': url, 'accessible': True}
            else:
                logger.warning(f"⚠️ Webtop responded but not with 200 OK: {curl_result['stdout']}")
                return {'status': 'partial', 'url': url, 'accessible': False, 'response': curl_result['stdout']}
        else:
            logger.error(f"❌ Webtop not accessible at {url}")
            return {'status': 'failed', 'url': url, 'accessible': False, 'error': curl_result['stderr']}

    def install_development_tools(self) -> Dict[str, Any]:
        """Install essential development tools in Webtop container."""
        logger.info(f"🛠️ Installing development tools in Webtop...")
        
        node = self.webtop_config['proxmox_node']
        lxc_id = self.webtop_config['lxc_id']
        
        tools_to_install = [
            'curl',
            'wget', 
            'git',
            'python3',
            'python3-pip',
            'nodejs',
            'npm',
            'vim',
            'nano',
            'htop',
            'tree',
            'jq',
        ]
        
        # Update package list
        logger.info(f"📦 Updating package list...")
        update_result = self._run_ssh_command(
            node,
            f"pct exec {lxc_id} -- docker exec webtop apt-get update",
            timeout=60
        )
        
        if not update_result['success']:
            logger.warning(f"⚠️ Package update warning: {update_result['stderr']}")
        
        # Install tools
        tools_str = ' '.join(tools_to_install)
        logger.info(f"🔧 Installing tools: {tools_str}")
        
        install_result = self._run_ssh_command(
            node,
            f"pct exec {lxc_id} -- docker exec webtop apt-get install -y {tools_str}",
            timeout=300
        )
        
        if not install_result['success']:
            logger.error(f"❌ Failed to install development tools: {install_result['stderr']}")
            return {'status': 'failed', 'error': f'Tool installation failed: {install_result["stderr"]}'}
        
        # Verify key tools are installed
        verification_commands = [
            'git --version',
            'python3 --version',
            'node --version',
            'npm --version'
        ]
        
        verified_tools = []
        for cmd in verification_commands:
            verify_result = self._run_ssh_command(
                node,
                f"pct exec {lxc_id} -- docker exec webtop {cmd}"
            )
            if verify_result['success']:
                tool_name = cmd.split()[0]
                version = verify_result['stdout'].split('\n')[0] if verify_result['stdout'] else 'installed'
                verified_tools.append(f"{tool_name}: {version}")
            else:
                logger.warning(f"⚠️ Could not verify {cmd}")
        
        logger.info(f"✅ Development tools installed successfully")
        for tool in verified_tools:
            logger.info(f"   - {tool}")
        
        return {'status': 'success', 'installed_tools': verified_tools}

    def deploy_development_environment(self) -> Dict[str, Any]:
        """
        Main method to deploy complete Webtop development environment.
        This method is idempotent and safe to run multiple times.
        """
        logger.info("🎯 Deploying Webtop Development Environment...")
        logger.info("=" * 60)
        
        start_time = time.time()
        results = {}
        
        try:
            # Step 1: Verify LXC container exists and is configured
            step1_result = self.verify_lxc_container()
            results['lxc_verification'] = step1_result
            
            if step1_result['status'] != 'success':
                logger.error("❌ LXC verification failed, stopping deployment")
                return results
            
            # Step 2: Configure ZFS storage and mount points
            step2_result = self.configure_zfs_storage()
            results['zfs_configuration'] = step2_result
            
            if step2_result['status'] != 'success':
                logger.error("❌ ZFS configuration failed, stopping deployment")
                return results
            
            # Step 3: Deploy Webtop Docker container
            step3_result = self.deploy_webtop_container()
            results['webtop_deployment'] = step3_result
            
            if step3_result['status'] != 'success':
                logger.error("❌ Webtop deployment failed, stopping deployment")
                return results
            
            # Step 4: Verify web access
            step4_result = self.verify_webtop_access()
            results['access_verification'] = step4_result
            
            # Step 5: Install development tools (optional - continue even if fails)
            step5_result = self.install_development_tools()
            results['development_tools'] = step5_result
            
            # Calculate summary
            elapsed_time = time.time() - start_time
            results['deployment_summary'] = {
                'status': 'success',
                'elapsed_time_seconds': round(elapsed_time, 2),
                'webtop_url': step4_result.get('url', 'Unknown'),
                'accessible': step4_result.get('accessible', False),
                'tools_installed': step5_result.get('status') == 'success'
            }
            
            logger.info("=" * 60)
            logger.info(f"🎉 Webtop Development Environment Deployed! ({elapsed_time:.1f}s)")
            logger.info("📋 Summary:")
            logger.info(f"   - LXC Container: {self.webtop_config['lxc_id']} on {self.webtop_config['proxmox_node']}")
            logger.info(f"   - ZFS Dataset: {self.webtop_config['zfs_dataset']}")
            logger.info(f"   - Web Access: {step4_result.get('url', 'Unknown')}")
            logger.info(f"   - Accessible: {'✅' if step4_result.get('accessible') else '❌'}")
            logger.info(f"   - Dev Tools: {'✅' if step5_result.get('status') == 'success' else '❌'}")
            
        except Exception as e:
            logger.error(f"❌ Deployment failed: {e}")
            results['deployment_summary'] = {
                'status': 'failed',
                'error': str(e),
                'elapsed_time_seconds': time.time() - start_time
            }
        
        return results

    @classmethod
    def create_or_update_development_environment(cls) -> Dict[str, Any]:
        """
        Class method for easy integration with existing infrastructure code.
        Creates or updates the Webtop development environment idempotently.
        """
        manager = cls()
        return manager.deploy_development_environment()


def main() -> None:
    """Main entry point for development environment deployment."""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--dry-run':
        logger.info("🔍 DRY RUN MODE - would deploy development environment")
        return
    
    manager = DevelopmentManager()
    results = manager.deploy_development_environment()
    
    # Exit with error code if deployment failed
    if results.get('deployment_summary', {}).get('status') != 'success':
        sys.exit(1)


if __name__ == '__main__':
    main()