# K3s Node Reprovisioning Workarounds - still-fawn

**Date**: 2025-11-12
**Node**: still-fawn.maas
**Proxmox Host**: still-fawn.maas
**VM ID**: 108
**VM Name**: k3s-vm-still-fawn
**Issue Severity**: High - Multiple infrastructure code gaps exposed

## Summary

During k3s cluster node reprovisioning for `still-fawn`, the Python infrastructure-as-code system (`proxmox/homelab`) failed to handle the scenario automatically. What should have been a single command (`poetry run python -m homelab.main`) required multiple manual workarounds, script creation, and SSH-based interventions.

**Expected Workflow**:
- Run main provisioning script → Detect existing VM health → Delete if needed → Recreate → Join k3s cluster → Verify

**Actual Workflow**:
- Proxmox API SSL failures → Manual script creation → DNS resolution workarounds → Manual k3s token retrieval → Manual VM creation → Manual cluster join → Manual verification

The root cause was lack of robustness in the Python infrastructure code for handling real-world scenarios like SSL certificate issues, network failures, and k3s cluster integration.

## Issues Encountered and Workarounds

### 1. Proxmox API SSL Certificate Failures

**Problem**:
- Python `proxmoxer` library failed with SSL certificate verification errors when connecting to Proxmox API
- Error: `SSL: CERTIFICATE_VERIFY_FAILED` when attempting to connect to `https://still-fawn.maas:8006`
- Blocked all automated VM provisioning operations

**Root Cause**:
- Proxmox nodes use self-signed SSL certificates by default
- Python `proxmoxer` library enforces strict SSL verification
- Infrastructure code (`proxmox/homelab/src/homelab/proxmox_api.py`) had no fallback mechanism
- No configuration option to disable SSL verification for homelab environments

**Workaround**:
1. Created manual shell script: `/Users/10381054/code/home/proxmox/homelab/scripts/create_still_fawn_vm_manual.sh`
2. Used `ssh` commands to execute Proxmox CLI (`qm`) directly on the host
3. Bypassed Python API entirely for VM creation

```bash
#!/bin/bash
# Manual VM creation using SSH and qm commands
ssh root@still-fawn.maas "qm create 108 \
  --name k3s-vm-still-fawn \
  --memory 8192 \
  --cores 4 \
  --net0 virtio,bridge=vmbr0 \
  --scsihw virtio-scsi-pci \
  --scsi0 local-zfs:32 \
  --ide2 local:iso/ubuntu-22.04.3-live-server-amd64.iso,media=cdrom \
  --boot order=scsi0;ide2 \
  --ostype l26 \
  --agent enabled=1"
```

**Proper Solution**:
- Add `verify_ssl` parameter to `ProxmoxAPI` class initialization in `proxmox/homelab/src/homelab/proxmox_api.py`
- Allow configuration via environment variable: `PROXMOX_VERIFY_SSL=false`
- Implement automatic fallback to SSH/CLI when API fails
- Add warning log when SSL verification is disabled

```python
# Proposed fix for proxmox/homelab/src/homelab/proxmox_api.py
import os
from proxmoxer import ProxmoxAPI

class ProxmoxManager:
    def __init__(self, host: str, token_name: str, token_value: str):
        verify_ssl = os.getenv('PROXMOX_VERIFY_SSL', 'true').lower() == 'true'
        if not verify_ssl:
            logger.warning(f"SSL verification disabled for {host} - use only in homelab")

        try:
            self.proxmox = ProxmoxAPI(
                host,
                user=token_name.split('!')[0],
                token_name=token_name.split('!')[1],
                token_value=token_value,
                verify_ssl=verify_ssl
            )
        except Exception as e:
            logger.error(f"Proxmox API connection failed: {e}")
            logger.info("Falling back to SSH/CLI execution")
            self.use_ssh_fallback = True
```

### 2. DNS Resolution from Mac

