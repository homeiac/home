# VM Provisioning Self-Healing Implementation Plan

**GitHub Issue**: #159
**Created**: 2025-11-12
**Target Completion**: 3-4 weeks (15-20 working days)
**Estimated Effort**: 60-80 person-hours

## Executive Summary

This implementation plan transforms the homelab Python infrastructure system (`proxmox/homelab`) from a basic VM creation tool into a fully idempotent, self-healing platform. The current system fails to handle real-world scenarios like SSL certificate issues, stuck VMs, network validation, and k3s cluster integration. This plan addresses all 7 critical issues identified in the troubleshooting documentation through a phased approach that maintains backward compatibility while adding robust error handling, health checking, and automated cluster management.

The transformation will enable single-command provisioning (`poetry run python -m homelab.main`) that automatically detects unhealthy VMs, recovers from API failures, validates resources, manages k3s cluster membership, and verifies success end-to-end. All changes will maintain 100% test coverage and follow existing code patterns.

## Current Architecture Analysis

### Existing Components

#### `main.py` - Current workflow and gaps
- **Current**: Simple 3-step workflow (ISO download → ISO upload → VM creation)
- **Gaps**: No health checking, no k3s integration, no verification, no error recovery
- **Lines of Code**: 14 (minimal orchestration)

#### `vm_manager.py` - VM lifecycle management capabilities and limitations
- **Capabilities**: VM creation, cloud-init configuration, resource calculation, SSH operations
- **Limitations**: No deletion, no health checking, no pre-flight validation, no idempotency beyond "exists"
- **Lines of Code**: 220 (most complex module)

#### `k3s_migration_manager.py` - K3s operations but not integrated
- **Capabilities**: Complete k3s management (join, label, taint, verify)
- **Problem**: Not integrated into main workflow, designed for migration not provisioning
- **Lines of Code**: 462 (comprehensive but standalone)

#### `proxmox_api.py` - API client with SSL issues
- **Current**: Basic API wrapper with hardcoded `verify_ssl=False`
- **Gaps**: No configuration option, no CLI fallback, no retry logic
- **Lines of Code**: 57 (minimal wrapper)

#### `config.py` - Configuration management
- **Current**: Loads .env variables, manages node configuration
- **Gaps**: Missing k3s configuration, SSL settings, validation
- **Lines of Code**: 78

### Architecture Gaps

1. **No Health Detection**: System cannot detect stuck, failed, or misconfigured VMs
2. **No Lifecycle Management**: Can create but not update, delete, or recreate VMs
3. **No K3s Integration**: VMs created without cluster membership
4. **No Resource Validation**: Assumes bridges, storage, memory always available
5. **No Error Recovery**: API failures abort entire process
6. **No End-to-End Verification**: No confirmation that provisioning succeeded
7. **No Idempotency Beyond "Exists"**: Cannot reconcile partial states

### Dependencies and Constraints

- **Must maintain 100% test coverage** - All new code requires comprehensive unit tests
- **Must be backward compatible** - Existing .env configurations must continue working
- **Must work from both Mac and pve node** - Handle bastion SSH and DNS resolution
- **Must handle SSL certificate issues gracefully** - Self-signed certs are standard
- **Must use Poetry for execution** - No system Python usage
- **Must follow existing patterns** - Static methods, type hints, logging

## Implementation Phases

### Phase 1: Foundation - Health Checking and State Detection
**Duration**: 5-7 days
**Goal**: Add ability to detect VM health, validate resources, and handle API failures

#### Changes Required:

##### 1.1 New Module: `health_checker.py`
**Purpose**: Centralized health checking for VMs and k3s nodes

**New Classes**:
```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
import logging

class VMHealthStatus(Enum):
    """VM health states"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    MISSING = "missing"
    STUCK = "stuck"

@dataclass
class VMHealthReport:
    """Detailed VM health assessment"""
    vmid: int
    name: str
    node: str
    status: VMHealthStatus
    should_recreate: bool
    reason: str
    details: Dict[str, Any]

class VMHealthChecker:
    """Check VM health and detect issues"""

    @staticmethod
    def check_vm_health(proxmox: Any, vmid: int, node: str) -> VMHealthReport:
        """Comprehensive VM health check"""
        # Check if VM exists
        # Check VM status (running, stopped, stuck)
        # Check agent connectivity
        # Check network configuration
        # Return detailed health report

    @staticmethod
    def is_vm_stuck(proxmox: Any, vmid: int, node: str) -> bool:
        """Detect stuck VMs that need cleanup"""
        # Check for lock files
        # Check for zombie processes
        # Check for incomplete operations

    @staticmethod
    def should_recreate_vm(health: VMHealthReport) -> bool:
        """Decision logic for VM recreation"""
        # Based on health status and failure reasons
        # Consider retry counters
        # Return recreation decision

class K3sHealthChecker:
    """Check k3s cluster state"""

    @staticmethod
    def node_in_cluster(control_plane: str, node_name: str) -> bool:
        """Check if node is in k3s cluster"""
        # SSH to control plane
        # Run kubectl get nodes
        # Parse output for node presence

    @staticmethod
    def node_is_ready(control_plane: str, node_name: str) -> bool:
        """Check if k3s node is ready"""
        # Check node conditions
        # Verify kubelet status
        # Return readiness state

    @staticmethod
    def get_cluster_token(control_plane: str) -> Optional[str]:
        """Retrieve k3s join token"""
        # SSH to control plane
        # Read /var/lib/rancher/k3s/server/node-token
        # Return token or None
```

