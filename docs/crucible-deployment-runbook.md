# Crucible Storage Deployment Runbook

**Status**: WORKING - deployed to all 4 Proxmox hosts
**Architecture**: ext4-on-NBD with Crucible quorum (single sled)

---

## Quick Start (TL;DR)

Already have downstairs running on proper-raptor? Deploy in 3 commands:

```bash
# 1. Deploy NBD services to all hosts
./scripts/crucible/attach-volumes-to-proxmox.sh

# 2. Format and mount (first time only - skip if already formatted)
for host in pve still-fawn.maas pumped-piglet.maas chief-horse.maas fun-bedbug.maas; do
    ssh root@$host 'mkfs.ext4 -q /dev/nbd0 && mkdir -p /mnt/crucible-storage && mount /dev/nbd0 /mnt/crucible-storage'
done

# 3. Verify
for host in pve still-fawn.maas pumped-piglet.maas chief-horse.maas fun-bedbug.maas; do
    echo "=== $host ===" && ssh root@$host 'df -h /mnt/crucible-storage | tail -1'
done
```

For first-time setup or troubleshooting, continue reading.

---

## WARNING: Single Point of Failure

**Current setup provides ZERO fault tolerance.**

All 3 downstairs processes run on **one MA90 sled** (proper-raptor) with **one SSD**. The "3-way" is only for Crucible's quorum protocol to function.

```
CURRENT SETUP (Budget Testing):
+-------------------------------------+
|  proper-raptor (SINGLE SSD)         |
|                                     |
|  downstairs :3820 --+               |
|  downstairs :3821 --+--> SAME DISK  |
|  downstairs :3822 --+               |
|                                     |
|  If this sled dies = ALL DATA LOST  |
+-------------------------------------+

TRUE 3-WAY REPLICATION (Requires 2 more MA90s):
+--------------+  +--------------+  +--------------+
| MA90 Sled #1 |  | MA90 Sled #2 |  | MA90 Sled #3 |
| :3820        |  | :3820        |  | :3820        |
| SSD #1       |  | SSD #2       |  | SSD #3       |
+--------------+  +--------------+  +--------------+
       |                |                |
       +----------------+----------------+
                        |
             Any 1 sled can fail
             Data survives
```

**Use for testing/learning only. NOT for critical data.**

---

## Architecture

### What Gets Deployed

Each Proxmox host gets `/mnt/crucible-storage` (12GB ext4) backed by Crucible on proper-raptor.

### Network Topology

```
                                 +---------------------------+
                                 |      Main Network         |
                                 |    192.168.4.0/24         |
                                 +------------+--------------+
                                              |
                                              | 10GbE SFP+
                                              |
                                 +------------+--------------+
                                 |   2.5GbE Managed Switch   |
                                 |   (8-port + 10G uplink)   |
                                 +--+------+------+------+---+
                                    |      |      |      |
                                  2.5G   2.5G   2.5G   2.5G
                                    |      |      |      |
        +---------------------------+      |      |      +---------------------------+
        |                                  |      |                                  |
        v                                  v      v                                  v
+---------------+               +---------------+  +---------------+       +---------------+
|  still-fawn   |               | pumped-piglet |  | chief-horse   |       | proper-raptor |
| 192.168.4.17  |               | 192.168.4.175 |  | 192.168.4.19  |       | 192.168.4.189 |
|               |               |               |  |               |       |               |
| USB 2.5GbE    |               | USB 2.5GbE    |  | USB 2.5GbE    |       | USB 2.5GbE    |
| (RTL8156)     |               | (RTL8156)     |  | (RTL8156)     |       | (RTL8156)     |
|               |               |               |  |               |       |               |
| Proxmox Host  |               | Proxmox Host  |  | Proxmox Host  |       | MA90 Sled     |
| (consumer)    |               | (consumer)    |  | (consumer)    |       | (storage)     |
+---------------+               +---------------+  +---------------+       +---------------+
```

### Hardware

