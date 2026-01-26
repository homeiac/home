# Crucible Storage Deployment Runbook

**Date**: January 25, 2026
**Status**: WORKING - deployed to all 4 Proxmox hosts
**Architecture**: Simple ext4-on-NBD with Crucible quorum (single sled)

## ⚠️ IMPORTANT: This is NOT True Replication

**Current setup has a SINGLE POINT OF FAILURE.**

All 3 downstairs processes run on **one MA90 sled** (proper-raptor) with **one SSD**. The "3-way" is only for Crucible's quorum protocol to function - it provides **zero fault tolerance**.

```
CURRENT (Budget Testing Mode):
┌─────────────────────────────────────────┐
│  proper-raptor (SINGLE SSD)             │
│                                         │
│  downstairs :3820 ─┐                    │
│  downstairs :3821 ─┼─► SAME DISK        │
│  downstairs :3822 ─┘                    │
│                                         │
│  If this sled dies → ALL DATA LOST      │
└─────────────────────────────────────────┘

TRUE 3-WAY REPLICATION (Requires 2 more MA90s, ~$60):
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ MA90 Sled #1 │  │ MA90 Sled #2 │  │ MA90 Sled #3 │
│ :3820        │  │ :3820        │  │ :3820        │
│ SSD #1       │  │ SSD #2       │  │ SSD #3       │
└──────────────┘  └──────────────┘  └──────────────┘
        │                │                │
        └────────────────┼────────────────┘
                         │
              Any 1 sled can fail
              Data survives
```

**Bottom line**: Use this for testing/learning Crucible, NOT for critical data.

---

## Overview

Each Proxmox host gets `/mnt/crucible-storage` (12GB ext4) backed by Crucible on proper-raptor.

## Network Architecture

The storage network uses a dedicated 2.5GbE switch with 10GbE SFP+ uplink to the main network:

```
                              ┌─────────────────────────────┐
                              │      Main Network           │
                              │    192.168.4.0/24           │
                              │   (existing infrastructure) │
                              └─────────────┬───────────────┘
                                            │
                                            │ 10GbE SFP+
                                            │
                              ┌─────────────┴───────────────┐
                              │     2.5GbE Managed Switch   │
                              │     (8-port + 10G uplink)   │
                              └─┬─────────┬─────────┬─────┬─┘
                                │         │         │     │
                              2.5GbE    2.5GbE   2.5GbE  2.5GbE
                                │         │         │     │
        ┌───────────────────────┘         │         │     └─────────────────────┐
        │                                 │         │                           │
        ▼                                 ▼         ▼                           ▼
┌───────────────┐               ┌───────────────┐  ┌───────────────┐   ┌───────────────┐
│  still-fawn   │               │ pumped-piglet │  │ chief-horse   │   │ proper-raptor │
│ 192.168.4.17  │               │ 192.168.4.175 │  │ 192.168.4.19  │   │ 192.168.4.189 │
│               │               │               │  │               │   │               │
│ USB 2.5GbE    │               │ USB 2.5GbE    │  │ USB 2.5GbE    │   │ USB 2.5GbE    │
│ (RTL8156)     │               │ (RTL8156)     │  │ (RTL8156)     │   │ (RTL8156)     │
│               │               │               │  │               │   │               │
│ Proxmox Host  │               │ Proxmox Host  │  │ Proxmox Host  │   │ MA90 Sled     │
│ (consumer)    │               │ (consumer)    │  │ (consumer)    │   │ (storage)     │
└───────────────┘               └───────────────┘  └───────────────┘   └───────────────┘
```

**Hardware**:
- **Switch**: 8-port 2.5GbE managed switch with 10GbE SFP+ uplink (~$60)
- **USB NICs**: RTL8156-based USB 3.0 to 2.5GbE adapters (~$15 each)
- **Storage Sled**: ATOPNUC MA90 AMD mini PC (~$30 used)

## Bridge Configuration (proper-raptor)

The MA90 uses a bridge on the USB NIC for reliable boot:

```bash
# /etc/network/interfaces on proper-raptor

auto lo
iface lo inet loopback

# Built-in 1GbE - unused (no cable)
iface enp1s0 inet manual

# USB 2.5GbE adapter - bridge member
auto enx00e04ca81110
iface enx00e04ca81110 inet manual

# Bridge on USB adapter
auto br0
iface br0 inet static
    address 192.168.4.189/24
    gateway 192.168.4.1
    bridge-ports enx00e04ca81110
    bridge-stp off
    bridge-fd 0
    dns-nameservers 192.168.4.53
```

