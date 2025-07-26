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
- Run tests: `pytest proxmox/homelab/tests`
- Install Python dependencies: `pip install -r docs/requirements.txt`
- The Python code uses Poetry for dependency management (see `proxmox/homelab/pyproject.toml`)
- Type checking: `mypy`
- Code style: `flake8`
- Code formatting: `black --check`
- Coverage: `coverage run -m pytest` then `coverage html`

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

## Important Files
- `AGENTS.md` - AI agent contribution guidelines
- `proxmox/homelab/pyproject.toml` - Python dependencies and project config
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