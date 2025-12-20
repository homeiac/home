# RKE2 + Rancher Windows Worker Node Evaluation

Scripts to set up RKE2 with Rancher UI and a Windows Server 2022 worker node for evaluating Windows K8s agents for disk-heavy ADO builds.

## Architecture

```
pumped-piglet.maas (Proxmox)
├── VM 200: rancher-server (Ubuntu 24.04, 4 vCPU, 8GB RAM)
│   └── RKE2 control plane + Rancher UI
│
└── VM 201: windows-worker (Windows Server 2022, 8 vCPU, 16GB RAM)
    └── RKE2 Windows worker node
```

## Quick Start

```bash
# 1. Download required ISOs
./00-download-isos.sh
# Manually download Windows Server 2022 eval and upload to Proxmox

# 2. Create and start Rancher VM
./01-create-rancher-vm.sh

# 3. Install RKE2 + Rancher (wait ~5 min for VM boot first)
./02-install-rke2-rancher.sh

# 4. Add DNS: rancher.homelab -> 192.168.4.200 in OPNsense

# 5. Create Windows VM
./03-create-windows-vm.sh

# 6. Install Windows via Proxmox console (load VirtIO drivers)

# 7. On Windows, run the prep script:
#    Copy 04-prep-windows-rke2.ps1 to Windows and run as Administrator

# 8. In Rancher UI, get Windows join command and run on Windows

# 9. Verify: kubectl get nodes shows Windows node Ready
```

## Cleanup

```bash
./99-cleanup.sh
```

Removes both VMs. Don't forget to remove DNS entry in OPNsense.

## Network

- Uses existing `vmbr0` bridge on 192.168.4.x
- No new bridges or VLANs created
- Static IPs: 192.168.4.200 (Rancher), 192.168.4.201 (Windows)

## Resources Required

| VM | vCPU | RAM | Disk |
|----|------|-----|------|
| rancher-server | 4 | 8GB | 100GB |
| windows-worker | 8 | 16GB | 200GB |
| **Total** | 12 | 24GB | 300GB |

## Credentials

- Rancher VM: ubuntu / ubuntu123 (change immediately)
- Rancher UI: admin / admin (prompted to change on first login)
- Windows: Set during Windows install

## Troubleshooting

### RKE2 not starting
```bash
ssh ubuntu@192.168.4.200
sudo journalctl -u rke2-server -f
```

### Windows node not joining
- Check firewall rules on Windows
- Verify containerd is running: `Get-Service containerd`
- Check RKE2 agent logs on Windows: `Get-Content C:\var\log\rke2-agent.log`

### Out of memory on pumped-piglet
The existing K3s VM uses ~58GB (includes cache). If OOM occurs:
- Reduce Windows VM RAM to 12GB
- Or reduce Rancher VM RAM to 6GB
