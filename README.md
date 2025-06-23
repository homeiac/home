# home

![Deploy](https://github.com/homeiac/home/workflows/.github/workflows/deploy_to_github.yml/badge.svg)
![BalenaCloud Push](https://github.com/homeiac/home/workflows/BalenaCloud%20Push/badge.svg)

This repository manages my homelab entirely as code so that **AI tools can manage the environment running AI workloads**. Everything from virtual machines to Kubernetes manifests is stored and documented here.

## Architecture Overview

The design follows a layered approach. It begins with a clear **purpose**: automate and document the homelab using principles where AI manages the infrastructure that powers AI workloads. Below that sits the **automation layer** which contains Proxmox orchestration scripts, Kubernetes manifests and GitOps configuration for reproducible deployments. Next comes the **service layer** where LXC containers - created with Tteck's Proxmox VE helper scripts - and guides describe GPU servers, monitoring, and networking. Ubuntu MAAS handles bare-metal installs before nodes join Proxmox. At the base is the **documentation layer** with extensive Sphinx content explaining how everything fits together.

```{mermaid}
graph TD
    Purpose --> Automation
    Automation --> Services
    Services --> Documentation
    Documentation --> Purpose
```

See the [Homelab AI Overview](docs/source/md/homelab_ai_overview.md) for a deeper explanation and additional diagrams.
See the [Ubuntu MAAS and Proxmox Overview](docs/source/md/maas_proxmox_overview.md) for details on bare metal installs and container provisioning.

## Guides

* [Ollama GPU Server Guide](proxmox/guides/ollama-gpu-server.md) - deploy via Flux
* [Ollama Service Guide](proxmox/guides/ollama-service-guide.md)
* [Stable Diffusion Web UI Guide](proxmox/guides/stable-diffusion-webui-guide.md)
* [Proxmox WiFi Routing Guide](proxmox/guides/wifi_routing.md)
* [Flux Bootstrap Guide](proxmox/guides/flux-guide.md)
* [MetalLB Setup Guide](proxmox/guides/metallb-guide.md)
* [Monitoring Setup Guide](proxmox/guides/monitoring-guide.md) - deployed via Flux
* [Homelab Local DNS Resolution Guide](docs/source/md/homelab_local_dns_resolution_guide.md)
* [Docs Workflow Guide](docs/source/md/docs_workflow_guide.md) - documentation is deployed from `master` using `make -C docs html`
* [Docs Build Guide](docs/source/md/docs_build_guide.md) - build docs locally before pushing
* [Docs Symlink Guide](docs/source/md/docs_symlink_guide.md) - fix broken markdown links
* [Docs Publishing Guide](docs/source/md/docs_publishing_guide.md) - update the `gh-pages` branch
* [Python Tests Guide](docs/source/md/guides/python_tests_guide.md)
* [Project Documentation](https://homeiac.github.io/home/)
