# Storage Architecture Investigation Runbook

## Overview

This runbook documents the complete command sequence used to trace the homelab storage architecture from Kubernetes persistent volumes down to the underlying ZFS pools. Use this guide for future storage troubleshooting and architecture analysis.

## Prerequisites

- SSH access to bastion host (192.168.4.122)
- Kubeconfig access to Kubernetes cluster
- Root access to Proxmox nodes
- Basic understanding of ZFS, Kubernetes storage, and Proxmox

## Investigation Workflow

### Phase 1: Kubernetes Storage Discovery

#### 1.1 Identify Problem Workloads
```bash
# Check pod status for storage-related issues
kubectl get pods -A | grep -E "(Pending|Error|CrashLoopBackOff)"

# Look for PVC binding issues
kubectl get pvc -A
kubectl describe pvc netdata-parent-database -n default
```

#### 1.2 Analyze Persistent Volumes
```bash
# List all persistent volumes and their backing storage
kubectl get pv -o wide

# Examine specific PV configuration
kubectl describe pv prometheus-2tb-pv

# Check storage classes
kubectl get storageclass
kubectl describe storageclass prometheus-2tb-storage
```

#### 1.3 Trace Volume Mounts
```bash
# Find pods using specific volumes
kubectl get pods -o=jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.volumes[*].persistentVolumeClaim.claimName}{"\n"}{end}' | grep -v "<none>"

# Examine pod volume mounts
kubectl describe pod prometheus-kube-prometheus-prometheus-0 -n monitoring
```

### Phase 2: Node-Level Investigation

#### 2.1 Connect to Target Node
```bash
# Use bastion host to connect to nodes
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@192.168.4.122

# From bastion, connect to specific node
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ubuntu@k3s-vm-still-fawn
```

#### 2.2 Examine Mount Points
```bash
# Check all mounted filesystems
df -h

# Look for specific mount points
mount | grep -E "(smb_data|rancher|prometheus)"

# Examine filesystem types and options
cat /proc/mounts | grep -E "(ext4|zfs)"
```

#### 2.3 Analyze Directory Structure
```bash
# Navigate to storage mount points
ls -la /mnt/smb_data/
ls -la /mnt/smb_data/prometheus/

# Check prometheus database structure
ls -la /mnt/smb_data/prometheus/prometheus-db/
```

#### 2.4 Identify Block Devices
```bash
# List all block devices
lsblk

# Show detailed disk information
fdisk -l

# Check disk usage
du -sh /mnt/smb_data/*
```

### Phase 3: Proxmox Virtualization Layer

#### 3.1 VM Configuration Analysis
```bash
# From bastion host (192.168.4.122), check VM config
qm config 108

# List all VMs on node
qm list

# Show VM disk allocation
qm config 108 | grep -E "(scsi|disk)"
```

#### 3.2 Storage Backend Investigation
```bash
# Check Proxmox storage configuration
pvesm status

# List storage pools
pvesm list local-20TB-zfs
pvesm list local-2TB-zfs

# Show storage pool details
pvesm status -storage local-20TB-zfs
```

### Phase 4: ZFS Layer Investigation

#### 4.1 Pool Status and Health
```bash
# Check all ZFS pools
zpool list

# Detailed pool status
zpool status local-20TB-zfs

# Pool history and events
zpool history local-20TB-zfs | tail -20
```

#### 4.2 Dataset and Volume Analysis
```bash
# List all datasets and volumes
zfs list -t all

# Show specific volume details
zfs list local-20TB-zfs/vm-108-disk-0

# Check volume properties
zfs get all local-20TB-zfs/vm-108-disk-0 | grep -E "(volsize|referenced|used|compressratio)"
```

#### 4.3 Space Utilization
```bash
# Pool space utilization
zfs list -o name,used,avail,refer,mountpoint local-20TB-zfs

# Compression and deduplication status
zfs get compression,compressratio,dedup,dedupratio local-20TB-zfs/vm-108-disk-0

# Pool fragmentation status
zpool list -o name,size,alloc,free,frag local-20TB-zfs
```

