# Homelab Storage Architecture

## Overview

This document describes the complete storage architecture of the homelab infrastructure, focusing on the ZFS-backed storage solution for Kubernetes workloads, particularly Prometheus time-series data storage.

## Architecture Summary

The homelab uses a multi-layered storage approach combining Proxmox ZFS pools, Kubernetes persistent volumes, and Samba file sharing to provide scalable, efficient storage for monitoring and data workloads.

## High-Level Architecture

```mermaid
graph TB
    subgraph "Kubernetes Layer"
        A[Prometheus Pod] --> B[prometheus-2tb-pv]
        C[Samba Pod] --> D[HostPath Volume]
        E[Other Pods] --> F[local-path Storage]
    end
    
    subgraph "VM Layer - k3s-vm-still-fawn"
        B --> G[mnt/smb_data/prometheus]
        D --> H[mnt/smb_data]
        F --> I[var/lib/rancher]
        
        G --> J[dev/sdb - 20TB]
        H --> J
        I --> K[dev/sda - 400GB]
    end
    
    subgraph "Proxmox ZFS Layer - still-fawn"
        J --> L[local-20TB-zfs/vm-108-disk-0]
        K --> M[local-2TB-zfs/vm-108-disk-0]
        
        L --> N[local-20TB-zfs Pool - 21.8TB]
        M --> O[local-2TB-zfs Pool]
    end
    
    subgraph "Client Access"
        P[SMB Client] --> Q[homelab/secure]
        Q --> H
    end
```

## Detailed Storage Flow

### Prometheus Storage Path

```mermaid
flowchart LR
    A[Prometheus Writes] --> B[LocalVolume PV]
    B --> C[mnt/smb_data/prometheus]
    C --> D[ext4 filesystem]
    D --> E[dev/sdb]
    E --> F[ZFS Volume]
    F --> G[local-20TB-zfs Pool]
    G --> H[Physical HDDs]
```

### Storage Classes and Provisioning

```mermaid
graph TB
    subgraph "Storage Classes"
        A[prometheus-2tb-storage]
        B[local-path default]
        C[longhorn - REMOVED]
    end
    
    subgraph "Provisioning Methods"
        A --> D[LocalVolume Static]
        B --> E[local-path-provisioner Dynamic]
        C --> F[Longhorn CSI - DELETED]
    end
    
    subgraph "Target Storage"
        D --> G[mnt/smb_data/prometheus]
        E --> H[var/lib/rancher/k3s/...]
        F --> I[Removed after migration]
    end
```

## ZFS Configuration Details

### Pool Configuration

| Property | Value | Description |
|----------|-------|-------------|
| Pool Name | `local-20TB-zfs` | Primary storage pool |
| Total Size | 21.8TB | Raw pool capacity |
| Used Space | 1.87TB | Actually allocated |
| Free Space | 19.9TB | Available for expansion |
| Fragmentation | 0% | Optimal performance |
| Health | ONLINE | Pool status |

### Volume Configuration

| Property | Value | Description |
|----------|-------|-------------|
| Dataset | `local-20TB-zfs/vm-108-disk-0` | VM disk dataset |
| Volume Size | 19.5TB | Allocated to VM |
| Referenced | 1.87TB | Actually used data |
| Block Size | 16K | ZFS volume block size |
| Compression | OFF | Currently disabled |
| Compression Ratio | 1.00x | No compression benefit yet |

### Thin Provisioning Status

```mermaid
pie title ZFS Space Utilization
    "Used Space" : 1.87
    "Available Space" : 19.93
```

**Key Thin Provisioning Features:**
- **Sparse**: Enabled in Proxmox (`sparse 1`)
- **Reservation**: None (thin provisioning active)
- **Reference Reservation**: 19.8TB (space protection)
- **Expandable**: Online expansion supported

## Kubernetes Storage Integration

### Persistent Volume Configuration

```yaml
# prometheus-2tb-pv configuration
apiVersion: v1
kind: PersistentVolume
metadata:
  name: prometheus-2tb-pv
spec:
  capacity:
    storage: 1000Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: prometheus-2tb-storage
  local:
    path: /mnt/smb_data/prometheus
  nodeAffinity:
    required:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/hostname
          operator: In
          values:
          - k3s-vm-still-fawn
```

### Storage Class Definitions

```yaml
# prometheus-2tb-storage StorageClass
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: prometheus-2tb-storage
provisioner: rancher.io/local-path
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
```

## VM Disk Configuration

### Proxmox VM 108 Disks

```mermaid
graph LR
    subgraph "VM 108 - k3s-vm-still-fawn"
        A[scsi0: Main OS Disk] --> B[local-2TB-zfs:vm-108-disk-0]
        C[scsi1: Storage Disk] --> D[local-20TB-zfs:vm-108-disk-0]
    end
    
    subgraph "Guest OS View"
        B --> E[dev/sda - 400GB]
        D --> F[dev/sdb - 20TB]
    end
    
    subgraph "Mount Points"
        E --> G[ root filesystem]
        F --> H[mnt/smb_data ext4]
    end
```

### VM Configuration Details