**Why a bridge?** USB NICs can be flaky at boot. The bridge waits for the interface and matches Proxmox host patterns.

## Logical Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────────────────┐
│   Proxmox Host  │     │  NBD Server     │     │  proper-raptor (storage)    │
│                 │     │  (localhost)    │     │  192.168.4.189              │
│                 │     │                 │     │                             │
│ /mnt/crucible-  │     │ crucible-nbd-   │     │ ┌─────────────────────────┐ │
│ storage (ext4)  │────▶│ server          │────▶│ │ downstairs :3820        │ │
│                 │     │ :10809          │     │ │ downstairs :3821        │ │
│ /dev/nbd0       │     │                 │     │ │ downstairs :3822        │ │
└─────────────────┘     └─────────────────┘     │ └─────────────────────────┘ │
                                                │    (quorum only, 1 disk!)   │
                                                └─────────────────────────────┘
```

## Port Allocation

| Host | Downstairs Ports | NBD Port | Device |
|------|------------------|----------|--------|
| pve | 3820, 3821, 3822 | 10809 | /dev/nbd0 |
| still-fawn | 3830, 3831, 3832 | 10809 | /dev/nbd0 |
| pumped-piglet | 3840, 3841, 3842 | 10809 | /dev/nbd0 |
| chief-horse | 3850, 3851, 3852 | 10809 | /dev/nbd0 |

## Prerequisites

1. **proper-raptor online** at 192.168.4.189 with downstairs processes running
2. **K3s cluster** for building the patched binary (or pre-built binary)
3. **SSH access** to all Proxmox hosts

---

## Step 1: Verify Downstairs on proper-raptor

```bash
ssh ubuntu@192.168.4.189 "ss -tlnp | grep crucible"
```

Expected output (ports 3820-3852 listening):
```
LISTEN 0 1024 0.0.0.0:3850 0.0.0.0:* users:(("crucible-downst"...))
LISTEN 0 1024 0.0.0.0:3840 0.0.0.0:* users:(("crucible-downst"...))
LISTEN 0 1024 0.0.0.0:3830 0.0.0.0:* users:(("crucible-downst"...))
LISTEN 0 1024 0.0.0.0:3820 0.0.0.0:* users:(("crucible-downst"...))
```

If not running, see "Appendix A: Creating Downstairs Volumes".

---

## Step 2: Build Patched crucible-nbd-server

The upstream binary hardcodes the listen address. We patch it to support `--address` flag (optional but useful for debugging).

### Option A: Build via K8s Job (Recommended)

```bash
# Apply the build job
export KUBECONFIG=~/kubeconfig
kubectl apply -f scripts/crucible/k8s/crucible-build-job.yaml

# Watch progress
kubectl logs -n crucible-build -f job/crucible-nbd-build

# Wait for completion (~5 minutes)
kubectl get pods -n crucible-build
# Should show: Completed

# Extract binary
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: get-crucible-binary
  namespace: crucible-build
spec:
  nodeSelector:
    kubernetes.io/hostname: k3s-vm-pumped-piglet-gpu
  containers:
  - name: helper
    image: busybox
    command: ["sleep", "300"]
    volumeMounts:
    - name: output
      mountPath: /output
  volumes:
  - name: output
    hostPath:
      path: /tmp/crucible-build
  restartPolicy: Never
EOF

sleep 10
kubectl exec -n crucible-build get-crucible-binary -- cat /output/crucible-nbd-server > /tmp/crucible-nbd-server
chmod +x /tmp/crucible-nbd-server

# Verify
file /tmp/crucible-nbd-server
# Should show: ELF 64-bit LSB pie executable, x86-64

# Cleanup
kubectl delete ns crucible-build
```

### Option B: Use Existing Binary

If binary already exists on proper-raptor:
```bash
scp ubuntu@192.168.4.189:/home/ubuntu/crucible-nbd-server /tmp/crucible-nbd-server
```

---

## Step 3: Copy Binary to proper-raptor

```bash
scp /tmp/crucible-nbd-server ubuntu@192.168.4.189:/home/ubuntu/crucible-nbd-server
ssh ubuntu@192.168.4.189 "chmod +x /home/ubuntu/crucible-nbd-server"

