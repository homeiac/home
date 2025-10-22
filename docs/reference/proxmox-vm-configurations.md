# Proxmox VM Configurations Reference

**Last Updated**: October 21, 2025
**Purpose**: Complete VM configuration backup for disaster recovery and documentation

## VM Topology

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Proxmox VE Cluster: homelab                          │
└──────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────────┐
│    pve.maas             │  │  chief-horse.maas        │  │  pumped-piglet.maas      │
│  192.168.4.122          │  │  192.168.4.19            │  │  192.168.4.175           │
│  ┌───────────────────┐  │  │  ┌────────────────────┐  │  │  ┌────────────────────┐  │
│  │ VM 107            │  │  │  │ VM 109             │  │  │  │ VM 105             │  │
│  │ k3s-vm-pve        │  │  │  │ k3s-vm-chief-horse │  │  │  │ k3s-vm-pumped-     │  │
│  │                   │  │  │  │                    │  │  │  │ piglet-gpu         │  │
│  │ 2 CPU / 4GB RAM   │  │  │  │ 2 CPU / 4GB RAM    │  │  │  │ 10 CPU / 48GB RAM  │  │
│  │ 200GB disk        │  │  │  │ 200GB disk         │  │  │  │ 1800GB + 18TB disk │  │
│  │ 192.168.4.238     │  │  │  │ 192.168.4.237      │  │  │  │ 192.168.4.210      │  │
│  │                   │  │  │  │                    │  │  │  │ RTX 3070 GPU       │  │
│  └───────────────────┘  │  │  └────────────────────┘  │  │  └────────────────────┘  │
│  (etcd master)          │  │  (etcd master)           │  │  (etcd master + GPU)     │
└─────────────────────────┘  └──────────────────────────┘  └──────────────────────────┘
                                      │
                                      │ ┌────────────────────────┐
                                      └─┤  VM 116                │
                                        │  haos16.0              │
                                        │  Home Assistant OS     │
                                        │  2 CPU / 2GB RAM       │
                                        │  40GB disk             │
                                        │  DHCP IP               │
                                        └────────────────────────┘

