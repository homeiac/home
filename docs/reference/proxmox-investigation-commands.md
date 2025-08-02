# Proxmox Investigation Commands

*Commands for investigating Proxmox VE infrastructure state*

## Prerequisites
- SSH access to Proxmox nodes
- Access pattern: `ssh root@<hostname>.maas` or appropriate SSH method
- Proxmox VE API access (pvesh) available on nodes

## Cluster Overview
```bash
# Cluster status and resources
pvesh get /cluster/resources
pvesh get /cluster/status
pvesh get /version

# Node information
pvesh get /nodes
pvesh get /nodes/<node-name>/status
```

## Virtual Machine Investigation
```bash
# List VMs on specific node
pvesh get /nodes/<node-name>/qemu

# VM details and status
pvesh get /nodes/<node-name>/qemu/<vmid>/status/current
pvesh get /nodes/<node-name>/qemu/<vmid>/config

# VM resource usage
pvesh get /nodes/<node-name>/qemu/<vmid>/rrd
```

## Container Investigation  
```bash
# List LXC containers on node
pvesh get /nodes/<node-name>/lxc

# Container details
pvesh get /nodes/<node-name>/lxc/<vmid>/status/current
pvesh get /nodes/<node-name>/lxc/<vmid>/config
```

## Storage Investigation
```bash
# Storage configuration
pvesh get /nodes/<node-name>/storage
pvesh get /storage

# Storage content and usage
pvesh get /nodes/<node-name>/storage/<storage-id>/content
pvesh get /nodes/<node-name>/storage/<storage-id>/status

# Direct storage commands
zpool status  # ZFS pools
zfs list     # ZFS datasets
pvs && vgs && lvs  # LVM status
df -h        # Filesystem usage
lsblk        # Block device overview
```

## Network Investigation
```bash
# Network configuration
pvesh get /nodes/<node-name>/network
ip addr show
ip route show

# Bridge information
brctl show
ovs-vsctl show  # If using OVS
```

## Hardware Investigation
```bash
# Hardware overview
lshw -short
lscpu
lsmem
lspci | grep -i vga  # GPU devices
lsusb

# GPU specific (if applicable)
nvidia-smi
lspci | grep -i nvidia

# Temperature and sensors
sensors  # If lm-sensors installed
```

## Service Investigation
```bash
# Proxmox services
systemctl status pve*
systemctl status corosync
systemctl status pvedaemon
systemctl status pveproxy

# Resource monitoring
top
htop  # If available
iotop  # If available
```

## Investigation Checklist

### For Service Deployment Planning:
- [ ] Node resources: `pvesh get /nodes/<node>/status`
- [ ] Available storage: `pvesh get /nodes/<node>/storage`
- [ ] Network configuration: `pvesh get /nodes/<node>/network`
- [ ] GPU availability: `nvidia-smi` or `lspci | grep -i vga`

### For VM/Container Troubleshooting:
- [ ] VM/Container status: `pvesh get /nodes/<node>/qemu` or `/lxc`
- [ ] Resource allocation: Check VM/container config
- [ ] Storage access: Verify storage mount points
- [ ] Network connectivity: Check bridge configuration

### For Performance Issues:
- [ ] Resource usage: `top`, `df -h`, `free -h`
- [ ] Storage performance: `iostat`, `iotop`
- [ ] Network performance: `iftop`, `ss -tuln`

## Safety Notes
- All `pvesh get` commands are read-only
- Hardware detection commands are safe
- Avoid `pvesh set` or `pvesh create` during investigation
- Use `systemctl status` not `systemctl restart` during investigation