| Component | Model | Cost |
|-----------|-------|------|
| Switch | 8-port 2.5GbE + 10GbE SFP+ uplink | ~$60 |
| USB NICs | RTL8156-based USB 3.0 to 2.5GbE | ~$15 each |
| Storage Sled | ATOPNUC MA90 AMD mini PC | ~$30 used |

### Data Flow

```
+----------------+     +-----------------+     +-----------------------------+
|  Proxmox Host  |     |  NBD Server     |     |  proper-raptor (storage)    |
|                |     |  (localhost)    |     |  192.168.4.189              |
|                |     |                 |     |                             |
| /mnt/crucible- |     | crucible-nbd-   |     | +-------------------------+ |
| storage (ext4) |---->| server          |---->| | downstairs :38X0        | |
|                |     | :10809          |     | | downstairs :38X1        | |
| /dev/nbd0      |     |                 |     | | downstairs :38X2        | |
+----------------+     +-----------------+     | +-------------------------+ |
                                              |    (quorum only, 1 disk!)    |
                                              +------------------------------+
```

### Port Allocation

| Host | Downstairs Ports | NBD Port | Device |
|------|------------------|----------|--------|
| pve | 3820, 3821, 3822 | 10809 | /dev/nbd0 |
| still-fawn | 3830, 3831, 3832 | 10809 | /dev/nbd0 |
| pumped-piglet | 3840, 3841, 3842 | 10809 | /dev/nbd0 |
| chief-horse | 3850, 3851, 3852 | 10809 | /dev/nbd0 |
| fun-bedbug | 3860, 3861, 3862 | 10809 | /dev/nbd0 |

---

## Prerequisites

1. **proper-raptor online** at 192.168.4.189 with downstairs running
2. **SSH access** to all Proxmox hosts as root
3. **crucible-nbd-server binary** on proper-raptor (see Step 2 if missing)

---

## Deployment Steps

### Step 1: Verify Downstairs on proper-raptor

```bash
ssh ubuntu@192.168.4.189 "ss -tlnp | grep crucible"
```

**Expected**: Ports 3820-3852 listening (12 total, 3 per host)

```
LISTEN 0 1024 0.0.0.0:3820 0.0.0.0:* users:(("crucible-downst"...))
LISTEN 0 1024 0.0.0.0:3821 0.0.0.0:* users:(("crucible-downst"...))
...
```