┌──────────────────────────┐
│  fun-bedbug.maas         │
│  192.168.4.172           │
│  ┌────────────────────┐  │
│  │ LXC 113            │  │
│  │ Frigate NVR        │  │
│  │ 4 CPU / 4GB RAM    │  │
│  │ 20GB rootfs        │  │
│  │ 500GB media mount  │  │
│  │ AMD Radeon + Coral │  │
│  └────────────────────┘  │
│  ┌────────────────────┐  │
│  │ LXC 112            │  │
│  │ Docker Host        │  │
│  │ 2 CPU / 2GB RAM    │  │
│  │ 24GB rootfs        │  │
│  └────────────────────┘  │
└──────────────────────────┘
```

## VM 105: k3s-vm-pumped-piglet-gpu

**Critical VM**: Main K3s GPU node hosting all migrated workloads

```
┌──────────────────────────────────────────────────────────────────────────┐
│                   VM 105: k3s-vm-pumped-piglet-gpu                       │
│                   Host: pumped-piglet.maas (192.168.4.175)               │
├──────────────────────────────────────────────────────────────────────────┤
│ CPU:      10 cores (host CPU, AMD Ryzen 5 5600G)                        │
│ Memory:   49152 MB (48 GB)                                               │
│ Machine:  Q35 with UEFI (efidisk0)                                       │
│ BIOS:     OVMF (UEFI), pre-enrolled-keys=0                               │
│ OS:       Ubuntu 24.04.3 LTS (cloud-init)                                │
│ IP:       192.168.4.210 (DHCP)                                           │
│ Hostname: k3s-vm-pumped-piglet                                           │
│ User:     ubuntu (cloud-init configured)                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ Storage:                                                                 │
│   scsi0:     1800GB (local-2TB-zfs:vm-105-disk-1)  → Root /             │
│   scsi1:     18000GB (local-20TB-zfs:vm-105-disk-0) → /mnt/samba-storage│
│   efidisk0:  1M (local-2TB-zfs:vm-105-disk-2)      → EFI vars           │
│   ide2:      CloudInit ISO (local-2TB-zfs:vm-105-cloudinit)             │
│                                                                          │
│ GPU Passthrough:                                                         │
│   hostpci0:  0000:b3:00.0 (NVIDIA RTX 3070), pcie=1                     │
│                                                                          │
│ Network:                                                                 │
│   net0:      virtio, MAC=BC:24:11:44:73:D6, bridge=vmbr0                │
│                                                                          │
│ Cloud-Init:                                                              │
│   Custom:    user=local:snippets/install-k3sup-qemu-agent.yaml         │
│   User:      ubuntu                                                      │
│   SSH Keys:  Multiple keys from all Proxmox hosts + workstation        │
└──────────────────────────────────────────────────────────────────────────┘
```

### VM 105 Configuration File

```ini
agent: enabled=1
bios: ovmf
boot: order=scsi0
cicustom: user=local:snippets/install-k3sup-qemu-agent.yaml
ciuser: ubuntu
cores: 10
cpu: host
efidisk0: local-2TB-zfs:vm-105-disk-2,efitype=4m,pre-enrolled-keys=0,size=1M
hostpci0: 0000:b3:00.0,pcie=1
ide2: local-2TB-zfs:vm-105-cloudinit,media=cdrom
ipconfig0: ip=dhcp
machine: q35
memory: 49152
name: k3s-vm-pumped-piglet
net0: virtio=BC:24:11:44:73:D6,bridge=vmbr0,firewall=0
scsi0: local-2TB-zfs:vm-105-disk-1,size=1800G
scsi1: local-20TB-zfs:vm-105-disk-0,size=18000G
scsihw: virtio-scsi-pci
smbios1: uuid=4abec58f-ba68-4f1f-950a-703f55838a4e
vmgenid: 0479cb19-81d7-4a76-ba7c-3cfbabc7f55c
```

### VM 105 Storage Layout

```mermaid
graph TB
    subgraph VM_105[VM 105 - k3s-vm-pumped-piglet-gpu]
        ROOT[scsi0: 1800GB<br>Root filesystem<br>local-2TB-zfs]
        DATA[scsi1: 18000GB<br>Data storage<br>local-20TB-zfs]
        EFI[efidisk0: 1M<br>UEFI variables<br>local-2TB-zfs]
    end

    subgraph Mounts[Mounted Filesystems]
        ROOT_FS[ext4: /<br>System + K3s]
        SAMBA_FS[ext4: /mnt/samba-storage<br>18TB formatted]
        SYMLINK[/mnt/smb_data → /mnt/samba-storage/smb_data]
    end

    subgraph K8s_Storage[Kubernetes Storage]
        PROM[Prometheus TSDB<br>500Gi PVC<br>/mnt/smb_data/prometheus]
        SAMBA_SHARES[Samba Shares<br>/mnt/smb_data]
        LOCAL_PVS[Other PVCs<br>local-path provisioner<br>/var/lib/rancher/k3s/storage]
    end

    ROOT --> ROOT_FS
    DATA --> SAMBA_FS
    SAMBA_FS --> SYMLINK
    SYMLINK --> PROM
    SYMLINK --> SAMBA_SHARES
    ROOT_FS --> LOCAL_PVS
```

**Disk Layout**:
```
/dev/sda (scsi0 - 1800GB):
  └─ /dev/sda1 → / (root filesystem, ext4)

/dev/sdb (scsi1 - 18000GB):
  └─ /dev/sdb1 → /mnt/samba-storage (ext4)
      └─ /mnt/smb_data (symlink to /mnt/samba-storage/smb_data)
          ├─ prometheus/  (500Gi PVC for Prometheus TSDB)
          └─ (Samba share directories)
```

**fstab Entry**:
```
/dev/sdb /mnt/samba-storage ext4 defaults 0 2
```

### VM 105 Recreation Commands

```bash
# On pumped-piglet.maas
# IMPORTANT: GPU passthrough requires IOMMU and specific PCI device

# Step 1: Create VM with UEFI and Q35
qm create 105 \
  --name k3s-vm-pumped-piglet \
  --machine q35 \
  --bios ovmf \
  --cores 10 \
  --cpu host \
  --memory 49152 \
  --scsihw virtio-scsi-pci

# Step 2: Add EFI disk
qm set 105 --efidisk0 local-2TB-zfs:1,efitype=4m,pre-enrolled-keys=0

# Step 3: Add root disk (1800GB)
qm set 105 --scsi0 local-2TB-zfs:1800