**Problem**:
- Mac development machine could not resolve `still-fawn.maas` hostname
- DNS resolution worked from other homelab hosts but not from Mac
- Blocked direct API access and SSH operations from development environment

**Root Cause**:
- Mac DNS resolver not configured to use homelab OPNsense Unbound DNS server
- MAAS domain (`.maas`) not propagated to Mac DNS configuration
- Development environment not integrated with homelab DNS infrastructure

**Workaround**:
1. Connected to intermediate host that could resolve `.maas` domains
2. Used SSH proxy/jump host pattern: `ssh -J pve root@still-fawn.maas`
3. Ran all Proxmox operations from `pve` host instead of Mac

```bash
# Temporary workaround - use pve as jump host
ssh root@pve "ssh root@still-fawn.maas 'qm list'"
```

**Proper Solution**:
- Add documentation for Mac DNS configuration in `docs/setup/mac-development-environment.md`
- Configure Mac to use OPNsense DNS server for `.maas` domain
- Add DNS configuration script: `scripts/setup-mac-dns-homelab.sh`
- Update `CLAUDE.md` with Mac DNS setup requirements

```bash
# Proposed: scripts/setup-mac-dns-homelab.sh
#!/bin/bash
# Configure Mac to resolve .maas domains via homelab DNS

OPNSENSE_DNS="192.168.1.1"  # OPNsense Unbound DNS server

# Create resolver configuration for .maas domain
sudo mkdir -p /etc/resolver
sudo tee /etc/resolver/maas > /dev/null <<EOF
nameserver $OPNSENSE_DNS
domain maas
search maas
EOF

echo "Mac DNS configured for .maas domain resolution"
scutil --dns | grep -A 3 "resolver #"
```

### 3. K3s Cluster Join Token Retrieval

**Problem**:
- K3s cluster join requires a token from existing control plane node
- No automated way to retrieve token from existing k3s cluster
- Infrastructure code had zero k3s cluster integration

**Root Cause**:
- `proxmox/homelab/src/homelab/main.py` creates VMs but doesn't handle k3s cluster operations
- No k3s cluster manager module exists in the infrastructure code
- K3s token retrieval logic never implemented

**Workaround**:
1. Manually SSH to existing k3s node: `ssh ubuntu@k3s-vm-recent-cub`
2. Retrieved token: `sudo cat /var/lib/rancher/k3s/server/node-token`
3. Saved to temporary file: `/tmp/k3s-cluster-token.txt` for reuse

```bash
# Manual token retrieval
ssh ubuntu@k3s-vm-recent-cub "sudo cat /var/lib/rancher/k3s/server/node-token" > /tmp/k3s-cluster-token.txt
K3S_TOKEN=$(cat /tmp/k3s-cluster-token.txt)
```

**Proper Solution**:
- Create new module: `proxmox/homelab/src/homelab/k3s_manager.py`
- Implement `get_cluster_token()` function
- Add k3s cluster discovery and health checking
- Integrate k3s operations into main provisioning workflow

```python
# Proposed: proxmox/homelab/src/homelab/k3s_manager.py
import paramiko
from typing import Optional

class K3sManager:
    """Manage K3s cluster operations."""

    def get_cluster_token(self, control_plane_vm: str) -> Optional[str]:
        """Retrieve K3s cluster join token from control plane node.

        Args:
            control_plane_vm: SSH hostname of control plane node

        Returns:
            K3s join token string or None if failed
        """
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(control_plane_vm, username='ubuntu', key_filename='~/.ssh/id_ed25519_pve')

            stdin, stdout, stderr = client.exec_command(
                'sudo cat /var/lib/rancher/k3s/server/node-token'
            )
            token = stdout.read().decode().strip()
            client.close()

            if token:
                logger.info(f"Retrieved K3s token from {control_plane_vm}")
                return token
            else:
                logger.error(f"Empty token from {control_plane_vm}")
                return None

        except Exception as e:
            logger.error(f"Failed to retrieve K3s token: {e}")
            return None

    def verify_cluster_membership(self, control_plane_vm: str, node_name: str) -> bool:
        """Verify a node has successfully joined the K3s cluster."""
        # Implementation for kubectl get nodes verification
        pass
```

