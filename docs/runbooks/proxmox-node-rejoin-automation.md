# Proxmox Node Rejoin Automation

**Last Updated**: 2026-01-23
**Author**: Claude Code
**Status**: Production-ready, tested on still-fawn recovery

---

## Overview

The `cluster_manager.py` script automates rejoining a Proxmox node to the cluster after a reinstall. This is a complete, end-to-end automation that handles:

- SSH key setup to virgin nodes (using password from `.env`)
- Inter-node SSH key exchange (new node → primary node)
- Cluster state cleanup (removes stale corosync/pmxcfs data)
- Cluster join via `pvecm add --use_ssh`
- GPU passthrough configuration (IOMMU, VFIO, driver blacklist)

**The script is fully idempotent** - running it multiple times on a healthy node does nothing destructive.

---

## Quick Start: Rejoining still-fawn from Scratch

### Prerequisites

1. **Fresh Proxmox installed** on still-fawn with:
   - IP: 192.168.4.17
   - Hostname: still-fawn
   - ZFS root pool (rpool)
   - Network configured and reachable

2. **Password in `.env`**:
   ```bash
   # In ~/code/home/proxmox/homelab/.env
   PVE_ROOT_PASSWORD=<your-proxmox-root-password>
   ```

3. **SSH key exists** at `~/.ssh/id_ed25519_pve.pub` (matches `~/.ssh/config` for `*.maas` hosts)

### Run the Script

```bash
cd ~/code/home/proxmox/homelab
poetry run python src/homelab/cluster_manager.py rejoin still-fawn
```

That's it. The script will:
1. Set up SSH keys (Mac → still-fawn)
2. Remove any stale cluster entry
3. Clean up cluster state on still-fawn
4. Set up inter-node SSH (still-fawn → pumped-piglet)
5. Join the cluster
6. Configure GPU passthrough (AMD Radeon for VAAPI)

### After the Script

1. **Reboot still-fawn** (required for GPU passthrough):
   ```bash
   ssh root@still-fawn.maas reboot
   ```

2. **Restore VM 108** from PBS backup:
   ```bash
   ssh root@still-fawn.maas
   qmrestore pbs:backup/vzdump-qemu-108-2026_01_20-10_30_03.vma.zst 108 --storage local-zfs
   ```

3. **Configure passthrough** for Coral TPU and GPU (see recovery runbook)

4. **Start VM**:
   ```bash
   qm start 108
   ```

---

## Command Reference

### Check Cluster Status

```bash
poetry run python src/homelab/cluster_manager.py status
```

Output:
```
Cluster: homelab
Quorate: True
Votes: 5/6
Nodes:
  - pve (ID: 1)
  - still-fawn (ID: 3)
  - chief-horse (ID: 4)
  - fun-bedbug (ID: 5)
  - pumped-piglet (ID: 6) (local)
```

### Rejoin a Node (Idempotent)

```bash
# Normal run - skips if node is already healthy
poetry run python src/homelab/cluster_manager.py rejoin still-fawn

# Force rejoin even if node appears healthy
poetry run python src/homelab/cluster_manager.py rejoin still-fawn --force
```

### Set Up SSH Keys Only

```bash
poetry run python src/homelab/cluster_manager.py ssh-setup still-fawn
```

### Configure GPU Passthrough Only

```bash
poetry run python src/homelab/cluster_manager.py gpu still-fawn
```

### Remove a Node from Cluster

```bash
poetry run python src/homelab/cluster_manager.py remove still-fawn
```

---

## How It Works