# Step 4: Add data disk (18TB)
qm set 105 --scsi1 local-20TB-zfs:18000

# Step 5: Add network
qm set 105 --net0 virtio,bridge=vmbr0,firewall=0

# Step 6: GPU passthrough (find PCI address first: lspci | grep NVIDIA)
qm set 105 --hostpci0 0000:b3:00.0,pcie=1

# Step 7: Cloud-init setup
qm set 105 --ide2 local-2TB-zfs:cloudinit
qm set 105 --ciuser ubuntu
qm set 105 --ipconfig0 ip=dhcp
qm set 105 --cicustom user=local:snippets/install-k3sup-qemu-agent.yaml
qm set 105 --sshkeys /path/to/authorized_keys.pub

# Step 8: Enable QEMU agent
qm set 105 --agent enabled=1

# Step 9: Set boot order
qm set 105 --boot order=scsi0

# Step 10: Import Ubuntu cloud image (if starting from scratch)
# wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
# qm importdisk 105 noble-server-cloudimg-amd64.img local-2TB-zfs
# qm set 105 --scsi0 local-2TB-zfs:vm-105-disk-0

# Step 11: Resize root disk after import (if needed)
# qm resize 105 scsi0 +1700G

# Step 12: Start VM
qm start 105

# Step 13: Format and mount data disk (inside VM)
ssh ubuntu@192.168.4.210 <<'EOF'
  sudo mkfs.ext4 -F /dev/sdb
  sudo mkdir -p /mnt/samba-storage
  sudo mount /dev/sdb /mnt/samba-storage
  echo '/dev/sdb /mnt/samba-storage ext4 defaults 0 2' | sudo tee -a /etc/fstab
  sudo mkdir -p /mnt/samba-storage/smb_data
  sudo ln -s /mnt/samba-storage/smb_data /mnt/smb_data
EOF
```

## VM 107: k3s-vm-pve

**Role**: K3s control-plane + etcd master

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        VM 107: k3s-vm-pve                                │
│                        Host: pve.maas (192.168.4.122)                    │
├──────────────────────────────────────────────────────────────────────────┤
│ CPU:      2 cores (host CPU, Intel Xeon)                                │
│ Memory:   4000 MB (4 GB)                                                 │
│ Machine:  Default                                                        │
│ BIOS:     SeaBIOS                                                        │
│ OS:       Ubuntu 24.04.2 LTS (cloud-init)                                │
│ IP:       192.168.4.238 (DHCP)                                           │
│ Hostname: k3s-vm-pve                                                     │
│ User:     ubuntu (cloud-init configured)                                 │
│ Onboot:   Yes (auto-start with Proxmox)                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ Storage:                                                                 │
│   scsi0:  200GB (local-zfs:vm-107-disk-0) → Root /                      │
│   ide2:   CloudInit ISO (local-zfs:vm-107-cloudinit)                    │
│                                                                          │
│ Network:                                                                 │
│   net0:   virtio, MAC=BC:24:11:3B:7A:A7, bridge=vmbr25gbe (2.5GbE)      │
│   net1:   virtio, MAC=BC:24:11:42:A9:81, bridge=vmbr0 (1GbE)            │
│                                                                          │
│ Cloud-Init:                                                              │
│   Custom: user=local:snippets/install-k3sup-qemu-agent.yaml            │
│   User:   ubuntu (password set, not in git)                             │
└──────────────────────────────────────────────────────────────────────────┘
```

### VM 107 Configuration File

```ini
agent: 1
balloon: 2000
boot: c
bootdisk: scsi0
cicustom: user=local:snippets/install-k3sup-qemu-agent.yaml
ciuser: ubuntu
cores: 2
cpu: host
ide2: local-zfs:vm-107-cloudinit,media=cdrom
ipconfig0: ip=dhcp
memory: 4000
name: k3s-vm-pve
net0: virtio=BC:24:11:3B:7A:A7,bridge=vmbr25gbe
net1: virtio=BC:24:11:42:A9:81,bridge=vmbr0
numa: 0
onboot: 1
scsi0: local-zfs:vm-107-disk-0,size=200G
scsihw: virtio-scsi-pci
shares: 1000
smbios1: uuid=658589db-2a51-452a-885a-5472ebb4a84e
sockets: 1
vmgenid: bdc330f2-c8c1-431b-91a2-5ca72903388d
```