### 4. K3s Installation Token Passing

**Problem**:
- New VM needed k3s installation with proper cluster join token
- Cloud-init configuration didn't include k3s agent installation
- No mechanism to pass k3s token to new VM during provisioning

**Root Cause**:
- Cloud-init template (`proxmox/homelab/templates/cloud-init.yaml.j2` if it exists) lacks k3s installation logic
- VM provisioning doesn't accept k3s-specific parameters
- No integration between VM creation and k3s cluster membership

**Workaround**:
1. Manually SSH to new VM after creation: `ssh ubuntu@k3s-vm-still-fawn`
2. Manually installed k3s agent with token:

```bash
# Manual k3s agent installation
K3S_TOKEN="K10abc123::server:xyz789"
K3S_URL="https://k3s-vm-recent-cub:6443"

curl -sfL https://get.k3s.io | \
  K3S_URL=$K3S_URL \
  K3S_TOKEN=$K3S_TOKEN \
  sh -s - agent
```

**Proper Solution**:
- Extend `vm_manager.py` to accept k3s parameters
- Create cloud-init template with k3s installation support
- Implement idempotent k3s agent installation in provisioning workflow

```python
# Proposed: proxmox/homelab/src/homelab/vm_manager.py
def create_k3s_vm(
    self,
    node: str,
    vm_id: int,
    vm_name: str,
    k3s_control_plane: str,
    k3s_token: str,
    **kwargs
) -> bool:
    """Create VM with automatic K3s cluster join.

    Args:
        node: Proxmox node name
        vm_id: VM identifier
        vm_name: VM hostname
        k3s_control_plane: Control plane node hostname
        k3s_token: K3s cluster join token
        **kwargs: Additional VM parameters
    """
    # Generate cloud-init with k3s installation
    cloud_init = self._render_cloud_init_k3s(
        hostname=vm_name,
        k3s_url=f"https://{k3s_control_plane}:6443",
        k3s_token=k3s_token
    )

    # Create VM with k3s cloud-init
    # Implementation here
```

### 5. Network Bridge Validation

**Problem**:
- VM creation succeeded but network connectivity was uncertain
- No validation that `vmbr0` bridge existed on `still-fawn` host
- Could have created VM with invalid network configuration

**Root Cause**:
- VM creation code doesn't validate network bridge availability before VM creation
- No pre-flight checks for host resources (storage, network, memory)
- Assumes all Proxmox hosts have identical network configuration

**Workaround**:
1. Manually verified bridge existence: `ssh root@still-fawn.maas "ip link show vmbr0"`
2. Checked bridge configuration: `ssh root@still-fawn.maas "cat /etc/network/interfaces"`
3. Confirmed bridge was active before proceeding with VM creation

```bash
# Manual bridge validation
ssh root@still-fawn.maas "ip link show vmbr0"
# Output: 4: vmbr0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP
```

**Proper Solution**:
- Add pre-flight validation in `vm_manager.py`
- Verify bridge existence before VM creation
- Check storage pool availability and capacity
- Validate memory and CPU availability on target node

```python
# Proposed: proxmox/homelab/src/homelab/vm_manager.py
def validate_host_resources(
    self,
    node: str,
    required_memory: int,
    required_storage: int,
    required_network: str = 'vmbr0'
) -> bool:
    """Validate host has required resources before VM creation.

    Args:
        node: Proxmox node name
        required_memory: Memory in MB
        required_storage: Storage in GB
        required_network: Network bridge name

    Returns:
        True if all resources available, False otherwise

    Raises:
        ResourceValidationError: If resources insufficient
    """
    # Check network bridge
    result = self._ssh_execute(node, f"ip link show {required_network}")
    if result.returncode != 0:
        raise ResourceValidationError(f"Bridge {required_network} not found on {node}")

    # Check storage availability
    # Check memory availability
    # Check CPU availability

    return True
```