# Verify
ssh ubuntu@192.168.4.189 "/home/ubuntu/crucible-nbd-server --help | head -10"
```

---

## Step 4: Deploy to All Proxmox Hosts

```bash
# Use the existing deployment script
/opt/homebrew/bin/bash scripts/crucible/attach-volumes-to-proxmox.sh
```

This script:
1. Copies binary from proper-raptor to each host
2. Installs nbd-client package
3. Creates systemd services with timestamp-based generation
4. Starts and enables the services
5. Connects /dev/nbd0

---

## Step 5: Format and Mount (First Time Only)

```bash
for host in pve still-fawn.maas pumped-piglet.maas chief-horse.maas; do
    echo "=== $host ==="
    ssh root@$host '
        set -e

        # Format if needed
        if ! blkid /dev/nbd0 | grep -q ext4; then
            echo "Formatting /dev/nbd0..."
            mkfs.ext4 -q /dev/nbd0
        fi

        # Create mount point
        mkdir -p /mnt/crucible-storage

        # Mount
        mount /dev/nbd0 /mnt/crucible-storage 2>/dev/null || true

        # Create systemd mount unit for persistence
        cat > /etc/systemd/system/mnt-crucible\\x2dstorage.mount << EOF
[Unit]
Description=Crucible Storage Mount
After=crucible-nbd-connect.service
Requires=crucible-nbd-connect.service

[Mount]
What=/dev/nbd0
Where=/mnt/crucible-storage
Type=ext4
Options=defaults,noatime

[Install]
WantedBy=multi-user.target
EOF

        systemctl daemon-reload
        systemctl enable mnt-crucible\\x2dstorage.mount

        # Ensure mount is active
        if ! mountpoint -q /mnt/crucible-storage; then
            systemctl start mnt-crucible\\x2dstorage.mount
        fi

        # Verify
        df -h /mnt/crucible-storage | tail -1
    '
done
```

---

## Step 6: Add to Proxmox Storage

```bash
for host in pve still-fawn.maas pumped-piglet.maas chief-horse.maas; do
    echo "=== $host ==="
    ssh root@$host '
        if pvesm status | grep -q crucible-storage; then
            echo "Already configured"
        else
            pvesm add dir crucible-storage --path /mnt/crucible-storage --content images,vztmpl,iso,backup
            echo "Added crucible-storage"
        fi
        pvesm status | grep crucible-storage
    '
done
```

---

## Verification

### Check All Hosts

```bash
for host in pve still-fawn.maas pumped-piglet.maas chief-horse.maas; do
    echo "=== $host ==="
    ssh root@$host '
        echo "NBD device:"
        lsblk /dev/nbd0 2>/dev/null || echo "NOT CONNECTED"
        echo ""
        echo "Mount:"
        df -h /mnt/crucible-storage 2>/dev/null | tail -1 || echo "NOT MOUNTED"
        echo ""
        echo "Proxmox storage:"
        pvesm status | grep crucible-storage || echo "NOT CONFIGURED"
        echo ""
    '
done
```

### Check Downstairs on proper-raptor

```bash
ssh ubuntu@192.168.4.189 "systemctl status crucible-vm-* --no-pager | grep -E '(●|Active:)'"
```

---

## Systemd Services (Per Host)

### crucible-nbd.service
Starts the NBD server connecting to proper-raptor's downstairs.

```ini
[Unit]
Description=Crucible NBD Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/crucible-nbd-wrapper.sh --target 192.168.4.189:38X0 --target 192.168.4.189:38X1 --target 192.168.4.189:38X2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### crucible-nbd-connect.service
Connects nbd-client to the local NBD server.

```ini
[Unit]
Description=Connect NBD client to Crucible
After=crucible-nbd.service
Requires=crucible-nbd.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/sleep 3
ExecStart=/usr/sbin/nbd-client 127.0.0.1 10809 /dev/nbd0
ExecStop=/usr/sbin/nbd-client -d /dev/nbd0

[Install]
WantedBy=multi-user.target
```

### mnt-crucible\x2dstorage.mount
Mounts the ext4 filesystem.