### VM 107 Recreation Commands

```bash
# On pve.maas
qm create 107 \
  --name k3s-vm-pve \
  --cores 2 \
  --cpu host \
  --memory 4000 \
  --balloon 2000 \
  --numa 0 \
  --shares 1000 \
  --scsihw virtio-scsi-pci \
  --onboot 1

qm set 107 --scsi0 local-zfs:200
qm set 107 --net0 virtio,bridge=vmbr25gbe
qm set 107 --net1 virtio,bridge=vmbr0
qm set 107 --ide2 local-zfs:cloudinit
qm set 107 --ciuser ubuntu
qm set 107 --ipconfig0 ip=dhcp
qm set 107 --cicustom user=local:snippets/install-k3sup-qemu-agent.yaml
qm set 107 --agent 1
qm set 107 --boot c --bootdisk scsi0

# Import cloud image and resize as needed
# qm start 107
```

## VM 109: k3s-vm-chief-horse

**Role**: K3s control-plane + etcd master

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    VM 109: k3s-vm-chief-horse                            │
│                    Host: chief-horse.maas (192.168.4.19)                 │
├──────────────────────────────────────────────────────────────────────────┤
│ CPU:      2 cores (host CPU, Intel Xeon)                                │
│ Memory:   4000 MB (4 GB)                                                 │
│ Machine:  Default                                                        │
│ BIOS:     SeaBIOS                                                        │
│ OS:       Ubuntu 24.04.2 LTS (cloud-init)                                │
│ IP:       192.168.4.237 (DHCP)                                           │
│ Hostname: k3s-vm-chief-horse                                             │
│ User:     ubuntu (cloud-init configured)                                 │
│ Onboot:   Yes                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│ Storage:                                                                 │
│   scsi0:  200GB (local-256-gb-zfs:vm-109-disk-0) → Root /               │
│   ide2:   CloudInit ISO (local-256-gb-zfs:vm-109-cloudinit)             │
│                                                                          │
│ Network:                                                                 │
│   net0:   virtio, MAC=BC:24:11:1A:38:07, bridge=vmbr0                   │
│                                                                          │
│ Cloud-Init:                                                              │
│   Custom: user=local:snippets/install-k3sup-qemu-agent.yaml            │
│   User:   ubuntu (password set, not in git)                             │
└──────────────────────────────────────────────────────────────────────────┘
```

### VM 109 Configuration File

```ini
agent: 1
boot: c
bootdisk: scsi0
cicustom: user=local:snippets/install-k3sup-qemu-agent.yaml
ciuser: ubuntu
cores: 2
cpu: host
ide2: local-256-gb-zfs:vm-109-cloudinit,media=cdrom
ipconfig0: ip=dhcp
memory: 4000
name: k3s-vm-chief-horse
net0: virtio=BC:24:11:1A:38:07,bridge=vmbr0
numa: 0
onboot: 1
scsi0: local-256-gb-zfs:vm-109-disk-0,size=200G
scsihw: virtio-scsi-pci
smbios1: uuid=381e20b8-bb6e-430d-a226-de8d746e88dc
sockets: 1
vmgenid: 781b3d64-b74c-45ca-97c6-afbc149444df
```

### VM 109 Recreation Commands

```bash
# On chief-horse.maas
qm create 109 \
  --name k3s-vm-chief-horse \
  --cores 2 \
  --cpu host \
  --memory 4000 \
  --numa 0 \
  --scsihw virtio-scsi-pci \
  --onboot 1

qm set 109 --scsi0 local-256-gb-zfs:200
qm set 109 --net0 virtio,bridge=vmbr0
qm set 109 --ide2 local-256-gb-zfs:cloudinit
qm set 109 --ciuser ubuntu
qm set 109 --ipconfig0 ip=dhcp
qm set 109 --cicustom user=local:snippets/install-k3sup-qemu-agent.yaml
qm set 109 --agent 1
qm set 109 --boot c --bootdisk scsi0

