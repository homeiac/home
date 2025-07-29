# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a homelab infrastructure management repository that follows Infrastructure as Code principles. The homelab is designed to be **entirely managed by AI tools** - from virtual machines to Kubernetes manifests. The architecture uses a layered approach with automation, services, and extensive documentation layers.

## Key Commands

### Documentation
- Build documentation: `make -C docs html`
- Documentation is deployed from `master` branch automatically
- Clean docs build: `make -C docs clean && make -C docs html`

### Python Development (Proxmox automation)
- **IMPORTANT**: Always use Poetry to run Python commands from `proxmox/homelab/` directory
- **Run tests**: `poetry run pytest tests/` (from proxmox/homelab directory)
- **Test with coverage**: `poetry run coverage run -m pytest` then `poetry run coverage html`
- **Install dependencies**: `cd proxmox/homelab && poetry install` (Poetry is required)
- **Type checking**: `poetry run mypy src/` (ensure type hints on all functions)
- **Code style**: `poetry run flake8 src/` (must pass before commit)
- **Code formatting**: `poetry run black src/` (auto-format code)
- **Import sorting**: `poetry run isort src/` (organize imports)
- **Execute scripts**: `poetry run python script_name.py` (never use system Python)
- **Documentation dependencies**: `pip install -r docs/requirements.txt` (only for docs, outside Poetry)

### SSH Access Patterns
- **Proxmox Hosts**: `ssh root@<hostname>.maas` (e.g., `ssh root@still-fawn.maas`)
- **K3s VMs**: `ssh ubuntu@k3s-vm-<proxmox-host-name>` (e.g., `ssh ubuntu@k3s-vm-still-fawn`)
- **Host Commands**: Use `lshw`, `nvidia-smi`, etc. on individual hosts for hardware verification

### Kubernetes/GitOps
- **Kubernetes Cluster Access**: `export KUBECONFIG=~/kubeconfig` (available on pve host and Mac)
- **Preferred Terminal**: Use Mac terminal when using Claude Code for kubectl commands
- All Kubernetes manifests are managed via GitOps using Flux
- Main GitOps configuration: `gitops/clusters/homelab/kustomization.yaml`
- Test MetalLB LoadBalancer: `proxmox/homelab/scripts/metallb-smoketest.sh`

### Documentation Quality
- Validate Markdown: `markdownlint`
- **Mermaid Diagrams**: Ensure compliance with Mermaid.js syntax - parentheses are not allowed in node/edge descriptions

### GitHub Issues and Git Workflow
- Create GitHub issue before starting work: `gh issue create --title "Brief description" --body "Detailed description"`
- Reference issue in commits: Use format "fixes #123" or "refs #123" in commit messages
- GitHub CLI authentication: `gh auth login` (follow prompts for web-based authentication)

## Architecture Structure

### Core Directories
- `gitops/` - Flux GitOps configuration for Kubernetes cluster management
  - `clusters/homelab/` - Main cluster configuration with apps and infrastructure
- `proxmox/` - Proxmox VE automation scripts and guides
  - `homelab/` - Python package for VM/container management using Poetry
  - `guides/` - Comprehensive setup guides for various services
- `docs/` - Sphinx documentation with extensive guides and runbooks
- `k8s/` - Standalone Kubernetes manifests (legacy, prefer GitOps)
- `raspberrypi-master/` - Balena-based Pi cluster services

### Key Technologies
- **Infrastructure**: Proxmox VE with Ubuntu MAAS for bare metal
- **Orchestration**: Kubernetes (K3s) with Flux GitOps
- **Monitoring**: kube-prometheus-stack deployed via Flux
- **Load Balancing**: MetalLB for LoadBalancer services
- **AI Workloads**: Ollama GPU server, Stable Diffusion WebUI
- **Documentation**: Sphinx with reStructuredText and Markdown

## Development Workflow

### Before Starting Work
- Always create a GitHub issue first: `gh issue create --title "Brief title" --body "Detailed description with acceptance criteria"`
- Reference the issue number in all related commits using "fixes #123" or "refs #123"
- Follow the project's agent guidelines for AI-managed infrastructure

