# Samsung 1TB USB Drive Usage Report

## Drive Identification
- **Location**: PVE node `fun-bedbug` (fun-bedbug.maas)
- **Device**: `/dev/sdb` 
- **Model**: Samsung Portable SSD T5
- **Serial**: S4B0NS0R508926D
- **Capacity**: 931.5GB (1TB nominal)
- **Connection**: USB 3.0 (Bus 002 Device 003: ID 04e8:61f5)

## Current Usage

### ZFS Pool Configuration
```
Pool: local-1TB-backup
State: ONLINE
Device: ata-Samsung_Portable_SSD_T5_S4B0NS0R508926D
```

### Storage Utilization
- **Total Pool Size**: ~900GB
- **Used Space**: 157GB
- **Available Space**: 742GB
- **Usage**: ~17% utilized

### Current Data
The drive contains:
1. **subvol-113-disk-0**: 157GB used (200GB allocated)
   - **LXC 113**: Frigate NVR container 
   - **Mount Point**: `/media` (media storage for camera recordings)
   - **Purpose**: Video recordings and Frigate data storage
   - **Status**: Running

2. **subvol-114-disk-0**: 595MB used (900GB allocated) 
   - **LXC 114**: Duplicati backup container
   - **Root Filesystem**: Primary storage for Duplicati
   - **Purpose**: Backup management and storage
   - **Status**: Stopped

### Proxmox Storage Configuration
```
Storage ID: local-1TB-backup
Type: ZFS Pool
Content Types: rootdir, images
Mount Point: /local-1TB-backup
Node Assignment: fun-bedbug only
```

## Health Status
- **ZFS Pool**: ONLINE, no errors
- **Last Scrub**: August 10, 2025 (completed successfully)
- **Scrub Duration**: 1h 29m 31s
- **Errors**: None detected

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    fun-bedbug.maas                          │
│                  (PVE Node - AMD)                           │
│                                                             │
│  ┌─────────────────┐    USB 3.0     ┌─────────────────────┐ │
│  │   Internal SSD  │◄──────────────►│  Samsung T5 1TB     │ │
│  │   119GB Boot    │                │  /dev/sdb           │ │
│  │   /dev/sda      │                │  931.5GB            │ │
│  └─────────────────┘                └─────────────────────┘ │
│                                               │             │
│                                               ▼             │
│                                     ┌─────────────────────┐ │
│                                     │   ZFS Pool          │ │
│                                     │ local-1TB-backup    │ │
│                                     │                     │ │
│                                     │ ┌─────────────────┐ │ │
│                                     │ │ subvol-113-disk │ │ │
│                                     │ │     157GB       │ │ │
│                                     │ │ Frigate NVR     │ │ │
│                                     │ │ (/media mount)  │ │ │
│                                     │ └─────────────────┘ │ │
│                                     │                     │ │
│                                     │ ┌─────────────────┐ │ │
│                                     │ │ subvol-114-disk │ │ │
│                                     │ │     595MB       │ │ │
│                                     │ │ Duplicati Backup│ │ │
│                                     │ │ (rootfs)        │ │ │
│                                     │ └─────────────────┘ │ │
│                                     │                     │ │
│                                     │ Free: 742GB         │ │
│                                     └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

Storage Flow:
USB T5 → ZFS Pool → VM/Container Disks → Backup Storage
```

## Use Case
This Samsung T5 SSD serves as backup storage for VM/container disks on the fun-bedbug node, providing fast USB 3.0 attached storage for the homelab infrastructure.