# Import cloud image and resize as needed
# qm start 109
```

## VM 116: haos16.0 (Home Assistant OS)

**Role**: Home Assistant Operating System

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        VM 116: haos16.0                                  │
│                   Host: chief-horse.maas (192.168.4.19)                  │
├──────────────────────────────────────────────────────────────────────────┤
│ CPU:      2 cores (host CPU)                                             │
│ Memory:   2048 MB (2 GB)                                                 │
│ Machine:  Default                                                        │
│ BIOS:     OVMF (UEFI)                                                    │
│ OS:       Home Assistant OS 16.0                                         │
│ IP:       DHCP (check DHCP server)                                       │
│ Hostname: haos16.0                                                       │
│ Onboot:   Yes                                                            │
│ Tags:     community-script                                               │
├──────────────────────────────────────────────────────────────────────────┤
│ Storage:                                                                 │
│   scsi0:  40GB (local:116/vm-116-disk-1.raw) → Root /, cache=writethrough│
│   efidisk0: 4MB (local:116/vm-116-disk-0.raw) → EFI vars                │
│                                                                          │
│ Network:                                                                 │
│   net0:   virtio, MAC=02:86:5F:DF:2B:0B, bridge=vmbr0                   │
│   net1:   virtio, MAC=BC:24:11:21:F4:AB, bridge=vmbr1                   │
│   net2:   virtio, MAC=BC:24:11:BD:9A:ED, bridge=vmbr2                   │
│                                                                          │
│ Special:  localtime=1 (use host time), tablet=0 (disable tablet)        │
└──────────────────────────────────────────────────────────────────────────┘
```

### VM 116 Configuration File

```ini
agent: 1
bios: ovmf
boot: order=scsi0
cores: 2
cpu: host
efidisk0: local:116/vm-116-disk-0.raw,efitype=4m,size=4M
localtime: 1
memory: 2048
name: haos16.0
net0: virtio=02:86:5F:DF:2B:0B,bridge=vmbr0
net1: virtio=BC:24:11:21:F4:AB,bridge=vmbr1
net2: virtio=BC:24:11:BD:9A:ED,bridge=vmbr2
onboot: 1
ostype: l26
scsi0: local:116/vm-116-disk-1.raw,cache=writethrough,size=40G
scsihw: virtio-scsi-pci
smbios1: uuid=eb326121-5320-421f-88b7-c9b7c1dafa79
tablet: 0
tags: community-script
vmgenid: 30dd1bf8-c596-4cba-b678-b1b266e6cead
```

### VM 116 Recreation Commands

```bash
# On chief-horse.maas
# Home Assistant OS is typically installed via PVE Helper Scripts
# URL: https://community-scripts.github.io/ProxmoxVE/

# Manual creation (if needed):
qm create 116 \
  --name haos16.0 \
  --bios ovmf \
  --cores 2 \
  --cpu host \
  --memory 2048 \
  --scsihw virtio-scsi-pci \
  --ostype l26 \
  --localtime 1 \
  --tablet 0 \
  --onboot 1 \
  --tags community-script

qm set 116 --efidisk0 local:4,efitype=4m
qm set 116 --scsi0 local:40,cache=writethrough
qm set 116 --net0 virtio,bridge=vmbr0
qm set 116 --net1 virtio,bridge=vmbr1
qm set 116 --net2 virtio,bridge=vmbr2
qm set 116 --boot order=scsi0
qm set 116 --agent 1

# Download and import Home Assistant OS image
# wget https://github.com/home-assistant/operating-system/releases/download/16.0/haos_ova-16.0.qcow2
# qm importdisk 116 haos_ova-16.0.qcow2 local
# qm set 116 --scsi0 local:116/vm-116-disk-1.raw

# qm start 116
```

## LXC Containers

### LXC 113: Frigate NVR