**Implementation Details**:
- Use paramiko for SSH operations
- Parse JSON from kubectl commands
- Implement timeout handling for all checks
- Add detailed logging at each step
- Cache health results to avoid repeated checks

**Test Coverage**:
```python
# tests/test_health_checker.py
def test_vm_health_check_healthy(mock_proxmox):
    """Test health check for running VM"""

def test_vm_health_check_stuck(mock_proxmox):
    """Test detection of stuck VM"""

def test_should_recreate_decision_logic():
    """Test recreation decision matrix"""

def test_k3s_node_detection(mock_ssh):
    """Test k3s cluster membership check"""

def test_token_retrieval_success(mock_ssh):
    """Test successful token retrieval"""

def test_token_retrieval_failure(mock_ssh):
    """Test token retrieval error handling"""
```

**Files to Create**:
- `src/homelab/health_checker.py` (250 lines estimated)
- `tests/test_health_checker.py` (400 lines estimated)

##### 1.2 Update `vm_manager.py`
**Changes**: Add deletion, validation, and health integration

**Specific Code Changes**:
```python
# vm_manager.py additions

@staticmethod
def delete_vm(proxmox: Any, node: str, vmid: int) -> bool:
    """Delete VM and clean up resources"""
    try:
        # Stop VM if running
        status = proxmox.nodes(node).qemu(vmid).status.current.get()
        if status.get("status") == "running":
            proxmox.nodes(node).qemu(vmid).status.stop.post()
            # Wait for stop
            time.sleep(10)

        # Delete VM
        proxmox.nodes(node).qemu(vmid).delete()
        logger.info(f"Deleted VM {vmid} on {node}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete VM {vmid}: {e}")
        return False

@staticmethod
def validate_network_bridges(proxmox: Any, node: str, bridges: List[str]) -> bool:
    """Validate network bridges exist on node"""
    try:
        # Get network configuration
        networks = proxmox.nodes(node).network.get()
        available = {net["iface"] for net in networks if net["type"] == "bridge"}

        for bridge in bridges:
            if bridge not in available:
                logger.warning(f"Bridge {bridge} not found on {node}")
                return False

        return True
    except Exception as e:
        logger.error(f"Failed to validate bridges: {e}")
        return False

@staticmethod
def validate_storage(proxmox: Any, node: str, storage: str, required_gb: int) -> bool:
    """Validate storage exists and has capacity"""
    try:
        # Get storage status
        status = proxmox.nodes(node).storage(storage).status.get()
        available_gb = status["avail"] / (1024**3)

        if available_gb < required_gb:
            logger.warning(f"Insufficient storage on {storage}: {available_gb}GB < {required_gb}GB")
            return False

        return True
    except Exception as e:
        logger.error(f"Failed to validate storage: {e}")
        return False

# Update create_or_update_vm() method
@staticmethod
def create_or_update_vm() -> None:
    """Create or update VMs with health checking"""
    for idx, node in enumerate(Config.get_nodes()):
        name = node["name"]
        storage = node["img_storage"]

        if not storage:
            logger.warning(f"Skipping node {name}: no storage defined")
            continue

        # Connect with retry logic
        proxmox = VMManager._connect_with_retry(name)
        if not proxmox:
            logger.error(f"Cannot connect to {name}, skipping")
            continue

        # Check VM health if exists
        expected_name = Config.VM_NAME_TEMPLATE.format(node=name.replace("_", "-"))
        vmid = VMManager.vm_exists(proxmox, name)

        if vmid:
            # Health check existing VM
            health = VMHealthChecker.check_vm_health(proxmox, vmid, name)

            if health.should_recreate:
                logger.info(f"VM {vmid} unhealthy: {health.reason}")
                if VMManager.delete_vm(proxmox, name, vmid):
                    vmid = None  # Will recreate below
                else:
                    logger.error(f"Failed to delete unhealthy VM {vmid}")
                    continue
            else:
                logger.info(f"VM {vmid} is healthy, skipping")
                continue

        # Validate resources before creation
        bridges = Config.get_network_ifaces_for(idx)
        if not VMManager.validate_network_bridges(proxmox, name, bridges):
            logger.warning(f"Network validation failed for {name}")
            continue

        if not VMManager.validate_storage(proxmox, name, storage, 250):  # 250GB required
            logger.warning(f"Storage validation failed for {name}")
            continue

        # Create VM (existing logic)
        vmid = VMManager.get_next_available_vmid(proxmox)
        logger.info(f"Creating VM {expected_name} (vmid={vmid})")
        # ... rest of creation logic ...
```