### 6. VM Deletion for Re-provisioning

**Problem**:
- Existing VM (ID 108) was in failed state and needed deletion
- Main provisioning script had no VM health checking or cleanup capability
- No safe way to delete and recreate VM through infrastructure code

**Root Cause**:
- No VM lifecycle management in infrastructure code
- No health checking or state detection
- No idempotent "ensure VM exists and is healthy" logic

**Workaround**:
1. Created manual deletion script: `/Users/10381054/code/home/proxmox/homelab/scripts/delete_vm.py`
2. Manually identified VM ID and node
3. Ran deletion script separately before re-provisioning

```python
# Manual deletion script created as workaround
from homelab.proxmox_api import get_proxmox_connection

def delete_vm(node: str, vm_id: int):
    """Manually delete VM - workaround for lack of lifecycle management."""
    proxmox = get_proxmox_connection(node)
    proxmox.nodes(node).qemu(vm_id).delete()
```

**Proper Solution**:
- Add VM health checking to main provisioning flow
- Implement `ensure_vm_healthy()` function that detects and fixes issues
- Add `--force-recreate` flag to main script
- Make provisioning idempotent with automatic cleanup

```python
# Proposed: proxmox/homelab/src/homelab/vm_manager.py
def ensure_vm_healthy(self, node: str, vm_id: int, vm_name: str) -> bool:
    """Ensure VM exists and is healthy, recreate if needed.

    Args:
        node: Proxmox node name
        vm_id: Expected VM ID
        vm_name: Expected VM name

    Returns:
        True if VM is healthy or successfully recreated
    """
    # Check if VM exists
    if not self.vm_exists(node, vm_id):
        logger.info(f"VM {vm_id} doesn't exist, will create")
        return False

    # Check VM health
    vm_status = self.get_vm_status(node, vm_id)

    if vm_status == 'running':
        # Verify network connectivity
        if self.verify_vm_network(vm_name):
            logger.info(f"VM {vm_id} is healthy")
            return True
        else:
            logger.warning(f"VM {vm_id} has network issues")

    # VM exists but unhealthy - delete and recreate
    logger.info(f"VM {vm_id} unhealthy, deleting for recreation")
    self.delete_vm(node, vm_id)
    return False
```

### 7. Cluster Membership Verification

**Problem**:
- No automated verification that new node successfully joined k3s cluster
- Manual SSH to control plane required to check `kubectl get nodes`
- Could have silently failed cluster join without detection

**Root Cause**:
- No end-to-end verification in provisioning workflow
- No k3s cluster state integration
- No success criteria validation after provisioning

**Workaround**:
1. Manually SSH to control plane: `ssh ubuntu@k3s-vm-recent-cub`
2. Manually ran: `kubectl get nodes` to verify new node appeared
3. Checked node status: `kubectl get node k3s-vm-still-fawn -o wide`

```bash
# Manual cluster verification
ssh ubuntu@k3s-vm-recent-cub "kubectl get nodes"
# Expected: k3s-vm-still-fawn   Ready    <none>   2m    v1.28.5+k3s1
```

**Proper Solution**:
- Add cluster verification to provisioning workflow
- Implement `wait_for_cluster_join()` function with timeout
- Verify node readiness before marking provisioning complete
- Add health checks for node conditions