### Documentation Updates
- Every change must include corresponding documentation updates
- Update relevant files in `docs/source/md/` or `proxmox/guides/` as appropriate
- Ensure documentation reflects the current state after changes

### DNS Configuration
The homelab uses a layered DNS approach with OPNsense Unbound DNS and the `.homelab` domain:

#### Network Architecture
- **Domain**: `homelab` (e.g., `service.homelab`)
- **DNS Server**: OPNsense Unbound DNS
- **HTTP Services**: Traefik LoadBalancer at `192.168.4.50`
- **Non-HTTP Services**: Direct MetalLB LoadBalancer IPs (`192.168.4.50-70` pool)

#### Service DNS Patterns
- **HTTP/HTTPS**: Use Traefik IngressRoute → `service.homelab` → `192.168.4.50`
- **TCP/Raw Ports**: Use MetalLB LoadBalancer → `service.homelab` → `192.168.4.5X`

#### DNS Configuration Process
1. **Deploy service** with MetalLB LoadBalancer (gets IP from pool)
2. **Add DNS Override** in OPNsense: 
   - Navigate: Services → Unbound DNS → Overrides
   - Add Host Override: `service.homelab` → `192.168.4.5X`
3. **Test resolution**: `nslookup service.homelab` should return the LoadBalancer IP
4. **Update documentation** with DNS access instructions

#### Service Deployment Format
Always end service deployments with DNS configuration:

```yaml
# Example: After deploying service with MetalLB LoadBalancer
apiVersion: v1
kind: Service
metadata:
  name: example-service
spec:
  type: LoadBalancer
  # MetalLB assigns IP from pool (e.g., 192.168.4.53)
```

**Required DNS Update:**
- OPNsense Unbound DNS Override: `example.homelab` → `192.168.4.53`
- Client access: `example.homelab:port` instead of IP address

### Making Changes
1. For Kubernetes resources: modify files in `gitops/clusters/homelab/`
2. For Proxmox automation: work in `proxmox/homelab/src/homelab/`
3. For documentation: update files in `docs/source/md/`

### Testing Requirements
- **Python changes only**: Run `pytest proxmox/homelab/tests` from repository root
- Type validation: `mypy`
- Style checks: `flake8` and `black --check`
- Coverage: `coverage run -m pytest` followed by `coverage html`
- **Markdown**: Ensure all Markdown files pass `markdownlint`

### Commit Standards
- Reference GitHub issue in every commit
- Start with short summary (under 50 characters)
- Add blank line followed by detailed explanation
- All checks must pass before merging
- **NEVER use `git add .` blindly** - always review files being staged first with `git status`
- Use selective staging: `git add specific-file.yaml` or `git add directory/`
- Verify staged changes with `git diff --cached` before committing

### GitOps Deployment
- Changes to `gitops/` are automatically deployed by Flux
- Flux monitors the repository and applies changes to the cluster
- Key applications managed: monitoring stack, MetalLB, Ollama, Stable Diffusion

## Python Development Best Practices

### Code Quality Standards
All Python code in `proxmox/homelab/` must follow these standards:

#### Testing Requirements
- **100% test coverage**: Every function must have unit tests
- **Mock external calls**: Use `unittest.mock` for Proxmox API, SSH, file operations
- **Test file naming**: `test_<module_name>.py` in `proxmox/homelab/tests/`
- **Run before commit**: `pytest proxmox/homelab/tests` must pass

#### Testing Patterns and Examples
```python
# Mock Proxmox API calls
from unittest import mock
import pytest

def test_vm_creation(monkeypatch, tmp_path):
    # Setup test environment
    ssh_key = tmp_path / "id_rsa.pub"
    ssh_key.write_text("ssh-rsa AAAA")
    monkeypatch.setenv("SSH_PUBKEY_PATH", str(ssh_key))
    monkeypatch.setenv("API_TOKEN", "user!token=abc")
    
    # Mock Proxmox API
    proxmox = mock.MagicMock()
    proxmox.nodes.return_value.qemu.create.return_value = {"status": "success"}
    
    # Test the function
    result = vm_manager.create_vm(proxmox, "test-vm")
    assert result is not None

# Mock SSH operations
@mock.patch('paramiko.SSHClient')
def test_ssh_command_execution(mock_ssh):
    mock_client = mock.MagicMock()
    mock_ssh.return_value = mock_client
    mock_client.exec_command.return_value = (None, mock.MagicMock(), mock.MagicMock())
    
    result = manager.execute_ssh_command("host", "command")
    mock_client.connect.assert_called_once()

# Mock file operations
@mock.patch('builtins.open', mock.mock_open(read_data="config data"))
def test_config_loading():
    result = config.load_config("/fake/path")
    assert "config data" in result
```