**Test Coverage**:
```python
# tests/test_vm_manager.py additions
def test_delete_vm_success(mock_proxmox):
    """Test successful VM deletion"""

def test_delete_vm_already_stopped(mock_proxmox):
    """Test deletion of stopped VM"""

def test_validate_bridges_all_present(mock_proxmox):
    """Test bridge validation success"""

def test_validate_bridges_missing(mock_proxmox):
    """Test bridge validation failure"""

def test_validate_storage_sufficient(mock_proxmox):
    """Test storage validation with space"""

def test_validate_storage_insufficient(mock_proxmox):
    """Test storage validation failure"""

def test_health_check_integration(mock_proxmox, mock_health_checker):
    """Test health checking in main flow"""
```

**Files to Modify**:
- `src/homelab/vm_manager.py` (+150 lines)
- `tests/test_vm_manager.py` (+200 lines)

##### 1.3 Update `proxmox_api.py` - Graceful Fallback
**Changes**: Add SSL configuration and CLI fallback

**Implementation**:
```python
import os
import subprocess
import json
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class ProxmoxClient:
    """Wrapper with API and CLI fallback"""

    def __init__(self, host: str, use_cli_fallback: bool = True) -> None:
        if not host.endswith(".maas"):
            host = host + ".maas"
        self.host = host
        self.use_cli_fallback = use_cli_fallback
        self.proxmox: Optional[Any] = None
        self.cli_mode = False

        # Check SSL verification setting
        verify_ssl = os.getenv("PROXMOX_VERIFY_SSL", "false").lower() == "true"

        # Try API connection
        try:
            if Config.API_TOKEN is None:
                raise ValueError("API_TOKEN not set")

            user_token, api_token = Config.API_TOKEN.split("=")
            user, token_name = user_token.split("!")

            self.proxmox = ProxmoxAPI(
                host,
                user=user,
                token_name=token_name,
                token_value=api_token,
                verify_ssl=verify_ssl
            )

            # Test connection
            self.proxmox.version.get()
            logger.info(f"Connected to {host} via API")

        except Exception as e:
            logger.warning(f"API connection failed: {e}")

            if use_cli_fallback:
                logger.info("Falling back to CLI mode")
                self.cli_mode = True
            else:
                raise

    def _execute_ssh(self, command: str) -> Dict[str, Any]:
        """Execute command via SSH and parse JSON output"""
        ssh_user = os.getenv("SSH_USER", "root")
        ssh_key = os.path.expanduser(os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa"))

        full_command = f"ssh -o StrictHostKeyChecking=no -i {ssh_key} {ssh_user}@{self.host} '{command}'"

        try:
            result = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                raise RuntimeError(f"Command failed: {result.stderr}")

            # Try to parse as JSON
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"output": result.stdout}

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"SSH command timed out: {command}")

    def get_node_status(self) -> Dict[str, Any]:
        """Get node status via API or CLI"""
        if self.cli_mode:
            return self._execute_ssh("pvesh get /nodes/$(hostname)/status --output-format json")
        else:
            return self.proxmox.nodes(self.host).status.get()

    def get_storage_content(self, storage: str) -> List[Dict[str, Any]]:
        """Get storage content via API or CLI"""
        if self.cli_mode:
            cmd = f"pvesh get /nodes/$(hostname)/storage/{storage}/content --output-format json"
            result = self._execute_ssh(cmd)
            return result if isinstance(result, list) else []
        else:
            return self.proxmox.nodes(self.host).storage(storage).content.get()
```

**Test Coverage**:
```python
# tests/test_proxmox_api.py additions
def test_api_connection_success(mock_proxmoxer):
    """Test successful API connection"""

def test_api_ssl_verification_disabled(mock_proxmoxer, monkeypatch):
    """Test SSL verification can be disabled"""

def test_cli_fallback_activation(mock_proxmoxer, mock_subprocess):
    """Test CLI fallback when API fails"""

def test_cli_command_execution(mock_subprocess):
    """Test SSH command execution"""

def test_cli_json_parsing(mock_subprocess):
    """Test JSON parsing from CLI output"""
```

**Files to Modify**:
- `src/homelab/proxmox_api.py` (+100 lines)
- `tests/test_proxmox_api.py` (+150 lines)

#### Phase 1 Deliverables:
- [ ] `health_checker.py` module with full test coverage
- [ ] Updated `vm_manager.py` with deletion and validation
- [ ] Updated `proxmox_api.py` with CLI fallback
- [ ] All tests passing with 100% coverage
- [ ] Documentation updated in README

#### Phase 1 Success Criteria:
- System can detect stuck or unhealthy VMs
- System can delete VMs safely
- System gracefully handles SSL certificate failures
- Resource validation prevents failed provisioning
- All operations have clear logging

---

### Phase 2: K3s Integration
**Duration**: 4-5 days
**Goal**: Integrate k3s cluster join into main provisioning workflow