```python
# Proposed: proxmox/homelab/src/homelab/k3s_manager.py
def wait_for_cluster_join(
    self,
    control_plane_vm: str,
    new_node_name: str,
    timeout: int = 300
) -> bool:
    """Wait for new node to join cluster and become ready.

    Args:
        control_plane_vm: Control plane node hostname
        new_node_name: Name of node joining cluster
        timeout: Maximum wait time in seconds

    Returns:
        True if node joined and ready, False if timeout
    """
    import time
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            # Check if node appears in cluster
            result = self._ssh_execute(
                control_plane_vm,
                f"kubectl get node {new_node_name} -o json"
            )

            if result.returncode == 0:
                node_data = json.loads(result.stdout)
                conditions = node_data['status']['conditions']

                # Check if Ready condition is True
                for condition in conditions:
                    if condition['type'] == 'Ready' and condition['status'] == 'True':
                        logger.info(f"Node {new_node_name} is ready")
                        return True

                logger.info(f"Node {new_node_name} exists but not ready yet")

            time.sleep(10)

        except Exception as e:
            logger.debug(f"Waiting for node join: {e}")
            time.sleep(10)

    logger.error(f"Timeout waiting for {new_node_name} to join cluster")
    return False
```

## Scripts Created as Workarounds

All workaround scripts represent gaps in the infrastructure code that should be automated:

1. **`/Users/10381054/code/home/proxmox/homelab/scripts/delete_vm.py`**
   - Purpose: Manually delete VM when infrastructure code can't handle lifecycle
   - Should be: Integrated into main provisioning with health checking

2. **`/Users/10381054/code/home/proxmox/homelab/scripts/provision_vms_only.py`**
   - Purpose: VM creation without k3s integration
   - Should be: Part of modular provisioning workflow with k3s support

3. **`/Users/10381054/code/home/proxmox/homelab/scripts/create_still_fawn_vm_manual.sh`**
   - Purpose: Workaround for Proxmox API SSL failures
   - Should be: API code with SSL verification configuration and SSH fallback

4. **`/tmp/k3s-cluster-token.txt`**
   - Purpose: Manual token storage for reuse
   - Should be: Automated token retrieval and secure storage in infrastructure code

## What Should Have Worked

The ideal workflow for k3s node reprovisioning should be:

```bash
# Desired: Single command handles everything
cd /Users/10381054/code/home/proxmox/homelab
poetry run python -m homelab.main --reprovision-node still-fawn

# What it should do automatically:
# 1. Detect VM 108 exists but is unhealthy
# 2. Safely delete VM 108 from still-fawn.maas
# 3. Retrieve k3s cluster token from control plane
# 4. Create new VM 108 with k3s cloud-init configuration
# 5. Wait for VM to boot and k3s agent to install
# 6. Verify node joined cluster and is ready
# 7. Report success with node details
```

**Current Reality**:
```bash
# What actually happened:
# 1. Run main.py → SSL certificate error → FAIL
# 2. Create manual shell script for VM creation
# 3. SSH to retrieve k3s token manually
# 4. Create VM via shell script
# 5. SSH to new VM to install k3s manually
# 6. SSH to control plane to verify cluster join manually
# 7. 7 manual steps instead of 1 automated command
```

## Infrastructure Code Gaps

### Critical Gaps Requiring Immediate Attention

1. **`proxmox/homelab/src/homelab/proxmox_api.py`** (Lines 1-50)
   - Missing: SSL verification configuration
   - Missing: SSH/CLI fallback when API fails
   - Missing: Connection retry logic with exponential backoff

2. **`proxmox/homelab/src/homelab/main.py`** (Lines 5-9)
   - Missing: K3s cluster integration entirely
   - Missing: VM health checking before provisioning
   - Missing: Idempotent "ensure desired state" logic
   - Missing: End-to-end verification of provisioning success

3. **`proxmox/homelab/src/homelab/vm_manager.py`** (Lines 136-142)
   - Missing: Pre-flight resource validation (network, storage, memory)
   - Missing: VM health checking and auto-remediation
   - Missing: Lifecycle management (create, update, delete, recreate)
   - Missing: Cloud-init template rendering with k3s support

