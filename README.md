# home

![Deploy](https://github.com/homeiac/home/workflows/.github/workflows/deploy_to_github.yml/badge.svg)
![BalenaCloud Push](https://github.com/homeiac/home/workflows/BalenaCloud%20Push/badge.svg)

This repository manages my homelab entirely as code so that **AI tools can manage the environment running AI workloads**.
Everything from virtual machines to Kubernetes manifests is stored and documented here.

## Architecture Overview

The design follows a layered approach.
It begins with a clear **purpose**: automate and document the homelab.
AI manages the infrastructure that powers AI workloads.
Below that sits the **automation layer** which contains Proxmox orchestration scripts,
Kubernetes manifests and GitOps configuration for reproducible deployments.
Next comes the **service layer** where LXC containers - created with Tteck's Proxmox VE helper scripts -
and guides describe GPU servers, monitoring, and networking.
Ubuntu MAAS handles bare-metal installs before nodes join Proxmox.
At the base is the **documentation layer** with extensive Sphinx content explaining how everything fits together.

```{mermaid}
graph TD
    Purpose --> Automation
    Automation --> Services
    Services --> Documentation
    Documentation --> Purpose
```

See the [Homelab AI Overview](docs/source/md/homelab_ai_overview.md) for a deeper explanation
and additional diagrams.
See the [Ubuntu MAAS and Proxmox Overview](docs/source/md/maas_proxmox_overview.md)
for details on bare metal installs and container provisioning.

## Guides

* [Ollama GPU Server Guide](proxmox/guides/ollama-gpu-server.md) - deploy via Flux
* [Ollama Service Guide](proxmox/guides/ollama-service-guide.md)
* [Coral TPU Automation System](proxmox/homelab/README_CORAL_AUTOMATION.md) - automated Coral TPU initialization
* [Frigate Storage Migration Report](docs/source/md/frigate-storage-migration-report.md) - Samsung T5 to 3TB HDD migration
* [Stable Diffusion Web UI Guide](proxmox/guides/stable-diffusion-webui-guide.md)
* [Flux Bootstrap Guide](proxmox/guides/flux-guide.md)
* [MetalLB Setup Guide](proxmox/guides/metallb-guide.md)
* [Monitoring Setup Guide](proxmox/guides/monitoring-guide.md) - deployed via Flux
* [Monitoring Troubleshooting](monitoring/docs/troubleshooting.md) - fix common issues
* [K3s Too Many Open Files Runbook](docs/source/md/runbooks/too-many-open-files-k3s.md) - troubleshoot descriptor errors
* [Coral TPU Automation Runbook](docs/source/md/coral-tpu-automation-runbook.md) - maintain and troubleshoot automated Coral TPU initialization
* [Docs Workflow Guide](docs/source/md/docs_workflow_guide.md)
  * documentation is deployed from `master` using `make -C docs html`
* [Docs Build Guide](docs/source/md/docs_build_guide.md) - build docs locally before pushing
* [Docs Symlink Guide](docs/source/md/docs_symlink_guide.md) - fix broken markdown links
* [Docs Publishing Guide](docs/source/md/docs_publishing_guide.md) - update the `gh-pages` branch
* [Python Tests Guide](docs/source/md/guides/python_tests_guide.md)
* [Agent Guidelines](docs/source/md/guides/agents_guidelines.md)
* [Project Documentation](https://homeiac.github.io/home/)

## Proxmox Network Guides

* [2.5 GbE Migration Guide](proxmox/guides/2.5gbe-migration.md) — step-by-step migration from 1 GbE to 2.5 GbE,
  with lessons learned.
* [Flint 3 VLAN40 Split Guide](docs/source/md/runbooks/flint3-vlan40-guide.md) — bridge Wi-Fi while isolating Proxmox
* [VLAN Troubleshooting Checklist & Guide](docs/source/md/runbooks/vlan_troubleshooting_guide.md) -
  diagnose common VLAN issues
