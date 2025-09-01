#!/usr/bin/env python3
####
#
#  Program: 45-ma90-multi-zfs-layout.sh
#
#  Description:
#  This script creates a custom storage layout for MA90 mini PCs with
#  dedicated ZFS partition for Crucible distributed storage.
#
#  Inputs: MAAS_RESOURCES_FILE (json with hardware details from commissioning)
#  Outputs: Adds 'storage-extra' block to MAAS_RESOURCES_FILE with custom layout
#
#  Layout: EFI(512M) + Root(25G) + ZFS(remaining ~90GB)
#
# --- Start MAAS 1.0 script metadata ---
# name: 45-ma90-multi-zfs-layout-v2
# title: MA90 Multi-ZFS Storage Layout v2
# description: Create EFI + Root + ZFS partition layout for MA90 Crucible storage
# script_type: commissioning
# timeout: 300
# --- End MAAS 1.0 script metadata ---
#
####

import json
import os
import sys

def read_json_file(path):
    """Read and parse JSON file safely"""
    try:
        with open(path) as fd:
            return json.load(fd)
    except OSError as e:
        sys.exit(f"Failed to read {path}: {e}")
    except json.JSONDecodeError as e:
        sys.exit(f"Failed to parse {path}: {e}")

def write_json_file(path, data):
    """Write JSON data to file safely"""
    try:
        with open(path, 'w') as fd:
            json.dump(data, fd, indent=2)
    except OSError as e:
        sys.exit(f"Failed to write {path}: {e}")

# Load hardware resources from MAAS
print("MA90 Multi-ZFS Layout Commissioning Script v2 starting...")

if 'MAAS_RESOURCES_FILE' not in os.environ:
    sys.exit("ERROR: MAAS_RESOURCES_FILE environment variable not set")

resources_file = os.environ['MAAS_RESOURCES_FILE']
print(f"Reading MAAS resources from: {resources_file}")

# Load the hardware data
hardware = read_json_file(resources_file)

# Extract disk information
disks = hardware.get('resources', {}).get('storage', {}).get('disks', [])
if not disks:
    sys.exit("ERROR: No disks found in MAAS resources")

# Find the primary disk (largest disk > 100GB, typically sda on MA90)
primary_disk = None
for disk in disks:
    # Skip virtual/removable drives  
    if 'Virtual' in disk.get("model", "") or disk.get('removable', False):
        continue
    
    # MA90 should have ~128GB M.2 SATA disk
    disk_size_gb = disk.get('size', 0) / (1024 * 1024 * 1024)
    if disk_size_gb > 100 and disk_size_gb < 200:  # MA90 range
        primary_disk = disk
        break

# Fallback to first non-removable disk
if not primary_disk:
    for disk in disks:
        if not disk.get('removable', False):
            primary_disk = disk
            break

if not primary_disk:
    sys.exit("ERROR: No suitable disk found for MA90 storage layout")

disk_id = primary_disk['id']
disk_size = primary_disk['size']
disk_size_gb = disk_size / (1024 * 1024 * 1024)

print(f"Selected disk: {disk_id}")
print(f"Disk size: {disk_size_gb:.1f}GB ({disk_size} bytes)")
print(f"Disk model: {primary_disk.get('model', 'Unknown')}")

# Validate disk size (MA90 should be ~119-128GB)
if disk_size_gb < 100 or disk_size_gb > 150:
    print(f"WARNING: Unexpected disk size {disk_size_gb:.1f}GB for MA90")

# Calculate partition sizes (MAAS uses 1000-based, not 1024-based)
efi_size_bytes = 512 * 1000 * 1000      # 512MB
root_size_bytes = 25 * 1000 * 1000 * 1000  # 25GB
zfs_size_bytes = disk_size - efi_size_bytes - root_size_bytes

# Convert to MAAS size format
efi_size = "512M"
root_size = "25G" 
zfs_size_gb = int(zfs_size_bytes / (1000 * 1000 * 1000))
zfs_size = f"{zfs_size_gb}G"

print(f"Partition plan: EFI({efi_size}) + Root({root_size}) + ZFS({zfs_size})")

# Create storage layout configuration
# NOTE: Removed "fs": "unformatted" - MAAS doesn't recognize this
storage_layout = {
    "layout": {
        disk_id: {
            "type": "disk",
            "ptable": "gpt",
            "boot": True,
            "partitions": [
                {
                    "name": f"{disk_id}1",
                    "fs": "fat32",
                    "size": efi_size,
                    "bootable": True
                },
                {
                    "name": f"{disk_id}2", 
                    "fs": "ext4",
                    "size": root_size
                },
                {
                    "name": f"{disk_id}3",
                    "size": zfs_size
                    # No "fs" specified = unformatted partition
                }
            ]
        }
    },
    "mounts": {
        "/": {
            "device": f"{disk_id}2",
            "options": "noatime,errors=remount-ro"
        },
        "/boot/efi": {
            "device": f"{disk_id}1"
        }
    }
}

# Add storage-extra to hardware resources (this is the key!)
hardware["storage-extra"] = storage_layout

# Write back to MAAS_RESOURCES_FILE
print(f"Adding custom storage layout to {resources_file}")
write_json_file(resources_file, hardware)

print("SUCCESS: MA90 Multi-ZFS storage layout configuration added successfully")
print(f"Layout: EFI({efi_size}) + Root({root_size}) + ZFS({zfs_size} for Crucible)")

# Log the configuration for debugging
print("\nGenerated storage configuration:")
print(json.dumps(storage_layout, indent=2))

print(f"\nConfiguration written to: {resources_file}")
print("MAAS will use this layout during deployment")

sys.exit(0)