4. **Non-existent: `proxmox/homelab/src/homelab/k3s_manager.py`**
   - Missing: Entire k3s cluster management module
   - Missing: Token retrieval from control plane
   - Missing: Agent installation automation
   - Missing: Cluster membership verification
   - Missing: Node health monitoring

5. **Non-existent: `proxmox/homelab/templates/cloud-init-k3s.yaml.j2`**
   - Missing: Cloud-init template with k3s agent installation
   - Missing: Parameterized k3s token and control plane URL
   - Missing: Post-installation verification hooks

6. **`proxmox/homelab/tests/`** (Entire directory)
   - Missing: Integration tests for k3s cluster operations
   - Missing: End-to-end provisioning tests
   - Missing: Network validation tests
   - Missing: SSL fallback tests

### Environment and Configuration Gaps

7. **`proxmox/homelab/.env.example`**
   - Missing: `PROXMOX_VERIFY_SSL` configuration
   - Missing: `K3S_CONTROL_PLANE_NODE` configuration
   - Missing: Network bridge configuration per node

8. **`docs/setup/mac-development-environment.md`**
   - Missing: Mac DNS configuration for `.maas` domain
   - Missing: Development environment setup instructions
   - Missing: SSH key setup and jump host configuration

## Success Criteria for Proper Implementation

When the infrastructure code is properly fixed, these scenarios should work automatically:

### 1. VM Health Detection and Auto-Cleanup
```bash
poetry run python -m homelab.main
# Should automatically:
# - Detect VM 108 is unhealthy
# - Log: "VM 108 on still-fawn is unhealthy, recreating"
# - Delete and recreate without manual intervention
```

### 2. Graceful API Fallback to CLI
```bash
poetry run python -m homelab.main
# When API fails with SSL error:
# - Log: "Proxmox API failed (SSL), falling back to SSH/CLI"
# - Continue provisioning via SSH commands
# - Complete successfully without manual scripts
```

### 3. Network Validation Before VM Creation
```bash
poetry run python -m homelab.main
# Should validate:
# - Bridge vmbr0 exists on still-fawn
# - Storage pool has capacity
# - Memory available for VM
# - Fail fast if resources missing
```

### 4. Integrated K3s Cluster Join Workflow
```bash
poetry run python -m homelab.main
# Should automatically:
# - Retrieve k3s token from control plane
# - Create VM with k3s cloud-init
# - Wait for k3s agent to install
# - Verify cluster membership
# - Report: "k3s-vm-still-fawn joined cluster successfully"
```

### 5. End-to-End Idempotent Operation
```bash
# Run multiple times - should be safe
poetry run python -m homelab.main
poetry run python -m homelab.main  # Second run should detect healthy state
# Second run should:
# - Log: "All VMs healthy, no action needed"
# - Exit successfully without changes
```

### 6. Comprehensive Error Handling
```bash
# When something fails:
poetry run python -m homelab.main
# Should provide:
# - Clear error messages
# - Rollback to previous state
# - Actionable remediation steps
# - Never leave infrastructure in half-configured state
```

## Related Files

### Documentation
- `docs/reference/proxmox-investigation-commands.md` - Proxmox investigation patterns
- `docs/reference/kubernetes-investigation-commands.md` - K3s cluster investigation
- `CLAUDE.md` - SSH access patterns and Poetry requirements

### Configuration
- `proxmox/homelab/pyproject.toml` - Python dependencies
- `proxmox/homelab/.env` - Environment variables (not in git)
- `~/.ssh/config` - SSH configuration for `.maas` domain

### Scripts (Workarounds - should be deprecated)
- `/Users/10381054/code/home/proxmox/homelab/scripts/delete_vm.py`
- `/Users/10381054/code/home/proxmox/homelab/scripts/provision_vms_only.py`
- `/Users/10381054/code/home/proxmox/homelab/scripts/create_still_fawn_vm_manual.sh`
- `/tmp/k3s-cluster-token.txt`

