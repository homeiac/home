# Crucible Proxmox NBD Integration Guide

**Complete step-by-step guide for integrating Oxide Crucible distributed storage with Proxmox via NBD (Network Block Device)**

## Prerequisites

- **Crucible Storage Sleds**: MA90 mini PCs running Ubuntu 24.04 with Crucible downstairs processes
- **Proxmox Host**: Compute host with Crucible binaries compiled (still-fawn)
- **Network**: 2.5GbE connectivity between compute and storage hosts

## Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Proxmox Host   │    │   NBD Upstairs   │    │  MA90 Storage   │
│  (still-fawn)   │    │   (still-fawn)   │    │ (proper-raptor) │
│                 │    │                  │    │                 │
│  ┌───────────┐  │    │  ┌─────────────┐ │    │ ┌─────────────┐ │
│  │    VM     │  │    │  │ crucible-   │ │    │ │ crucible-   │ │
│  │           │  │    │  │ nbd-server  │ │◄──►│ │ downstairs  │ │
│  │  /dev/nbd0│◄─┼────┼─►│             │ │    │ │   :3810     │ │
│  └───────────┘  │    │  │ :10809      │ │    │ │   :3811     │ │
└─────────────────┘    │  └─────────────┘ │    │ │   :3812     │ │
                       └──────────────────┘    │ └─────────────┘ │
                                               └─────────────────┘
```

## Step 1: Verify Crucible Downstairs Status

Check that all 3 Crucible downstairs processes are running on the MA90 storage sled:

```bash
# SSH to MA90 storage sled
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas

# Verify downstairs processes
ps aux | grep crucible-downstairs
# Expected: 3 processes on ports 3810, 3811, 3812

# Check current IP address
ip addr show enp1s0
# Note the IP address (e.g., 192.168.4.121)
```

## Step 2: Create Crucible Volume for NBD Export

Initialize a test volume with the next generation number:

```bash
# SSH to Proxmox host (where Crucible binaries are compiled)
ssh root@still-fawn.maas

# Initialize volume with appropriate generation (check previous tests)
/tmp/crucible/target/release/crutest generic \
  --target 192.168.4.121:3810 \
  --target 192.168.4.121:3811 \
  --target 192.168.4.121:3812 \
  --gen 4 \
  --count 1 \
  --quiet

# Wait for successful completion, then kill the process
# (crutest hangs after completion - this is normal behavior)
```

## Step 3: Start Crucible NBD Server

Start the NBD server to export the Crucible volume:

```bash
# Start NBD server in background with correct generation
nohup /tmp/crucible/target/release/crucible-nbd-server \
  --target 192.168.4.121:3810 \
  --target 192.168.4.121:3811 \
  --target 192.168.4.121:3812 \
  --gen 4 \
  > /tmp/nbd-server-gen4.log 2>&1 &

# Wait 5 seconds for startup
sleep 5

# Verify NBD server started successfully
tail -20 /tmp/nbd-server-gen4.log
# Look for: "NBD advertised size as 524288000 bytes"
# Look for: "Set Active after no reconciliation"
```

**Expected Output (Success Indicators):**
- All 3 region UUIDs connected: `11111111-1111-1111-1111-111111111111`, `22222222-2222-2222-2222-222222222222`, `33333333-3333-3333-3333-333333333333`
- All replicas active: "Transition from WaitQuorum to Active"
- NBD ready: "NBD advertised size as 524288000 bytes"

## Step 4: Configure NBD Client on Proxmox

Load the NBD kernel module and install client tools:

```bash
# Load NBD kernel module
modprobe nbd

# Verify module loaded
lsmod | grep nbd
# Expected: nbd    65536  0

# Install NBD client tools
apt update && apt install -y nbd-client

# Verify NBD devices available
ls -la /dev/nbd*
# Expected: /dev/nbd0, /dev/nbd1, etc.
```

## Step 5: Connect NBD Client to Crucible Storage

Connect the NBD client to the Crucible NBD server:

```bash
# Connect NBD client to server (default port 10809)
nbd-client 127.0.0.1 10809 /dev/nbd0

# Expected output:
# Warning: the oldstyle protocol is no longer supported.
# This method now uses the newstyle protocol with a default export
# Negotiation: ..size = 500MB
# Connected /dev/nbd0

# Verify device is available
lsblk | grep nbd0
# Expected: nbd0       43:0    0   500M  0 disk

# Check device details
fdisk -l /dev/nbd0
# Expected: Disk /dev/nbd0: 500 MiB, 524288000 bytes, 1024000 sectors
```

## Step 6: Test NBD Device I/O Operations

Verify read/write operations work correctly:

```bash
# Test write operation (1MB)
dd if=/dev/zero of=/dev/nbd0 bs=1M count=1
# Expected: ~6+ MB/s write speed

# Test read operation (1MB)
dd if=/dev/nbd0 of=/dev/null bs=1M count=1
# Expected: ~11+ MB/s read speed
```

## Step 7: Create Filesystem for Proxmox Storage

Create a filesystem on the NBD device:

```bash
# Create ext4 filesystem
mkfs.ext4 /dev/nbd0