#### Code Style Requirements
- **Type hints**: All functions must have complete type annotations
- **Docstrings**: Google-style docstrings for all classes and public methods
- **Error handling**: Explicit exception handling with meaningful messages
- **Logging**: Use Python logging module, not print statements

#### Example Function Structure
```python
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class MonitoringManager:
    """Manages external monitoring deployment and configuration."""
    
    def deploy_uptime_kuma(self, node: str, config: Dict[str, str]) -> Optional[str]:
        """Deploy Uptime Kuma container on specified node.
        
        Args:
            node: Proxmox node name (e.g., 'pve', 'still-fawn')
            config: Container configuration including ports and volumes
            
        Returns:
            Container ID if successful, None if failed
            
        Raises:
            ProxmoxAPIError: If Proxmox API call fails
            SSHConnectionError: If SSH connection fails
        """
        try:
            logger.info(f"Deploying Uptime Kuma on node {node}")
            # Implementation here
            return container_id
        except Exception as e:
            logger.error(f"Failed to deploy on {node}: {e}")
            raise
```

#### Dependency Management
- **Poetry only**: Use `poetry add <package>` for new dependencies
- **Development dependencies**: `poetry add --group dev <package>` for testing tools
- **Lock file**: Always commit `poetry.lock` changes
- **Environment**: Use `.env` files for configuration, never hardcode secrets

#### Testing Configuration
```python
# conftest.py - shared test fixtures
import pytest
from unittest import mock
import tempfile
import os

@pytest.fixture
def mock_proxmox():
    """Mock Proxmox API client for testing."""
    with mock.patch('homelab.proxmox_api.ProxmoxAPI') as mock_api:
        yield mock_api.return_value

@pytest.fixture
def temp_ssh_key(tmp_path, monkeypatch):
    """Create temporary SSH key for testing."""
    key_file = tmp_path / "id_rsa.pub"
    key_file.write_text("ssh-rsa AAAA test@example.com")
    monkeypatch.setenv("SSH_PUBKEY_PATH", str(key_file))
    return str(key_file)

@pytest.fixture
def mock_env(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("API_TOKEN", "test!token=secret")
    monkeypatch.setenv("NODE_1", "test-node")
    monkeypatch.setenv("STORAGE_1", "local-zfs")
```

#### Pre-commit Checklist
Before committing Python code, ensure:
1. `pytest proxmox/homelab/tests` passes (100% success)
2. `coverage run -m pytest proxmox/homelab/tests && coverage report` shows 100% coverage
3. `mypy proxmox/homelab/src` passes with no errors
4. `flake8 proxmox/homelab/src` passes with no violations
5. `black proxmox/homelab/src` formats code consistently
6. `isort proxmox/homelab/src` organizes imports properly

## Important Files
- `AGENTS.md` - AI agent contribution guidelines
- `proxmox/homelab/pyproject.toml` - Python dependencies and project config
- `proxmox/homelab/tests/conftest.py` - Shared test fixtures and configuration
- `gitops/clusters/homelab/kustomization.yaml` - Main GitOps apps and infrastructure
- `docs/requirements.txt` - Documentation build dependencies
- `proxmox/guides/monitoring-guide.md` - Monitoring stack setup via Flux
- `docs/source/md/monitoring-alerting-guide.md` - Email alerting configuration

## Notes
- The homelab runs GPU-accelerated AI workloads (RTX 3070 passthrough)
- Extensive documentation exists for troubleshooting common issues
- All infrastructure changes should go through the GitOps workflow when possible
- Python code follows modern practices with Poetry and pytest
- This repository is specifically designed for AI agent management - follow AGENTS.md guidelines