### Infrastructure Code (Needs Enhancement)
- `proxmox/homelab/src/homelab/main.py` - Main provisioning entry point
- `proxmox/homelab/src/homelab/vm_manager.py` - VM lifecycle management
- `proxmox/homelab/src/homelab/proxmox_api.py` - Proxmox API wrapper

### Missing Files (Should Be Created)
- `proxmox/homelab/src/homelab/k3s_manager.py` - K3s cluster management
- `proxmox/homelab/templates/cloud-init-k3s.yaml.j2` - K3s cloud-init template
- `docs/setup/mac-development-environment.md` - Mac DNS setup guide
- `scripts/setup-mac-dns-homelab.sh` - Automated Mac DNS configuration

## Implementation Priority

### Phase 1: Critical Fixes (Immediate)
1. Add SSL verification configuration to `proxmox_api.py`
2. Implement SSH/CLI fallback for API failures
3. Create `k3s_manager.py` with token retrieval
4. Add pre-flight resource validation to `vm_manager.py`

### Phase 2: Integration (Week 1)
1. Create cloud-init template with k3s support
2. Integrate k3s operations into main provisioning workflow
3. Add end-to-end verification after provisioning
4. Implement VM health checking and auto-remediation

### Phase 3: Robustness (Week 2)
1. Add comprehensive error handling and rollback
2. Implement retry logic with exponential backoff
3. Create integration tests for all scenarios
4. Document Mac development environment setup

### Phase 4: Polish (Week 3)
1. Add detailed logging and progress indicators
2. Create troubleshooting documentation
3. Implement `--dry-run` mode for safety
4. Add Prometheus metrics for provisioning operations

## Lessons Learned

### Technical Lessons
1. **SSL verification in homelab**: Self-signed certificates are standard, code must handle gracefully
2. **DNS propagation**: Development environments need explicit DNS configuration for internal domains
3. **K3s integration**: Cluster operations are core to VM provisioning, not an afterthought
4. **Idempotency matters**: Infrastructure code must safely handle "already exists" and "partially configured" states

### Process Lessons
1. **Health checking first**: Always detect current state before making changes
2. **Fail fast**: Validate resources exist before attempting operations
3. **End-to-end verification**: Provisioning isn't complete until cluster membership confirmed
4. **Graceful degradation**: When API fails, fall back to CLI rather than abort

### Architecture Lessons
1. **Modularity**: K3s operations should be separate module, not embedded in VM management
2. **Configuration flexibility**: SSL verification, DNS servers, network bridges must be configurable
3. **Testing requirements**: Integration tests must cover real-world failure scenarios
4. **Documentation**: Workaround scripts are documentation of missing features

## Future Enhancements

### Short-term (Next Sprint)
- [ ] Implement all Phase 1 critical fixes
- [ ] Create `k3s_manager.py` module with comprehensive tests
- [ ] Add SSL verification configuration and SSH fallback
- [ ] Document Mac development environment setup

### Medium-term (Next Month)
- [ ] Full k3s cluster lifecycle management (create, join, remove, upgrade)
- [ ] Prometheus monitoring integration for provisioning operations
- [ ] Automated backup before destructive operations
- [ ] Web UI for homelab infrastructure management

### Long-term (Next Quarter)
- [ ] Multi-cluster support (dev, staging, prod)
- [ ] Automated disaster recovery and cluster rebuild
- [ ] GitOps integration for declarative infrastructure
- [ ] Cost tracking and resource utilization reporting

## Tags

k3s, kubernetes, k8s, proxmox, vm-provisioning, infrastructure-as-code, iaac, idempotent, idempotency, workarounds, troubleshooting, ssl-certificates, dns-resolution, cluster-management, cloud-init, health-checking, lifecycle-management, automation, homelab, still-fawn, reprovisioning, manual-intervention, technical-debt, infrastructure-gaps