# Create mount point
mkdir -p /mnt/crucible-storage

# Mount the filesystem
mount /dev/nbd0 /mnt/crucible-storage

# Verify mount
df -h /mnt/crucible-storage
# Expected: ~500M filesystem mounted
```

## Step 8: Configure Proxmox Storage

Add the Crucible storage to Proxmox configuration:

```bash
# Create Proxmox storage directory configuration
# Option 1: Via CLI
pvesm add dir crucible-storage --path /mnt/crucible-storage --content images,vztmpl,iso

# Option 2: Via Proxmox Web UI
# Navigate to: Datacenter → Storage → Add → Directory
# ID: crucible-storage
# Directory: /mnt/crucible-storage
# Content: Disk image, Container template, ISO image

# Verify storage is configured
pvesm status
# Should show crucible-storage as available
```

## Step 9: Test VM Creation with Crucible Storage

Create a test VM using the Crucible storage:

```bash
# Create VM via CLI (example)
qm create 999 \
  --name "crucible-test-vm" \
  --memory 1024 \
  --cores 1 \
  --net0 virtio,bridge=vmbr0 \
  --scsi0 crucible-storage:10,format=qcow2

# Or via Proxmox Web UI:
# Navigate to: Create VM
# General: VM ID, Name
# OS: Select ISO from crucible-storage
# Hard Disk: Storage = crucible-storage, Disk size = 10 GB
```

## Troubleshooting

### NBD Server Connection Issues

```bash
# Check NBD server process
ps aux | grep crucible-nbd-server

# Check NBD server logs
tail -f /tmp/nbd-server-gen4.log

# Verify all downstairs are responsive
echo "" | nc -w 3 192.168.4.121 3810 && echo "3810 OK"
echo "" | nc -w 3 192.168.4.121 3811 && echo "3811 OK" 
echo "" | nc -w 3 192.168.4.121 3812 && echo "3812 OK"
```

### NBD Client Issues

```bash
# Disconnect NBD device
nbd-client -d /dev/nbd0

# Reconnect with verbose output
nbd-client -v 127.0.0.1 10809 /dev/nbd0

# Check kernel messages
dmesg | tail -20
```

### Storage Performance Issues

```bash
# Test I/O performance
fio --name=crucible-test --rw=randwrite --bs=4k --size=100M --filename=/dev/nbd0

# Monitor Crucible metrics (if available)
curl http://192.168.4.121:7810/metrics
```

## Systemd Service Configuration (Optional)

For persistent operation, create systemd services:

### Crucible NBD Server Service

```bash
# Create service file
cat > /etc/systemd/system/crucible-nbd-server.service << 'EOF'
[Unit]
Description=Crucible NBD Server
After=network.target

[Service]
Type=simple
ExecStart=/tmp/crucible/target/release/crucible-nbd-server \
  --target 192.168.4.121:3810 \
  --target 192.168.4.121:3811 \
  --target 192.168.4.121:3812 \
  --gen 4
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
systemctl enable crucible-nbd-server.service
systemctl start crucible-nbd-server.service
```

### NBD Client Mount Service

```bash
# Create mount service
cat > /etc/systemd/system/crucible-nbd-mount.service << 'EOF'
[Unit]
Description=Mount Crucible NBD Storage
After=crucible-nbd-server.service
Requires=crucible-nbd-server.service

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'nbd-client 127.0.0.1 10809 /dev/nbd0 && mount /dev/nbd0 /mnt/crucible-storage'
ExecStop=/bin/bash -c 'umount /mnt/crucible-storage && nbd-client -d /dev/nbd0'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# Enable service
systemctl enable crucible-nbd-mount.service
```

## Performance Characteristics

**Tested Performance (500MB volume):**
- **Write Speed**: ~6.2 MB/s
- **Read Speed**: ~11.2 MB/s
- **Latency**: Network + storage latency combined
- **Replication**: 3-way synchronous replication across all operations

## Limitations and Considerations

1. **Single NBD Server**: Current setup uses one NBD server per volume
2. **Generation Management**: Must increment generation numbers for new volumes
3. **Failover**: Manual restart required if NBD server fails
4. **Performance**: Network bandwidth limits throughput
5. **Scalability**: Each volume requires dedicated NBD server process

## Next Steps

1. **Multiple Volumes**: Deploy additional MA90 sleds for more storage capacity
2. **Automation**: Create scripts for dynamic volume management
3. **Monitoring**: Implement health checks and alerting
4. **Backup**: Configure snapshot-based backup strategies
5. **Production**: Scale to multiple compute hosts with dedicated storage network

## Validation Commands Summary

```bash
# Complete validation sequence
lsmod | grep nbd                          # NBD module loaded
ps aux | grep crucible-nbd-server         # NBD server running
lsblk | grep nbd0                         # NBD device available
df -h /mnt/crucible-storage               # Filesystem mounted
pvesm status | grep crucible-storage      # Proxmox storage configured
```

This completes the integration of Oxide Crucible distributed storage with Proxmox via NBD, providing fault-tolerant storage for VMs using commodity AMD MA90 hardware.