#### Changes Required:

##### 2.1 Create `k3s_manager.py` (refactor from k3s_migration_manager.py)
**Purpose**: Simplify k3s operations for provisioning workflow

**Changes**:
```python
# src/homelab/k3s_manager.py (new, simplified from migration manager)

import logging
import subprocess
import time
from typing import Optional, Dict, Any
import paramiko

logger = logging.getLogger(__name__)

class K3sManager:
    """Manages k3s cluster operations for VM provisioning"""

    @staticmethod
    def get_control_plane_vm() -> Optional[str]:
        """Find first available k3s control plane node"""
        # Try known control plane nodes
        control_planes = os.getenv("K3S_CONTROL_PLANES", "k3s-vm-recent-cub").split(",")

        for cp in control_planes:
            if K3sManager._is_reachable(cp.strip()):
                return cp.strip()

        return None

    @staticmethod
    def _is_reachable(hostname: str) -> bool:
        """Check if host is reachable via SSH"""
        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=5", f"ubuntu@{hostname}", "echo", "ok"],
                capture_output=True,
                timeout=10
            )
            return result.returncode == 0
        except:
            return False

    @staticmethod
    def get_cluster_token(control_plane: str) -> Optional[str]:
        """Retrieve k3s join token from control plane"""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh_key = os.path.expanduser(os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa"))
            ssh.connect(control_plane, username="ubuntu", key_filename=ssh_key)

            stdin, stdout, stderr = ssh.exec_command(
                "sudo cat /var/lib/rancher/k3s/server/node-token"
            )
            token = stdout.read().decode().strip()

            if token:
                logger.info(f"Retrieved k3s token from {control_plane}")
                return token
            else:
                logger.error("Empty token retrieved")
                return None

        except Exception as e:
            logger.error(f"Failed to get k3s token: {e}")
            return None
        finally:
            ssh.close()

    @staticmethod
    def ensure_node_in_cluster(
        vm_hostname: str,
        control_plane: str,
        token: Optional[str] = None
    ) -> bool:
        """Ensure VM is joined to k3s cluster (idempotent)"""

        # Check if already in cluster
        if K3sHealthChecker.node_in_cluster(control_plane, vm_hostname):
            logger.info(f"Node {vm_hostname} already in cluster")
            return True

        # Get token if not provided
        if not token:
            token = K3sManager.get_cluster_token(control_plane)
            if not token:
                logger.error("Cannot retrieve k3s token")
                return False

        # Install k3s and join cluster
        success = K3sManager._install_k3s_agent(
            vm_hostname,
            token,
            f"https://{control_plane}:6443"
        )

        if success:
            # Verify join succeeded
            return K3sManager._wait_for_node_ready(control_plane, vm_hostname)

        return False

    @staticmethod
    def _install_k3s_agent(vm_hostname: str, token: str, server_url: str) -> bool:
        """Install k3s agent on VM"""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh_key = os.path.expanduser(os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa"))
            ssh.connect(vm_hostname, username="ubuntu", key_filename=ssh_key)

            # Check if k3s already installed
            stdin, stdout, stderr = ssh.exec_command("which k3s")
            if stdout.channel.recv_exit_status() == 0:
                logger.info(f"k3s already installed on {vm_hostname}")
                # Just restart with correct config
                restart_cmd = f"""
                sudo systemctl stop k3s-agent
                sudo rm -f /etc/systemd/system/k3s-agent.service.env
                echo 'K3S_URL={server_url}' | sudo tee /etc/systemd/system/k3s-agent.service.env
                echo 'K3S_TOKEN={token}' | sudo tee -a /etc/systemd/system/k3s-agent.service.env
                sudo systemctl daemon-reload
                sudo systemctl start k3s-agent
                """
                stdin, stdout, stderr = ssh.exec_command(restart_cmd)
                return stdout.channel.recv_exit_status() == 0

            # Install k3s
            install_cmd = f"""
            curl -sfL https://get.k3s.io | K3S_URL='{server_url}' K3S_TOKEN='{token}' sh -s - agent
            """

            logger.info(f"Installing k3s on {vm_hostname}")
            stdin, stdout, stderr = ssh.exec_command(install_cmd, timeout=300)

            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                logger.error(f"k3s installation failed: {stderr.read().decode()}")
                return False

            logger.info(f"k3s installed successfully on {vm_hostname}")
            return True

        except Exception as e:
            logger.error(f"Failed to install k3s: {e}")
            return False
        finally:
            ssh.close()

    @staticmethod
    def _wait_for_node_ready(control_plane: str, node_name: str, timeout: int = 180) -> bool:
        """Wait for node to be ready in cluster"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if K3sHealthChecker.node_is_ready(control_plane, node_name):
                logger.info(f"Node {node_name} is ready in cluster")
                return True

            logger.debug(f"Waiting for {node_name} to be ready...")
            time.sleep(10)

        logger.error(f"Timeout waiting for {node_name} to be ready")
        return False

    @staticmethod
    def join_all_vms_to_cluster() -> None:
        """Join all VMs to k3s cluster"""
        # Find control plane
        control_plane = K3sManager.get_control_plane_vm()
        if not control_plane:
            logger.error("No k3s control plane found")
            return

        # Get token once
        token = K3sManager.get_cluster_token(control_plane)
        if not token:
            logger.error("Cannot retrieve k3s token")
            return

        # Join each VM
        for node in Config.get_nodes():
            vm_name = Config.VM_NAME_TEMPLATE.format(node=node["name"].replace("_", "-"))
            logger.info(f"Ensuring {vm_name} is in k3s cluster")

            success = K3sManager.ensure_node_in_cluster(vm_name, control_plane, token)
            if success:
                logger.info(f"✅ {vm_name} successfully joined cluster")
            else:
                logger.error(f"❌ Failed to join {vm_name} to cluster")
```

