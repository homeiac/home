# Ubuntu MAAS and Proxmox Overview

Ubuntu MAAS provisions bare metal machines in the homelab. It handles network booting, disk imaging and remote installs so new nodes are ready without manual intervention. Once a machine is installed it can join the Proxmox cluster or operate standalone.

Proxmox provides virtualization and container management. The cluster runs lightweight LXC containers and full VMs depending on workload needs. LXC guests are created using [Tteck's Proxmox VE helper scripts](https://github.com/tteck/Proxmox), which simplify container creation with sensible defaults and hardware passthrough options.

```{mermaid}
flowchart LR
    MAAS[Ubuntu MAAS] --> PX[Proxmox Cluster]
    PX --> LXC[LXC Containers]
    PX --> VM[Virtual Machines]
```

Together MAAS and Proxmox form the foundation for experimenting with networking, distributed storage and AI services while keeping everything reproducible as code.