If missing, see [Appendix A: Creating Downstairs Volumes](#appendix-a-creating-downstairs-volumes).

---

### Step 2: Ensure Binary Exists (Skip if Already Built)

Check if the patched binary exists:

```bash
ssh ubuntu@192.168.4.189 "/home/ubuntu/crucible-nbd-server --help 2>&1 | head -1"
```

If it exists, skip to Step 3. If not, build it:

**Option A: Build via K8s Job** (~5 minutes)

```bash
export KUBECONFIG=~/kubeconfig
kubectl apply -f scripts/crucible/k8s/crucible-build-job.yaml
kubectl logs -n crucible-build -f job/crucible-nbd-build
```

When complete, extract the binary:

```bash
# Create helper pod to access the built binary
kubectl apply -f - <<'EOF'
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
scp /tmp/crucible-nbd-server ubuntu@192.168.4.189:/home/ubuntu/
kubectl delete ns crucible-build
```

**Option B: Copy From Backup**

```bash
scp ubuntu@192.168.4.189:/home/ubuntu/crucible-nbd-server /tmp/crucible-nbd-server
```

---

### Step 3: Deploy to All Proxmox Hosts

```bash
./scripts/crucible/attach-volumes-to-proxmox.sh
```

This script:
1. Copies binary from proper-raptor to each host
2. Installs `nbd-client` package
3. Creates systemd services with timestamp-based generation
4. Starts services and connects `/dev/nbd0`

---

### Step 4: Format and Mount (First Time Only)

**Skip this step if already formatted.** Check with: `ssh root@pve 'blkid /dev/nbd0'`

```bash
for host in pve still-fawn.maas pumped-piglet.maas chief-horse.maas fun-bedbug.maas; do
    echo "=== $host ==="
    ssh root@$host 'set -e
        # Format if needed
        blkid /dev/nbd0 | grep -q ext4 || mkfs.ext4 -q /dev/nbd0

        # Mount
        mkdir -p /mnt/crucible-storage
        mount /dev/nbd0 /mnt/crucible-storage 2>/dev/null || true

        # Persistent mount unit
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
        df -h /mnt/crucible-storage | tail -1'
done
```

---

### Step 5: Add to Proxmox Storage (Optional)

Register the mount as Proxmox storage for VM disks, ISOs, backups:

```bash
for host in pve still-fawn.maas pumped-piglet.maas chief-horse.maas fun-bedbug.maas; do
    echo "=== $host ==="
    ssh root@$host 'pvesm status | grep -q crucible-storage || \
        pvesm add dir crucible-storage --path /mnt/crucible-storage --content images,vztmpl,iso,backup
        pvesm status | grep crucible-storage'
done
```

---

## Verification

Run this to check all hosts at once:

```bash
for host in pve still-fawn.maas pumped-piglet.maas chief-horse.maas fun-bedbug.maas; do
    echo "=== $host ==="
    ssh root@$host '
        printf "NBD:     " && (lsblk -no SIZE /dev/nbd0 2>/dev/null || echo "NOT CONNECTED")
        printf "Mount:   " && (df -h /mnt/crucible-storage 2>/dev/null | awk "NR==2{print \$3,\"/\",\$2}" || echo "NOT MOUNTED")
        printf "Storage: " && (pvesm status 2>/dev/null | grep crucible-storage | awk "{print \$2}" || echo "NOT CONFIGURED")'
    echo
done
```

**Expected output per host:**
```
=== pve ===
NBD:     12G
Mount:   1.2G / 12G
Storage: active
```

Check downstairs on proper-raptor:

```bash
ssh ubuntu@192.168.4.189 "systemctl status crucible-vm-* --no-pager | grep -E '(Active:|●)'"
```

---

## Troubleshooting

### NBD Not Connected

```bash
# On the affected Proxmox host:
systemctl status crucible-nbd.service
journalctl -u crucible-nbd.service -n 50 --no-pager

# Restart sequence
systemctl restart crucible-nbd.service && sleep 3 && systemctl restart crucible-nbd-connect.service
```

### Mount Failed

```bash
# Verify NBD is connected first
lsblk /dev/nbd0 || echo "NBD not connected - fix that first"

# Try manual mount
mount /dev/nbd0 /mnt/crucible-storage

# Check filesystem integrity (read-only)
fsck -n /dev/nbd0
```

### Downstairs Not Responding

```bash
# Check status on proper-raptor
ssh ubuntu@192.168.4.189 "systemctl status crucible-vm-* --no-pager | grep -E '(●|Active:|failed)'"

# Restart all downstairs for a specific host (e.g., pve = ports 3820-3822)
ssh ubuntu@192.168.4.189 "sudo systemctl restart crucible-vm-pve-0 crucible-vm-pve-1 crucible-vm-pve-2"
```

### Generation Number Issues

The wrapper uses `$(date +%s)` (Unix timestamp) which auto-increments. If you still see "generation too low":

```bash
# Check stored generation on downstairs
ssh ubuntu@192.168.4.189 "cat /crucible/vm-pve-0/region.json | jq .gen"

# Force higher generation manually (emergency only)
ssh root@pve "/usr/local/bin/crucible-nbd-server --target 192.168.4.189:3820 --target 192.168.4.189:3821 --target 192.168.4.189:3822 --gen 9999999999"
```

### Network Connectivity

```bash
# From Proxmox host, verify reach to proper-raptor
nc -zv 192.168.4.189 3820 3821 3822

# Check if downstairs ports are listening
ssh ubuntu@192.168.4.189 "ss -tlnp | grep ':38'"
```

---

## Complete Rebuild

To wipe and start fresh:

```bash
# 1. Stop and remove on all Proxmox hosts
for host in pve still-fawn.maas pumped-piglet.maas chief-horse.maas fun-bedbug.maas; do
    ssh root@$host 'systemctl stop mnt-crucible\\x2dstorage.mount crucible-nbd-connect crucible-nbd 2>/dev/null
        umount /mnt/crucible-storage 2>/dev/null; nbd-client -d /dev/nbd0 2>/dev/null
        rm -f /etc/systemd/system/crucible-nbd*.service /etc/systemd/system/mnt-crucible*.mount
        systemctl daemon-reload'
done

# 2. Redeploy
./scripts/crucible/attach-volumes-to-proxmox.sh

# 3. Format and mount (will destroy data!)
# See Step 4
```

---

## Appendix A: Creating Downstairs Volumes

If downstairs processes don't exist on proper-raptor:

```bash
# Use the automated script
./scripts/crucible/create-vm-disk-volumes.sh
```

Or manually per host (example for pve, ports 3820-3822):

```bash
ssh ubuntu@192.168.4.189 'UUID=$(uuidgen)
for i in 0 1 2; do
    PORT=$((3820 + i))
    DIR="/crucible/vm-pve-${i}"
    sudo mkdir -p "$DIR" && sudo chown ubuntu:ubuntu "$DIR"
    /home/ubuntu/crucible-downstairs create -d "$DIR" --block-size 4096 --extent-size 32768 --extent-count 100 --uuid "$UUID"
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
sudo systemctl daemon-reload && sudo systemctl enable --now crucible-vm-pve-{0,1,2}.service'
```

Repeat for: still-fawn (3830-3832), pumped-piglet (3840-3842), chief-horse (3850-3852).

---

## Appendix B: Systemd Service Reference

Three services run on each Proxmox host:

| Service | Purpose |
|---------|---------|
| `crucible-nbd.service` | NBD server connecting to proper-raptor downstairs |
| `crucible-nbd-connect.service` | Connects nbd-client to local NBD server |
| `mnt-crucible\x2dstorage.mount` | Mounts ext4 filesystem |

**Dependency chain**: `network-online.target` -> `crucible-nbd` -> `crucible-nbd-connect` -> `mnt-crucible\x2dstorage.mount`

The wrapper script (`/usr/local/bin/crucible-nbd-wrapper.sh`) adds `--gen $(date +%s)` for split-brain prevention.

---

## Appendix C: Bridge Configuration (proper-raptor)

The MA90 uses a bridge on the USB NIC for reliable boot:

```
# /etc/network/interfaces on proper-raptor
auto lo
iface lo inet loopback

iface enp1s0 inet manual         # Built-in 1GbE - unused

auto enx00e04ca81110             # USB 2.5GbE adapter
iface enx00e04ca81110 inet manual

auto br0                         # Bridge on USB adapter
iface br0 inet static
    address 192.168.4.189/24
    gateway 192.168.4.1
    bridge-ports enx00e04ca81110
    bridge-stp off
    bridge-fd 0
    dns-nameservers 192.168.4.53
```

**Why bridge?** USB NICs can be flaky at boot. Bridge waits for interface and matches Proxmox patterns.

---

## Appendix D: Related Files

| File | Purpose |
|------|---------|
| `scripts/crucible/attach-volumes-to-proxmox.sh` | Main deployment script |
| `scripts/crucible/setup-nbd-client.sh` | Per-host setup (called by above) |
| `scripts/crucible/create-vm-disk-volumes.sh` | Creates downstairs on proper-raptor |
| `scripts/crucible/k8s/crucible-build-job.yaml` | K8s job to build patched binary |
| `docs/crucible-proxmox-nbd-integration-guide.md` | Original integration guide |
| `docs/ma90-crucible-deployment-complete-guide.md` | MA90 hardware setup |

---

**TAGS**: crucible, proxmox, nbd, storage, deployment, runbook, ext4, replication