**Test Coverage**:
```python
# tests/test_k3s_manager.py
def test_find_control_plane(mock_subprocess):
    """Test control plane discovery"""

def test_get_cluster_token_success(mock_paramiko):
    """Test token retrieval"""

def test_node_already_in_cluster(mock_health_checker):
    """Test idempotent join"""

def test_k3s_installation(mock_paramiko):
    """Test k3s agent installation"""

def test_wait_for_ready_timeout(mock_health_checker):
    """Test timeout handling"""

def test_join_all_vms(mock_k3s_manager):
    """Test full cluster join workflow"""
```

**Files to Create/Modify**:
- `src/homelab/k3s_manager.py` (300 lines, simplified from migration manager)
- `tests/test_k3s_manager.py` (250 lines)

##### 2.2 Update `main.py` - Add K3s Workflow
**Changes**:
```python
# src/homelab/main.py
from homelab.iso_manager import IsoManager
from homelab.vm_manager import VMManager
from homelab.k3s_manager import K3sManager
from homelab.verification import verify_full_stack_health
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main() -> None:
    """Main entry point - fully idempotent provisioning"""
    try:
        logger.info("=== Phase 1: ISO Management ===")
        IsoManager.download_iso()
        IsoManager.upload_iso_to_nodes()

        logger.info("=== Phase 2: VM Provisioning ===")
        VMManager.create_or_update_vm()

        logger.info("=== Phase 3: K3s Cluster Integration ===")
        K3sManager.join_all_vms_to_cluster()

        logger.info("=== Phase 4: Verification ===")
        if verify_full_stack_health():
            logger.info("✅ All systems healthy and operational")
            sys.exit(0)
        else:
            logger.error("❌ Verification failed - check logs")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Provisioning interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Provisioning failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

**Test Coverage**:
```python
# tests/test_main.py
def test_main_full_workflow(mock_iso, mock_vm, mock_k3s, mock_verify):
    """Test complete provisioning workflow"""

def test_main_phase_failure(mock_iso, mock_vm):
    """Test handling of phase failures"""

def test_main_keyboard_interrupt(mock_iso):
    """Test graceful interrupt handling"""
```

##### 2.3 Cloud-init Template for K3s
**Purpose**: Install k3s prerequisites during VM boot

**New File**: Create template that will be uploaded to Proxmox nodes
```yaml
# src/homelab/templates/cloud-init-k3s.yaml
#cloud-config
package_update: true
package_upgrade: true
packages:
  - curl
  - qemu-guest-agent
  - open-iscsi
  - nfs-common

write_files:
  - path: /etc/modules-load.d/k3s.conf
    content: |
      br_netfilter
      overlay

  - path: /etc/sysctl.d/k3s.conf
    content: |
      net.bridge.bridge-nf-call-iptables = 1
      net.ipv4.ip_forward = 1
      net.bridge.bridge-nf-call-ip6tables = 1

runcmd:
  - modprobe br_netfilter
  - modprobe overlay
  - sysctl --system
  - systemctl enable qemu-guest-agent
  - systemctl start qemu-guest-agent
  # K3s will be installed by Python after VM boots
```

**Integration**: Update `vm_manager.py` to use new template
```python
# vm_manager.py modification
cloud_cfg = "user=local:snippets/cloud-init-k3s.yaml"  # Use k3s-ready template
```

#### Phase 2 Deliverables:
- [ ] `k3s_manager.py` module created with tests
- [ ] Updated `main.py` with 4-phase workflow
- [ ] Cloud-init template for k3s prerequisites
- [ ] Integration tests for k3s joining
- [ ] Documentation for k3s operations

#### Phase 2 Success Criteria:
- `poetry run python -m homelab.main` automatically joins VMs to k3s
- K3s join is fully idempotent (safe to re-run)
- Cluster membership verified automatically
- Token retrieval errors handled gracefully
- Control plane discovery works automatically

---

### Phase 3: End-to-End Testing and Polish
**Duration**: 2-3 days
**Goal**: Ensure robustness, comprehensive testing, and documentation

#### Changes Required:

##### 3.1 Create `verification.py` Module
**Purpose**: End-to-end verification of provisioning success

```python
# src/homelab/verification.py
import logging
from typing import List, Dict, Any
from homelab.config import Config
from homelab.health_checker import VMHealthChecker, K3sHealthChecker