```ini
# Relevant VM config from qm config 108
scsi0: local-2TB-zfs:vm-108-disk-0,size=400G
scsi1: local-20TB-zfs:vm-108-disk-0,backup=0,replicate=0,size=20000G
```

## Samba Integration

### Directory Structure

```
/mnt/smb_data/
├── prometheus/                    # Active Prometheus TSDB
│   └── prometheus-db/
│       ├── 01K2JTKDVXXTTHF23219RCSMEB/  # Data blocks
│       └── wal/                   # Write-ahead logs
├── elements_backup/               # Backup data
├── elements_data_backup/
├── opencloud/
└── guest-data.txt
```

### Samba Pod Configuration

```mermaid
graph TB
    A[Samba Pod] --> B[HostPath Volume]
    B --> C[mnt/smb_data]
    
    subgraph "SMB Shares"
        C --> D[secure share]
        D --> E[prometheus/]
        D --> F[backups/]
        D --> G[other data/]
    end
    
    subgraph "Client Access"
        H[SMB Client] --> I[homelab/secure]
        I --> D
    end
```

## Performance Characteristics

### Storage Tiers

| Storage Tier | Technology | Use Case | Performance |
|--------------|------------|----------|-------------|
| SSD (local-2TB-zfs) | ZFS on SSD | OS, hot data | High IOPS |
| HDD (local-20TB-zfs) | ZFS on HDD | Bulk storage | High throughput |

### Prometheus Storage Patterns

```mermaid
timeline
    title Prometheus Write Patterns
    
    section Real-time Writes
        Every 15s    : WAL files updated
        Every 2h     : New chunk files created
        
    section Maintenance
        Daily        : Old chunks compressed
        Weekly       : Block compaction
        
    section Growth
        Monthly      : ~100GB growth observed
        Yearly       : ~1.2TB projected
```

## Optimization Opportunities

### Current State
- **Compression**: OFF (1.00x ratio)
- **Deduplication**: OFF (1.00x ratio)
- **Snapshots**: None configured

### Recommendations

1. **Enable Compression**
   ```bash
   zfs set compression=lz4 local-20TB-zfs/vm-108-disk-0
   ```
   - Expected savings: 30-50% for time-series data
   - No performance impact with lz4

2. **Configure Snapshots**
   ```bash
   # Daily snapshots for backup
   zfs snapshot local-20TB-zfs/vm-108-disk-0@daily-$(date +%Y%m%d)
   ```

3. **Monitor Growth**
   ```bash
   # Track compression effectiveness
   zfs get compressratio local-20TB-zfs/vm-108-disk-0
   ```

## Expansion Procedures

### Online Disk Expansion

```mermaid
sequenceDiagram
    participant Admin
    participant Proxmox
    participant ZFS
    participant VM
    participant K8s
    
    Admin->>Proxmox: Resize VM disk
    Proxmox->>ZFS: Expand ZFS volume
    ZFS->>VM: Present larger disk
    VM->>VM: Resize ext4 filesystem
    K8s->>K8s: Automatic PV expansion
```

### Steps for Expansion

1. **Expand ZFS volume** (if needed)
   ```bash
   zfs set volsize=25T local-20TB-zfs/vm-108-disk-0
   ```

2. **Resize VM disk in Proxmox**
   ```bash
   qm resize 108 scsi1 +5000G
   ```

3. **Expand filesystem in VM**
   ```bash
   resize2fs /dev/sdb
   ```

## Monitoring and Maintenance

### Key Metrics to Monitor

| Metric | Command | Threshold |
|--------|---------|-----------|
| Pool Usage | `zpool list local-20TB-zfs` | < 80% |
| Compression Ratio | `zfs get compressratio` | > 1.20x |
| Fragmentation | `zpool list` | < 30% |
| Health Status | `zpool status` | ONLINE |

### Regular Maintenance Tasks

- **Weekly**: Check ZFS pool health
- **Monthly**: Review storage growth trends
- **Quarterly**: Evaluate compression settings
- **Annually**: Plan capacity expansion

## Troubleshooting

### Common Issues

1. **Prometheus Pod Stuck**
   - Check ZFS pool health
   - Verify mount points in VM
   - Check disk space usage

2. **Performance Issues**
   - Monitor ZFS ARC hit ratio
   - Check for fragmentation
   - Review I/O patterns

3. **Space Issues**
   - Enable compression
   - Clean old snapshots
   - Expand underlying pool

### Emergency Procedures

1. **Pool Degraded**
   ```bash
   zpool status local-20TB-zfs
   zpool clear local-20TB-zfs
   ```

2. **Full Filesystem**
   ```bash
   # Emergency cleanup
   find /mnt/smb_data -name "*.tmp" -delete
   ```

## Related Documentation

- [Prometheus Configuration](../monitoring/prometheus-setup.md)
- [ZFS Administration Guide](../infrastructure/zfs-management.md)
- [Kubernetes Storage Classes](../k8s/storage-classes.md)
- [Backup Procedures](../backup/storage-backup.md)

---

**Last Updated**: 2025-08-14  
**Maintainer**: Homelab Infrastructure Team  
**Review Cycle**: Quarterly
