# Homelab AI Overview

This project tracks my homelab entirely as code so that AI tools can deploy and manage the environment running AI workloads. Everything from virtual machines to Kubernetes manifests lives here so the infrastructure can be reproduced and updated automatically.

## Architecture

```{mermaid}
flowchart TD
    Purpose --> Automation
    Automation --> Services
    Services --> Documentation
```

## Purpose

The goal is to let AI systems manage the infrastructure that powers further AI experiments. Keeping every component in version control allows the environment to be rebuilt or modified automatically. This tight feedback loop lets new AI assistants help configure, deploy and operate the homelab itself.

## Automation Layer

Python tools in `proxmox/homelab` drive the Proxmox virtualization platform. Kubernetes manifests and GitOps configuration in `k8s/` and `gitops/` describe the desired cluster state. Together they ensure that virtual machines and containers can be recreated consistently across nodes.

```{mermaid}
flowchart LR
    P[Proxmox API] --> S[Python Scripts]
    S --> K[Kubernetes Manifests]
    K --> G[GitOps]
```

## Service Layer

LXC containers created with Tteck's Proxmox VE helper scripts and Flux-managed manifests provide GPU servers, networking tools and monitoring stacks. Guides under `proxmox/guides/` document each service so AI agents and humans know how everything is configured. These services supply the compute and observability needed for AI workloads.

```{mermaid}
flowchart TD
    GPU[GPU Servers] --> Net[Networking]
    Net --> Mon[Monitoring]
    Mon --> AI[AI Workloads]
```

## Documentation Layer

Sphinx and Markdown content in `docs/` explains the setup and processes. The documentation forms the foundation for automated assistants to reason about the environment and for people to reproduce it locally. Continuous documentation builds keep the information fresh as code changes.

At the core of every layer is the objective: **AI managing AI infrastructure**. Each component reinforces that principle so the homelab can evolve autonomously over time.