logger = logging.getLogger(__name__)

def verify_full_stack_health() -> bool:
    """Verify complete infrastructure health"""

    all_healthy = True
    results = []

    logger.info("Starting full stack verification...")

    # 1. Verify all VMs exist and are healthy
    for node in Config.get_nodes():
        vm_name = Config.VM_NAME_TEMPLATE.format(node=node["name"].replace("_", "-"))

        # Check VM exists
        # Check VM is running
        # Check guest agent responding
        # Check network connectivity

        results.append({
            "vm": vm_name,
            "exists": True,  # Implementation
            "healthy": True,  # Implementation
        })

    # 2. Verify k3s cluster membership
    control_plane = K3sManager.get_control_plane_vm()
    if control_plane:
        for node in Config.get_nodes():
            vm_name = Config.VM_NAME_TEMPLATE.format(node=node["name"].replace("_", "-"))

            in_cluster = K3sHealthChecker.node_in_cluster(control_plane, vm_name)
            is_ready = K3sHealthChecker.node_is_ready(control_plane, vm_name)

            results.append({
                "vm": vm_name,
                "in_cluster": in_cluster,
                "ready": is_ready
            })

    # 3. Generate summary report
    logger.info("=== Verification Report ===")
    for result in results:
        logger.info(f"  {result}")

    return all_healthy
```

##### 3.2 Integration Tests
**New File**: `tests/test_full_workflow_integration.py`

```python
# tests/test_full_workflow_integration.py
import pytest
from unittest import mock
from homelab.main import main

class TestFullWorkflowIntegration:
    """End-to-end integration tests"""

    def test_fresh_provisioning(self, mock_env, mock_proxmox, mock_ssh):
        """Test provisioning from scratch"""
        # Setup: No existing VMs
        # Execute: main()
        # Assert: VMs created, k3s joined, verified

    def test_reprovisioning_stuck_vm(self, mock_env, mock_proxmox):
        """Test handling stuck VM"""
        # Setup: VM exists but stuck
        # Execute: main()
        # Assert: VM deleted, recreated, joined

    def test_api_failure_cli_fallback(self, mock_env):
        """Test API to CLI fallback"""
        # Setup: API connection fails
        # Execute: main()
        # Assert: CLI commands used successfully

    def test_k3s_token_retrieval_retry(self, mock_env):
        """Test k3s token retry logic"""
        # Setup: First token retrieval fails
        # Execute: main()
        # Assert: Retry succeeds

    def test_network_validation_failure(self, mock_env):
        """Test missing bridge handling"""
        # Setup: vmbr0 doesn't exist
        # Execute: main()
        # Assert: VM creation skipped with warning

    def test_partial_success_recovery(self, mock_env):
        """Test recovery from partial failure"""
        # Setup: 2 VMs exist, 1 needs creation
        # Execute: main()
        # Assert: Only missing VM created
```

##### 3.3 Configuration Validation
**Add to `config.py`**:

```python
# src/homelab/config.py additions
@staticmethod
def validate_configuration() -> bool:
    """Pre-flight configuration validation"""
    errors = []

    # Check required environment variables
    required_vars = [
        "API_TOKEN",
        "SSH_PUBKEY_PATH",
        "NODE_1",
        "STORAGE_1",
    ]

    for var in required_vars:
        if not os.getenv(var):
            errors.append(f"Missing required variable: {var}")

    # Check SSH key file exists
    ssh_path = os.path.expanduser(os.getenv("SSH_PUBKEY_PATH", ""))
    if not os.path.exists(ssh_path):
        errors.append(f"SSH key not found: {ssh_path}")

    # Check at least one node configured
    if not Config.get_nodes():
        errors.append("No nodes configured")

    if errors:
        for error in errors:
            logger.error(error)
        return False

    return True
```

##### 3.4 Enhanced Logging
**Update all modules with structured logging**:

```python
# Example logging enhancement
import logging
import json

class StructuredLogger:
    """Structured logging with context"""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def log_operation(self, operation: str, **context):
        """Log operation with structured context"""
        self.logger.info(json.dumps({
            "operation": operation,
            "timestamp": time.time(),
            **context
        }))