```ini
[Unit]
Description=Crucible Storage Mount
After=crucible-nbd-connect.service
Requires=crucible-nbd-connect.service

[Mount]
What=/dev/nbd0
Where=/mnt/crucible-storage
Type=ext4
Options=defaults,noatime

[Install]
WantedBy=multi-user.target
```

### Wrapper Script (/usr/local/bin/crucible-nbd-wrapper.sh)

```bash
#!/bin/bash
# Timestamp-based generation for split-brain prevention
exec /usr/local/bin/crucible-nbd-server "$@" --gen $(date +%s)
```

---

## Troubleshooting

### NBD Not Connected

```bash
# Check NBD server status
systemctl status crucible-nbd.service

# Check logs
journalctl -u crucible-nbd.service -n 50

# Restart
systemctl restart crucible-nbd.service
sleep 3
systemctl restart crucible-nbd-connect.service
```

### Mount Failed

```bash
# Check if NBD is connected first
lsblk /dev/nbd0

# Try manual mount
mount /dev/nbd0 /mnt/crucible-storage

# Check filesystem
fsck -n /dev/nbd0
```

### Downstairs Not Responding

```bash
# On proper-raptor
ssh ubuntu@192.168.4.189 "systemctl status crucible-vm-pve-* --no-pager"

# Restart specific downstairs
ssh ubuntu@192.168.4.189 "sudo systemctl restart crucible-vm-pve-0 crucible-vm-pve-1 crucible-vm-pve-2"
```

### Generation Number Issues

The wrapper script uses `$(date +%s)` which always increases. If you see "generation too low" errors:

```bash
# The timestamp approach should handle this automatically
# But if needed, check current gen on downstairs:
ssh ubuntu@192.168.4.189 "cat /crucible/vm-pve-0/region.json | grep gen"
```

---

## Complete Rebuild Procedure

If you need to completely rebuild from scratch:

```bash
# 1. Stop everything on all Proxmox hosts
for host in pve still-fawn.maas pumped-piglet.maas chief-horse.maas; do
    ssh root@$host '
        systemctl stop mnt-crucible\\x2dstorage.mount 2>/dev/null || true
        systemctl stop crucible-nbd-connect.service 2>/dev/null || true
        systemctl stop crucible-nbd.service 2>/dev/null || true
        umount /mnt/crucible-storage 2>/dev/null || true
        nbd-client -d /dev/nbd0 2>/dev/null || true
        rm -f /etc/systemd/system/crucible-nbd*.service
        rm -f /etc/systemd/system/mnt-crucible*.mount
        systemctl daemon-reload
    '
done

# 2. (Optional) Recreate downstairs on proper-raptor
# See Appendix A

# 3. Rebuild binary
# See Step 2

# 4. Redeploy
/opt/homebrew/bin/bash scripts/crucible/attach-volumes-to-proxmox.sh

# 5. Format and mount
# See Step 5

# 6. Add to Proxmox
# See Step 6
```

---

## Appendix A: Creating Downstairs Volumes on proper-raptor

If downstairs don't exist, create them:

```bash
ssh ubuntu@192.168.4.189

# For each host volume (pve example, ports 3820-3822)
UUID=$(uuidgen)
for i in 0 1 2; do
    PORT=$((3820 + i))
    DIR="/crucible/vm-pve-${i}"

    sudo mkdir -p "$DIR"
    sudo chown ubuntu:ubuntu "$DIR"

    /home/ubuntu/crucible-downstairs create \
        -d "$DIR" \
        --block-size 4096 \
        --extent-size 32768 \
        --extent-count 100 \
        --uuid "$UUID"

    # Create systemd service
    sudo tee /etc/systemd/system/crucible-vm-pve-${i}.service > /dev/null << EOF
[Unit]
Description=Crucible VM Disk - pve Region ${i}
After=network.target

[Service]
Type=simple
User=ubuntu
ExecStart=/home/ubuntu/crucible-downstairs run -p ${PORT} -d ${DIR}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
done

sudo systemctl daemon-reload
sudo systemctl enable --now crucible-vm-pve-{0,1,2}.service
```

Repeat for still-fawn (3830-3832), pumped-piglet (3840-3842), chief-horse (3850-3852).

Or use the existing script:
```bash
./scripts/crucible/create-vm-disk-volumes.sh
```

---

## Appendix B: K8s Build Job YAML