**Host**: fun-bedbug.maas (192.168.4.172)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     LXC 113: Frigate NVR                                 │
│                     Host: fun-bedbug.maas                                │
├──────────────────────────────────────────────────────────────────────────┤
│ Arch:     amd64                                                          │
│ OS:       Debian (privileged container)                                  │
│ CPU:      4 cores                                                        │
│ Memory:   4096 MB (4 GB)                                                 │
│ Swap:     512 MB                                                         │
│ Hostname: frigate                                                        │
│ IP:       DHCP                                                           │
│ Onboot:   Yes (startup delay: 120s)                                     │
│ Tags:     community-script, nvr                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ Storage:                                                                 │
│   rootfs: 20GB (local:113/vm-113-disk-0.raw)                            │
│   mp0:    500GB (local-3TB-backup:subvol-113-disk-0) → /media          │
│           mountoptions=noatime, backup=1                                 │
│                                                                          │
│ Network:                                                                 │
│   eth0:   veth, MAC=BC:24:11:1F:05:27, bridge=vmbr0, ip=dhcp           │
│                                                                          │
│ Hardware Passthrough:                                                    │
│   - Google Coral TPU (USB device /dev/bus/usb/003/004)                  │
│   - AMD Radeon R5 GPU (renderD128, fb0, /dev/dri)                       │
│   - USB serial devices (ttyUSB0, ttyUSB1, ttyACM0, ttyACM1)            │
│                                                                          │
│ Features: nesting=1 (Docker support)                                    │
│ Capabilities: All devices allowed, cap.drop cleared                     │
└──────────────────────────────────────────────────────────────────────────┘
```

### LXC 113 Configuration File

```ini
arch: amd64
cores: 4
features: nesting=1
hostname: frigate
memory: 4096
mp0: local-3TB-backup:subvol-113-disk-0,mp=/media,backup=1,mountoptions=noatime,size=500G
net0: name=eth0,bridge=vmbr0,hwaddr=BC:24:11:1F:05:27,ip=dhcp,type=veth
onboot: 1
ostype: debian
rootfs: local:113/vm-113-disk-0.raw,size=20G
startup: up=120
swap: 512
tags: community-script;nvr

# Device passthrough (cgroup2 rules)
lxc.cgroup2.devices.allow: a
lxc.cap.drop:
lxc.cgroup2.devices.allow: c 188:* rwm
lxc.cgroup2.devices.allow: c 189:* rwm
lxc.cgroup2.devices.allow: c 226:0 rwm
lxc.cgroup2.devices.allow: c 226:128 rwm
lxc.cgroup2.devices.allow: c 29:0 rwm

# Mount entries for hardware
lxc.mount.entry: /dev/serial/by-id  dev/serial/by-id  none bind,optional,create=dir
lxc.mount.entry: /dev/ttyUSB0       dev/ttyUSB0       none bind,optional,create=file
lxc.mount.entry: /dev/ttyUSB1       dev/ttyUSB1       none bind,optional,create=file
lxc.mount.entry: /dev/ttyACM0       dev/ttyACM0       none bind,optional,create=file
lxc.mount.entry: /dev/ttyACM1       dev/ttyACM1       none bind,optional,create=file
lxc.mount.entry: /dev/fb0 dev/fb0 none bind,optional,create=file
lxc.mount.entry: /dev/dri dev/dri none bind,optional,create=dir
lxc.mount.entry: /dev/dri/renderD128 dev/dri/renderD128 none bind,optional,create=file

# USB device passthrough
dev0: /dev/bus/usb/003/004
```

### LXC 113 Recreation Commands

```bash
# On fun-bedbug.maas
# Frigate is typically installed via PVE Helper Scripts
# URL: https://community-scripts.github.io/ProxmoxVE/

# Manual creation example:
pct create 113 \
  local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname frigate \
  --cores 4 \
  --memory 4096 \
  --swap 512 \
  --rootfs local:20 \
  --mp0 local-3TB-backup:500,mp=/media,backup=1,mountoptions=noatime \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --features nesting=1 \
  --onboot 1 \
  --startup up=120 \
  --tags community-script,nvr

# Add device passthrough (edit /etc/pve/lxc/113.conf manually)
# Add Google Coral TPU and AMD GPU device rules as shown above