```

#### Phase 3 Deliverables:
- [ ] `verification.py` module for end-to-end checks
- [ ] Comprehensive integration test suite
- [ ] Configuration validation with pre-flight checks
- [ ] Enhanced structured logging throughout
- [ ] Complete documentation updates
- [ ] GitHub issue #159 closed

#### Phase 3 Success Criteria:
- All unit and integration tests pass
- 100% code coverage maintained
- Clear error messages guide troubleshooting
- Documentation accurate and complete
- No manual intervention for common scenarios
- Issue #159 closed with verification

---

## Work Breakdown for Sub-Agents

### Task 1: Implement Health Checking Module
**Agent**: General-purpose
**Duration**: 6-8 hours
**Files**:
- Create `src/homelab/health_checker.py`
- Create `tests/test_health_checker.py`
**Dependencies**: None
**Success Criteria**:
- All health checking methods implemented
- 100% test coverage achieved
- Handles timeouts and errors gracefully

### Task 2: Update VM Manager with Lifecycle Operations
**Agent**: General-purpose
**Duration**: 8-10 hours
**Files**:
- Modify `src/homelab/vm_manager.py`
- Update `tests/test_vm_manager.py`
**Dependencies**: Task 1 (health_checker.py)
**Success Criteria**:
- VM deletion works reliably
- Resource validation prevents failures
- Health checks integrated into workflow

### Task 3: Add CLI Fallback to Proxmox Client
**Agent**: General-purpose
**Duration**: 4-6 hours
**Files**:
- Modify `src/homelab/proxmox_api.py`
- Update `tests/test_proxmox_api.py`
**Dependencies**: None
**Success Criteria**:
- SSL configuration via environment
- CLI fallback activates on API failure
- All operations work in both modes

### Task 4: Create K3s Manager Module
**Agent**: General-purpose
**Duration**: 10-12 hours
**Files**:
- Create `src/homelab/k3s_manager.py` (refactor from migration manager)
- Create `tests/test_k3s_manager.py`
**Dependencies**: Task 1 (for K3sHealthChecker)
**Success Criteria**:
- Token retrieval works reliably
- K3s installation is idempotent
- Cluster join verified automatically

### Task 5: Integrate K3s into Main Workflow
**Agent**: General-purpose
**Duration**: 4-6 hours
**Files**:
- Modify `src/homelab/main.py`
- Create `src/homelab/verification.py`
- Update `tests/test_main.py`
**Dependencies**: Tasks 1-4
**Success Criteria**:
- 4-phase workflow executes cleanly
- Verification confirms success
- Proper exit codes on failure

### Task 6: Create Integration Tests
**Agent**: General-purpose
**Duration**: 6-8 hours
**Files**:
- Create `tests/test_full_workflow_integration.py`
- Create `tests/conftest.py` fixtures
**Dependencies**: Tasks 1-5
**Success Criteria**:
- All failure scenarios covered
- Mocking properly isolated
- Tests run quickly (<30 seconds)

### Task 7: Documentation and Polish
**Agent**: General-purpose
**Duration**: 4-6 hours
**Files**:
- Update `README.md`
- Update `docs/architecture.md`
- Create `docs/troubleshooting.md`
- Close GitHub issue #159
**Dependencies**: Tasks 1-6
**Success Criteria**:
- All new features documented
- Troubleshooting guide complete
- Issue closed with summary

---

## Risk Analysis

### High Risk Items:

1. **K3s Token Security**
   - **Risk**: Token exposed in logs or error messages
   - **Mitigation**: Mask token in all logging, use secure storage, rotate regularly
   - **Detection**: Log review, security scanning
   - **Recovery**: Token rotation procedure documented

2. **VM Deletion Logic**
   - **Risk**: Accidentally deleting healthy VMs
   - **Mitigation**: Conservative health checks, require multiple failure signals, dry-run mode
   - **Detection**: Extensive logging before deletion
   - **Recovery**: Backup VM configurations, quick reprovisioning

3. **Network Connectivity Dependencies**
   - **Risk**: SSH failures block all operations
   - **Mitigation**: Timeout handling, retry logic, bastion host support
   - **Detection**: Connection test before operations
   - **Recovery**: Manual fallback procedures documented

### Medium Risk Items:

1. **Test Coverage Maintenance**
   - **Risk**: New features reduce coverage below 100%
   - **Mitigation**: Write tests first (TDD), coverage checks in CI
   - **Detection**: Coverage reports on every commit
   - **Recovery**: Block merges until coverage restored

2. **Backward Compatibility**
   - **Risk**: Breaking existing deployments
   - **Mitigation**: Feature flags, gradual rollout, extensive testing
   - **Detection**: Integration tests with old configs
   - **Recovery**: Version pinning, rollback procedure

3. **Cloud-init Template Distribution**
   - **Risk**: Template not present on all nodes
   - **Mitigation**: Automatic template upload, pre-flight checks
   - **Detection**: Validation before VM creation
   - **Recovery**: Fallback to default template

### Low Risk Items:

1. **Performance Impact**
   - **Risk**: Health checks slow down provisioning
   - **Mitigation**: Parallel checks, caching, timeouts
   - **Detection**: Timing logs for each operation
   - **Recovery**: Optimization in follow-up

2. **Logging Volume**
   - **Risk**: Excessive logs fill disk
   - **Mitigation**: Log rotation, configurable levels
   - **Detection**: Disk usage monitoring
   - **Recovery**: Log cleanup procedures

---

## Testing Strategy

### Unit Tests (Per Module):
Required coverage: 100% for all new code

- `test_health_checker.py` - Mock VM states, SSH operations, k3s responses
- `test_vm_manager.py` - Mock Proxmox API calls, deletion, validation
- `test_k3s_manager.py` - Mock SSH, token retrieval, installation
- `test_proxmox_api.py` - Mock API failures, CLI execution
- `test_config.py` - Test validation logic, missing variables
- `test_verification.py` - Mock health checks, report generation

### Integration Tests:
Focus on interaction between components

- Full workflow from VM creation to k3s join
- API to CLI fallback scenarios
- Partial failure recovery
- Idempotency verification (run twice)
- Network failure handling

### Manual Testing Checklist:
Before marking complete:

- [ ] Fresh provisioning on clean Proxmox node
- [ ] Reprovisioning with existing stuck VM
- [ ] Recovery from API SSL failure
- [ ] K3s cluster join with existing cluster
- [ ] K3s cluster join as first node
- [ ] Network bridge validation failure
- [ ] Storage capacity validation failure
- [ ] Missing configuration handling
- [ ] Interrupt handling (Ctrl+C)
- [ ] Verification of all error messages

---

## Success Metrics

### Quantitative:
- **100% test coverage** maintained throughout
- **Zero manual interventions** for standard provisioning
- **< 10 minute** end-to-end provisioning time (3 VMs)
- **All 7 issues** from troubleshooting doc automated
- **< 30 second** health check completion
- **3 retry attempts** for transient failures

### Qualitative:
- Single command (`poetry run python -m homelab.main`) works reliably
- Error messages clearly indicate problems and solutions
- System recovers from common failures automatically
- Code is maintainable with clear separation of concerns
- Documentation sufficient for new developers
- Logging provides complete audit trail

### Verification Criteria:
- Can provision from scratch without intervention
- Can recover from stuck VM scenario
- Can handle SSL certificate issues
- Can join nodes to existing k3s cluster
- Can detect and report unhealthy states
- Can be safely interrupted and resumed

---

## Timeline and Effort Estimate

### Phase 1: Foundation (5-7 days)
- Health checking module: 1.5 days
- VM manager updates: 2 days
- API fallback implementation: 1 day
- Testing and bug fixes: 1.5 days
- Documentation: 0.5 days

### Phase 2: K3s Integration (4-5 days)
- K3s manager module: 2 days
- Main workflow integration: 1 day
- Cloud-init templates: 0.5 days
- Testing and fixes: 1 day
- Documentation: 0.5 days

### Phase 3: Polish (2-3 days)
- Verification module: 0.5 days
- Integration tests: 1 day
- Documentation updates: 0.5 days
- Final testing: 1 day

**Total Estimated Effort**: 11-15 working days (60-80 person-hours)
**Recommended Timeline**: 3-4 weeks with buffer for discoveries

### Effort Distribution:
- Development: 50% (30-40 hours)
- Testing: 30% (18-24 hours)
- Documentation: 10% (6-8 hours)
- Debugging/Polish: 10% (6-8 hours)

---

## Next Steps

### Immediate Actions (Day 1):
1. Review this plan with stakeholders
2. Create GitHub sub-issues for each task
3. Set up development environment
4. Begin Task 1 (Health Checking Module)

### Week 1 Goals:
- Complete Phase 1 (Foundation)
- All health checking operational
- VM lifecycle management working
- API fallback implemented

### Week 2 Goals:
- Complete Phase 2 (K3s Integration)
- K3s manager fully tested
- Main workflow integrated
- Cloud-init templates deployed

### Week 3 Goals:
- Complete Phase 3 (Polish)
- All integration tests passing
- Documentation complete
- Issue #159 closed

### Follow-up Improvements (Future):
- Web UI for monitoring provisioning
- Prometheus metrics integration
- Multi-cluster support
- Automated backup before deletion
- GitOps declarative configuration

---

## Appendix

### Related Documentation:
- **Troubleshooting doc**: `docs/troubleshooting/k3s-node-reprovisioning-workarounds-still-fawn.md`
- **GitHub issue**: #159
- **Current architecture**: `proxmox/homelab/README.md`
- **Poetry documentation**: https://python-poetry.org/docs/
- **K3s documentation**: https://docs.k3s.io/

### Code Review Checklist:
Before any PR merge:
- [ ] All new code has unit tests
- [ ] 100% coverage maintained
- [ ] Type hints on all functions
- [ ] Docstrings follow Google style
- [ ] Error handling comprehensive
- [ ] Logging provides context
- [ ] No hardcoded values
- [ ] Configuration via environment
- [ ] Backward compatible
- [ ] Documentation updated

### Definition of Done:
A task is complete when:
1. Code implemented and working
2. Unit tests achieve 100% coverage
3. Integration tests pass
4. Documentation updated
5. Code review completed
6. Manual testing performed
7. Merged to main branch

### Communication Plan:
- Daily updates on progress
- Blockers raised immediately
- Weekly demo of working features
- Final demo before closing issue

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-12 | AI Assistant | Initial implementation plan |

---

*End of Implementation Plan*