### Phase 5: Application-Level Verification

#### 5.1 Samba Integration Check
```bash
# Check if Samba is accessing the same storage
kubectl get pods -l app=samba -o wide

# Examine Samba pod volume mounts
kubectl describe pod $(kubectl get pods -l app=samba -o jsonpath='{.items[0].metadata.name}')

# Test SMB share accessibility from node
smbclient -L //localhost -N
```

#### 5.2 Prometheus Data Verification
```bash
# Check Prometheus data directory from within node
ls -la /mnt/smb_data/prometheus/prometheus-db/

# Verify recent data writes
ls -lt /mnt/smb_data/prometheus/prometheus-db/ | head -10

# Check WAL directory for active writes
ls -la /mnt/smb_data/prometheus/prometheus-db/wal/
```

## Command Output Interpretation

### Key Indicators to Look For

#### ZFS Health Indicators
```bash
# Good output examples:
zpool status local-20TB-zfs
# Should show: state: ONLINE, errors: No known data errors

zfs get compressratio local-20TB-zfs/vm-108-disk-0
# Shows compression effectiveness (1.00x = no compression)
```

#### Kubernetes Volume Health
```bash
# Healthy PV output:
kubectl get pv prometheus-2tb-pv
# Status should be: Bound

# PVC binding check:
kubectl get pvc -A
# Status should be: Bound
```

#### Storage Path Verification
```bash
# Verify mount chain:
lsblk
# Look for: sdb -> mounted at /mnt/smb_data

df -h /mnt/smb_data
# Should show proper filesystem type (ext4) and available space
```

## Troubleshooting Commands

### Storage Issues
```bash
# If mounts are missing:
mount /dev/sdb /mnt/smb_data
mount -a

# If ZFS pool is degraded:
zpool status local-20TB-zfs
zpool clear local-20TB-zfs

# If Kubernetes volumes are stuck:
kubectl patch pvc <pvc-name> -p '{"metadata":{"finalizers":null}}'
```

### Performance Issues
```bash
# Check I/O statistics
iostat -x 1

# Monitor ZFS ARC statistics
cat /proc/spl/kstat/zfs/arcstats

# Check for high fragmentation
zpool list -o name,frag
```

## Common Investigation Patterns

### Pattern 1: Pod Won't Start Due to Storage
1. Check pod events: `kubectl describe pod <pod-name>`
2. Verify PVC status: `kubectl get pvc`
3. Check PV availability: `kubectl get pv`
4. Examine node storage: `ssh to node && df -h`
5. Verify mount points: `mount | grep <path>`

### Pattern 2: Storage Performance Issues
1. Check ZFS pool health: `zpool status`
2. Monitor fragmentation: `zpool list -o frag`
3. Examine I/O patterns: `iostat -x`
4. Check compression ratios: `zfs get compressratio`
5. Review ARC hit ratios: `cat /proc/spl/kstat/zfs/arcstats`

### Pattern 3: Space Management
1. Check pool utilization: `zfs list`
2. Identify large consumers: `du -sh /path/*`
3. Review growth patterns: `zfs get referenced`
4. Plan expansion: `zpool list -o size,alloc,free`

## Cross-References

- **Architecture Documentation**: [Storage Architecture](../architecture/storage-architecture.md)
- **Monitoring Setup**: [Prometheus Configuration](../monitoring/prometheus-setup.md)
- **ZFS Management**: [ZFS Administration Guide](../infrastructure/zfs-management.md)

## Maintenance Schedule

- **Daily**: Monitor pool health with `zpool status`
- **Weekly**: Check space utilization with `zfs list`
- **Monthly**: Review compression effectiveness
- **Quarterly**: Analyze growth trends and plan expansion

---

**Last Updated**: 2025-08-14  
**Created During**: Netdata storage migration incident  
**Next Review**: 2025-11-14