### Step-by-Step Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  REJOIN WORKFLOW                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. CHECK HEALTH                                                            │
│     ├── Is node in cluster membership? (via pumped-piglet)                  │
│     └── Can node run `pvecm status`?                                        │
│         ├── YES → Skip to GPU check                                         │
│         └── NO  → Continue with rejoin                                      │
│                                                                             │
│  2. SSH KEY SETUP (Mac → still-fawn)                                        │
│     ├── Read PVE_ROOT_PASSWORD from .env                                    │
│     ├── Use sshpass to copy ~/.ssh/id_ed25519_pve.pub                       │
│     └── Write to /root/.ssh/authorized_keys (NOT the symlink)               │
│                                                                             │
│  3. REMOVE OLD CLUSTER ENTRY                                                │
│     └── Run `pvecm delnode still-fawn` on pumped-piglet                     │
│                                                                             │
│  4. PREPARE NODE (Clean Cluster State)                                      │
│     ├── Stop pve-cluster, corosync                                          │
│     ├── Delete /var/lib/pve-cluster/* (cached cluster DB)                   │
│     ├── Delete /etc/corosync/*, /var/lib/corosync/*                         │
│     ├── Start pmxcfs in local mode                                          │
│     ├── Delete /etc/pve/nodes/*, qemu-server/*, lxc/*                       │
│     ├── Restart pve-cluster                                                 │
│     └── Wait for `pvesh get /version` to succeed                            │
│                                                                             │
│  5. RE-SETUP SSH KEYS                                                       │
│     └── Prepare step may have reset authorized_keys symlink                 │
│                                                                             │
│  6. INTER-NODE SSH SETUP                                                    │
│     ├── Get still-fawn's /root/.ssh/id_rsa.pub                              │
│     └── Add to pumped-piglet's /etc/pve/priv/authorized_keys                │
│                                                                             │
│  7. JOIN CLUSTER                                                            │
│     ├── Run `pvecm add pumped-piglet.maas --use_ssh` on still-fawn          │
│     └── Run `pvecm updatecerts` on still-fawn                               │
│                                                                             │
│  8. CONFIGURE GPU PASSTHROUGH                                               │
│     ├── Update GRUB (intel_iommu=on iommu=pt)                               │
│     ├── Configure VFIO modules                                              │
│     ├── Blacklist radeon/amdgpu drivers                                     │
│     ├── Bind GPU to vfio-pci                                                │
│     └── Run update-initramfs                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Each Step Exists

| Step | Why It's Needed |
|------|-----------------|
| SSH Key Setup | Fresh Proxmox has no SSH keys from Mac |
| Remove Old Entry | Cluster still has stale node reference |
| Clean Cluster State | Leftover `/var/lib/pve-cluster/` causes "virtual guests exist" error |
| Delete `/etc/pve/nodes/*` | Synced node configs make `pvecm add` think there are VMs |
| Inter-node SSH | `pvecm add --use_ssh` needs still-fawn to SSH into pumped-piglet |
| Wait for pve-cluster | `pvecm add` fails with "Connection refused" if pve-cluster not ready |
| GPU Passthrough | Needs to be configured before VM with GPU can start |

---

## Configuration

### cluster.yaml

The script reads node configuration from `config/cluster.yaml`:

```yaml
cluster:
  name: homelab
  primary_node: pumped-piglet  # Used for cluster operations

nodes:
  - name: still-fawn
    ip: 192.168.4.17
    fqdn: still-fawn.maas
    role: compute
    enabled: true
    gpu_passthrough:
      enabled: true
      gpu_type: amd
      gpu_ids: "1002:67df,1002:aaf0"  # Radeon RX 570/580
      kernel_modules:
        - vfio
        - vfio_iommu_type1
        - vfio_pci
        - vfio_virqfd
      grub_cmdline: "intel_iommu=on iommu=pt"
      blacklist_drivers:
        - radeon
        - amdgpu
    storage:
      - name: local-zfs
        type: zfspool
        pool: rpool/data
        content: [images, rootdir]
```

### .env

Required environment variables in `proxmox/homelab/.env`:

```bash
# Root password for virgin Proxmox nodes (set to your actual password)
PVE_ROOT_PASSWORD=<your-proxmox-root-password>
```

### SSH Config

The script uses `~/.ssh/id_ed25519_pve.pub` which matches the SSH config:

```
# ~/.ssh/config
Host *.maas
  IdentityFile ~/.ssh/id_ed25519_pve
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
```

---

## Idempotency

The script is designed to be run multiple times safely:

### Cluster Rejoin
- **Check**: `is_node_healthy_in_cluster()` verifies:
  - Node appears in `pvecm nodes` output
  - Node can successfully run `pvecm status`
- **Skip**: If both pass, cluster rejoin is skipped
- **Force**: Use `--force` to rejoin anyway

### GPU Passthrough
- **Check**: `is_gpu_passthrough_configured()` verifies:
  - GRUB contains IOMMU flags
  - `/etc/modules-load.d/vfio.conf` exists
  - `/etc/modprobe.d/blacklist-gpu.conf` exists
  - `/etc/modprobe.d/vfio.conf` contains correct GPU IDs
- **Skip**: If all pass, GPU config is skipped
- **Always Checked**: Even if cluster is healthy, GPU config is checked

### SSH Keys
- **Check**: Attempts `ssh -o BatchMode=yes` to test key auth
- **Skip**: If SSH works without password, key setup is skipped

---

## Troubleshooting

### "virtual guests exist" Error

**Symptom**:
```
detected the following error(s):
* this host already contains virtual guests
Check if node may join a cluster failed!
```

**Cause**: Leftover VM configs in `/etc/pve/nodes/` from a previous partial join.

**Fix**: The script now cleans `/etc/pve/nodes/*`, `/etc/pve/qemu-server/*`, `/etc/pve/lxc/*` during prepare. If you still see this:

```bash
ssh root@still-fawn.maas
systemctl stop pve-cluster
killall pmxcfs
rm -rf /var/lib/pve-cluster/*
pmxcfs -l
rm -rf /etc/pve/nodes/* /etc/pve/qemu-server/* /etc/pve/lxc/*
killall pmxcfs
systemctl start pve-cluster
```

### "Connection refused" from pvecm add

**Symptom**:
```
ipcc_send_rec[1] failed: Connection refused
Unable to load access control list: Connection refused
```

**Cause**: `pve-cluster` service not running or not ready.

**Fix**: The script now waits for `pvesh get /version` to succeed. If it still fails:

```bash
ssh root@still-fawn.maas
systemctl restart pve-cluster
sleep 5
pvesh get /version  # Should return JSON
pvecm add pumped-piglet.maas --use_ssh
```

### "unable to copy ssh ID" Error

**Symptom**:
```
unable to copy ssh ID: exit code 1
```

**Cause**: SSH key from still-fawn not in pumped-piglet's authorized_keys.

**Fix**: The script now calls `setup_inter_node_ssh()` before join. Manual fix:

```bash
# Get still-fawn's public key
ssh root@still-fawn.maas cat /root/.ssh/id_rsa.pub

# Add to pumped-piglet
ssh root@pumped-piglet.maas
echo 'ssh-rsa AAAA...' >> /etc/pve/priv/authorized_keys
```

### SSH Key Setup Fails

**Symptom**: Script can't connect to virgin node.

**Check**:
1. `PVE_ROOT_PASSWORD` is set in `.env`
2. `sshpass` is installed: `brew install hudochenkov/sshpass/sshpass`
3. Node is reachable: `ping still-fawn.maas`

---

## File Locations

| File | Purpose |
|------|---------|
| `src/homelab/cluster_manager.py` | Main script |
| `config/cluster.yaml` | Node configuration |
| `.env` | Passwords and secrets |
| `~/.ssh/id_ed25519_pve.pub` | SSH public key for Proxmox nodes |
| `/etc/pve/priv/authorized_keys` | Cluster-shared SSH authorized_keys |
| `/var/lib/pve-cluster/` | Proxmox cluster database (pmxcfs) |

---

## Related Documentation

- [still-fawn Recovery Runbook (2026-01)](still-fawn-recovery-2026-01.md) - Incident-specific recovery steps
- [Proxmox Cluster Node Addition](proxmox-cluster-node-addition.md) - General cluster procedures
- [K3s VM still-fawn Setup](k3s-vm-still-fawn-setup.md) - VM 108 configuration

---

## Tags

proxmox, cluster, pvecm, still-fawn, rejoin, automation, python, cluster_manager, gpu-passthrough, vfio, iommu, ssh-keys, idempotent