**File**: `scripts/crucible/k8s/crucible-build-job.yaml`

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: crucible-build
---
apiVersion: batch/v1
kind: Job
metadata:
  name: crucible-nbd-build
  namespace: crucible-build
spec:
  ttlSecondsAfterFinished: 7200
  template:
    spec:
      nodeSelector:
        kubernetes.io/hostname: k3s-vm-pumped-piglet-gpu
      containers:
      - name: rust-builder
        image: rust:1.83-bookworm
        resources:
          requests:
            cpu: "4"
            memory: "8Gi"
          limits:
            cpu: "8"
            memory: "16Gi"
        command: ["/bin/bash", "-c"]
        args:
        - |
          set -ex

          # Install dependencies
          apt-get update
          apt-get install -y git pkg-config libssl-dev

          # Clone Crucible
          cd /build
          git clone --depth 1 https://github.com/oxidecomputer/crucible.git
          cd crucible

          # Show the line we're patching
          echo "=== Before patch ==="
          grep -n 'generation: u64' nbd_server/src/main.rs
          grep -n 'TcpListener::bind' nbd_server/src/main.rs

          # Apply patch: Add --address flag after the generation field
          sed -i '/generation: u64,/a\
          \
              /// Address to bind the NBD server (default: 127.0.0.1:10809)\
              #[clap(short = '\''a'\'', long, default_value = "127.0.0.1:10809")]\
              address: String,' nbd_server/src/main.rs

          # Replace hardcoded bind address with opt.address
          sed -i 's/TcpListener::bind("127.0.0.1:10809")/TcpListener::bind(\&opt.address)/' nbd_server/src/main.rs

          # Verify patch
          echo "=== After patch ==="
          grep -A3 'generation: u64' nbd_server/src/main.rs
          grep -n 'bind(&opt.address)' nbd_server/src/main.rs || { echo "PATCH FAILED!"; exit 1; }

          # Build
          echo "=== Building crucible-nbd-server ==="
          cargo build --release -p crucible-nbd-server 2>&1

          # Copy to output
          cp target/release/crucible-nbd-server /output/
          chmod +x /output/crucible-nbd-server

          # Verify
          echo "=== Verifying build ==="
          /output/crucible-nbd-server --help

          echo "=== BUILD COMPLETE ==="
          ls -la /output/
        volumeMounts:
        - name: build-cache
          mountPath: /build
        - name: cargo-cache
          mountPath: /usr/local/cargo/registry
        - name: output
          mountPath: /output
      restartPolicy: Never
      volumes:
      - name: build-cache
        emptyDir:
          sizeLimit: 20Gi
      - name: cargo-cache
        emptyDir:
          sizeLimit: 10Gi
      - name: output
        hostPath:
          path: /tmp/crucible-build
          type: DirectoryOrCreate
  backoffLimit: 1
```

---

## Appendix C: Files Reference

| File | Purpose |
|------|---------|
| `scripts/crucible/attach-volumes-to-proxmox.sh` | Main deployment script |
| `scripts/crucible/setup-nbd-client.sh` | Per-host setup (called by above) |
| `scripts/crucible/create-vm-disk-volumes.sh` | Creates downstairs on proper-raptor |
| `scripts/crucible/k8s/crucible-build-job.yaml` | K8s job to build patched binary |
| `docs/crucible-deployment-runbook.md` | This document |
| `docs/crucible-proxmox-nbd-integration-guide.md` | Original integration guide |
| `docs/ma90-crucible-deployment-complete-guide.md` | MA90 hardware setup guide |

---

## Appendix D: Quick Commands

```bash
# Check status on all hosts
for h in pve still-fawn.maas pumped-piglet.maas chief-horse.maas; do
    echo "=== $h ===" && ssh root@$h "df -h /mnt/crucible-storage 2>/dev/null | tail -1 || echo 'NOT MOUNTED'"
done

# Restart NBD on a host
ssh root@pve "systemctl restart crucible-nbd crucible-nbd-connect mnt-crucible\\x2dstorage.mount"

# Check downstairs on proper-raptor
ssh ubuntu@192.168.4.189 "ss -tlnp | grep crucible"

# View logs
ssh root@pve "journalctl -u crucible-nbd -n 20"
```

---

**TAGS**: crucible, proxmox, nbd, storage, deployment, runbook, ext4, replication