# Start container
pct start 113
```

### LXC 112: Docker Host

**Host**: fun-bedbug.maas (192.168.4.172)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     LXC 112: Docker Host                                 │
│                     Host: fun-bedbug.maas                                │
├──────────────────────────────────────────────────────────────────────────┤
│ Arch:     amd64                                                          │
│ OS:       Debian (unprivileged container)                                │
│ CPU:      2 cores                                                        │
│ Memory:   2048 MB (2 GB)                                                 │
│ Swap:     512 MB                                                         │
│ Hostname: docker                                                         │
│ IP:       DHCP (IPv4 + IPv6)                                             │
│ Onboot:   Yes                                                            │
│ Tags:     community-script, docker                                       │
├──────────────────────────────────────────────────────────────────────────┤
│ Storage:                                                                 │
│   rootfs: 24GB (local:112/vm-112-disk-0.raw)                            │
│                                                                          │
│ Network:                                                                 │
│   eth0:   veth, MAC=BC:24:11:5F:CD:81, bridge=vmbr0, ip=dhcp,ip6=dhcp  │
│                                                                          │
│ Features: nesting=1, keyctl=1 (Docker support)                          │
│ Unprivileged: Yes (safer for Docker workloads)                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### LXC 112 Configuration File

```ini
arch: amd64
cores: 2
features: keyctl=1,nesting=1
hostname: docker
memory: 2048
net0: name=eth0,bridge=vmbr0,hwaddr=BC:24:11:5F:CD:81,ip=dhcp,ip6=dhcp,type=veth
onboot: 1
ostype: debian
rootfs: local:112/vm-112-disk-0.raw,size=24G
swap: 512
tags: community-script;docker
unprivileged: 1
```

### LXC 112 Recreation Commands

```bash
# On fun-bedbug.maas
# Docker LXC is typically installed via PVE Helper Scripts
# URL: https://community-scripts.github.io/ProxmoxVE/

# Manual creation:
pct create 112 \
  local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname docker \
  --cores 2 \
  --memory 2048 \
  --swap 512 \
  --rootfs local:24 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp,ip6=dhcp \
  --features nesting=1,keyctl=1 \
  --onboot 1 \
  --unprivileged 1 \
  --tags community-script,docker

# Start container
pct start 112

# Install Docker inside container
pct exec 112 -- bash -c "curl -fsSL https://get.docker.com | sh"
```

## Cloud-Init Snippet

**Location**: `/var/lib/vz/snippets/install-k3sup-qemu-agent.yaml` (on each Proxmox host)

```yaml
#cloud-config
package_update: true
package_upgrade: true
packages:
  - qemu-guest-agent
  - curl
  - wget
  - git
  - net-tools
runcmd:
  - systemctl start qemu-guest-agent
  - systemctl enable qemu-guest-agent
```

**Purpose**: Automatically installs QEMU guest agent and basic utilities on VM first boot

## Disaster Recovery Procedure

### VM Recovery Steps

1. **Recreate VM** using commands above
2. **Import cloud image** (if starting from scratch)
3. **Restore K3s configuration**:
   ```bash
   # On first master node
   curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.32.4+k3s1 sh -s - server --cluster-init

   # Get token for other nodes
   sudo cat /var/lib/rancher/k3s/server/token

   # On additional master nodes
   curl -sfL https://get.k3s.io | K3S_URL=https://<first-master-ip>:6443 K3S_TOKEN=<token> INSTALL_K3S_VERSION=v1.32.4+k3s1 sh -s - server
   ```

4. **Restore kubeconfig**:
   ```bash
   # From master node
   sudo cat /etc/rancher/k3s/k3s.yaml > ~/kubeconfig
   # Edit server URL to match your setup
   ```

5. **GitOps auto-recovery**: Flux will automatically reconcile all workloads from GitHub repo

### GPU Passthrough Requirements

**IMPORTANT**: VM 105 requires GPU passthrough configuration on Proxmox host.

See: `docs/runbooks/proxmox-gpu-passthrough-k3s-node.md` for complete procedure.

**Quick checklist**:
- IOMMU enabled in BIOS
- GRUB/kernel parameters: `intel_iommu=on` or `amd_iommu=on`
- VFIO modules loaded
- GPU isolated from host
- UEFI + Q35 machine type
- Pre-enrolled-keys=0 for NVIDIA drivers

## Related Documentation

- [Homelab Service Inventory](homelab-service-inventory.md)
- [K3s Node Addition Blueprint](../runbooks/k3s-node-addition-blueprint.md)
- [GPU Passthrough Runbook](../runbooks/proxmox-gpu-passthrough-k3s-node.md)
- [Proxmox 2.5GbE USB Adapter Configuration](../runbooks/proxmox-usb-2.5gbe-adapter-configuration.md)
- [K3s Workload Migration Runbook](../runbooks/k3s-workload-migration-after-still-fawn-loss.md)

## Tags

proxmox, proxmox-ve, vm-configuration, disaster-recovery, backup, k3s, kubernetes, kubernettes, lxc, frigate, home-assistant, gpu-passthrough, nvidia, cloud-init, qemu, kvm, infrastructure-as-code

## Version History

- **v1.0** (Oct 21, 2025): Initial VM configuration documentation after still-fawn failure
