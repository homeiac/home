# Building a $30 "Oxide-Style" Storage Sled for Your Homelab

**Date**: January 25, 2026
**Author**: Claude + Human collaboration
**Tags**: oxide, crucible, storage, homelab, ma90, budget, distributed-storage

---

## The Dream: Oxide Computer's Distributed Storage at Home

[Oxide Computer](https://oxide.computer/) builds rack-scale computers with incredible distributed storage powered by their open-source [Crucible](https://github.com/oxidecomputer/crucible) software. Their racks cost hundreds of thousands of dollars. But what if you could run the same storage software on a $30 mini PC?

**Spoiler**: You can. Here's how I did it.

## The Hardware: AMD MA90 Mini PC ($30)

The ATOPNUC MA90 is a tiny fanless mini PC that shows up on AliExpress and eBay for around $30:

```
┌─────────────────────────────────────────┐
│            ATOPNUC MA90                 │
├─────────────────────────────────────────┤
│  CPU:     AMD A9-9400 (2c/2t, 2.4GHz)  │
│  RAM:     8GB DDR4                      │
│  Storage: 128GB M.2 SATA SSD           │
│  Network: 1GbE (built-in)              │
│  Power:   ~15W TDP                      │
│  Size:    Fits in your palm            │
├─────────────────────────────────────────┤
│  Cost:    ~$30 used                     │
└─────────────────────────────────────────┘
```

It's not fast. It's not fancy. But it runs Ubuntu, and that's all Crucible needs.

## The Network: Dedicated 2.5GbE Storage Fabric

Here's where it gets interesting. The MA90 only has 1GbE built-in, but I added a USB 2.5GbE adapter (~$15). The key is the network topology:

```
                           ┌─────────────────────────┐
                           │    Main Network         │
                           │    192.168.4.0/24       │
                           │    (existing switches)  │
                           └───────────┬─────────────┘
                                       │
                                       │ 10GbE SFP+
                                       │
                           ┌───────────┴─────────────┐
                           │   2.5GbE Switch         │
                           │   (8-port managed)      │
                           │                         │
                           │   ┌─────┬─────┬─────┐   │
                           │   │ 2.5G│ 2.5G│ 2.5G│   │
                           │   └──┬──┴──┬──┴──┬──┘   │
                           └──────┼─────┼─────┼──────┘
                                  │     │     │
                    ┌─────────────┘     │     └─────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
           ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
           │   Proxmox     │   │   Proxmox     │   │   MA90 Sled   │
           │  still-fawn   │   │pumped-piglet  │   │ proper-raptor │
           │  USB 2.5GbE   │   │  USB 2.5GbE   │   │  USB 2.5GbE   │
           │ 192.168.4.17  │   │ 192.168.4.175 │   │ 192.168.4.189 │
           └───────────────┘   └───────────────┘   └───────────────┘
```

**Why a separate storage network?**

- **Isolation**: Storage traffic doesn't compete with user traffic
- **Aggregation**: 10GbE uplink handles the combined 2.5GbE connections
- **Cost**: Cheap 2.5GbE switches (~$60) vs expensive 10GbE everywhere

**The USB 2.5GbE adapters** (RTL8156 chipset, ~$15 each):

- Work out of the box on Linux (built-in r8152 driver)
- Reliable with proper bridge configuration
- Much cheaper than adding PCIe 2.5GbE NICs to old Proxmox boxes

## The Bridge Configuration

On the MA90 (Ubuntu 24.04), I use a bridge just like the Proxmox hosts. This ensures reliable boot even with USB NICs:

```bash
# /etc/network/interfaces on proper-raptor

auto lo
iface lo inet loopback

# Built-in 1GbE - unused, no cable
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

**Why a bridge for a single NIC?**

1. **Boot reliability**: USB NICs can be flaky at boot (device enumeration timing). The bridge waits for the interface to come up.
2. **Consistency**: Matches Proxmox host configuration (easier to manage fleet-wide).
3. **Future-proofing**: Allows adding VMs later if you want to repurpose the sled.

## Installing Crucible

Crucible requires building from source (Rust). I do this in a Kubernetes pod for speed since the MA90's 2 cores would take forever:

```bash
# Build Crucible binaries in K8s (8 cores, ~5 minutes)
kubectl apply -f scripts/crucible/k8s/crucible-build-job.yaml

# Wait for build to complete
kubectl wait --for=condition=complete job/crucible-build -n crucible-build --timeout=600s

# Extract the binaries
kubectl cp crucible-build/crucible-build-pod:/output/crucible-downstairs /tmp/
kubectl cp crucible-build/crucible-build-pod:/output/crucible-nbd-server /tmp/

# Copy to MA90
scp /tmp/crucible-* ubuntu@192.168.4.189:/home/ubuntu/
```

## Setting Up the Storage Backend

On the MA90, Crucible stores its data in "regions" on disk. While Crucible doesn't require ZFS, it's a good choice for its checksumming and compression:

```bash
# SSH to MA90
ssh ubuntu@192.168.4.189

# Install ZFS
sudo apt update && sudo apt install -y zfsutils-linux

# Create ZFS pool on remaining disk space
# (Ubuntu uses ~25GB, leaving ~90GB for storage)
sudo zpool create -o ashift=12 crucible /dev/sda3

# Create directories for Crucible regions
sudo mkdir -p /crucible
sudo chown ubuntu:ubuntu /crucible
```

**Note**: You could also use ext4 or XFS. Crucible itself handles replication and integrity at the application layer.

## The Quorum Trick: 3 Downstairs on 1 Sled

Crucible requires 3 "downstairs" processes for its quorum protocol. In production, you'd run these on 3 separate sleds for fault tolerance. But for testing, you can run all 3 on one machine:

```bash
# Generate a shared UUID for the volume
UUID=$(uuidgen)

# Create 3 regions (same UUID = same volume, 3 replicas)
for i in 0 1 2; do
    PORT=$((3820 + i))
    DIR="/crucible/region-${i}"

    mkdir -p "$DIR"

    ./crucible-downstairs create \
        --data "$DIR" \
        --block-size 4096 \
        --extent-size 32768 \
        --extent-count 100 \
        --uuid "$UUID"
done

# Start 3 downstairs processes (use systemd in production)
for i in 0 1 2; do
    PORT=$((3820 + i))
    nohup ./crucible-downstairs run \
        --address "[::]:${PORT}" \
        --data /crucible/region-${i} \
        > /var/log/crucible-downstairs-${i}.log 2>&1 &
done
```

**Result**: 3 downstairs processes on ports 3820, 3821, 3822, all on one $30 sled.

## Connecting from Proxmox

On each Proxmox host, the "upstairs" (NBD server) connects to all 3 downstairs:

```bash
# On Proxmox host (e.g., still-fawn)
./crucible-nbd-server \
    --target 192.168.4.189:3820 \
    --target 192.168.4.189:3821 \
    --target 192.168.4.189:3822 \
    --generation $(date +%s)

# Load the NBD kernel module
modprobe nbd

# Connect NBD client to the local upstairs
nbd-client 127.0.0.1 10809 /dev/nbd0

# Format and mount (first time only)
mkfs.ext4 /dev/nbd0
mount /dev/nbd0 /mnt/crucible-storage

# Add to Proxmox as directory storage
pvesm add dir crucible-storage --path /mnt/crucible-storage --content images,rootdir
```

## The Complete Architecture

Here's how all the pieces fit together:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           COMPLETE SETUP                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│   PROXMOX HOSTS (Consumers)               MA90 STORAGE SLED (Provider)       │
│   ─────────────────────────               ────────────────────────────       │
│                                                                               │
│   ┌─────────────────────┐                 ┌─────────────────────────────┐    │
│   │     still-fawn      │                 │      proper-raptor          │    │
│   │   192.168.4.17      │                 │    192.168.4.189            │    │
│   │                     │                 │                             │    │
│   │ ┌─────────────────┐ │     2.5GbE      │ ┌─────────────────────────┐ │    │
│   │ │crucible-nbd-svr │─┼─────────────────┼─│ downstairs :3820        │ │    │
│   │ │    :10809       │ │                 │ │ downstairs :3821        │ │    │
│   │ └────────┬────────┘ │                 │ │ downstairs :3822        │ │    │
│   │          │          │                 │ └───────────┬─────────────┘ │    │
│   │          ▼          │                 │             │               │    │
│   │    /dev/nbd0        │                 │             ▼               │    │
│   │          │          │                 │    ┌─────────────────┐      │    │
│   │          ▼          │                 │    │   ZFS Pool      │      │    │
│   │ /mnt/crucible-      │                 │    │   /crucible     │      │    │
│   │    storage (ext4)   │                 │    │   (~90GB)       │      │    │
│   │                     │                 │    └─────────────────┘      │    │
│   │ Proxmox sees this   │                 │                             │    │
│   │ as local storage!   │                 │    Cost: ~$30               │    │
│   └─────────────────────┘                 └─────────────────────────────┘    │
│                                                                               │
│   ┌─────────────────────┐                 Each Proxmox host gets its own     │
│   │   pumped-piglet     │─────────────────► volume with dedicated ports:     │
│   │  (separate volume)  │                   :3830, :3831, :3832              │
│   └─────────────────────┘                                                    │
│                                                                               │
│   ┌─────────────────────┐                                                    │
│   │   chief-horse       │─────────────────► :3840, :3841, :3842              │
│   │  (separate volume)  │                                                    │
│   └─────────────────────┘                                                    │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Important Caveat: This is NOT True Replication

Let me be crystal clear about what this setup provides:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  WARNING: SINGLE POINT OF FAILURE                                            │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│   CURRENT SETUP (Budget Testing)          TRUE 3-WAY REPLICATION             │
│   ──────────────────────────────          ──────────────────────             │
│                                                                               │
│   ┌─────────────────────┐                ┌────────┐ ┌────────┐ ┌────────┐   │
│   │  ONE MA90 SLED      │                │ MA90#1 │ │ MA90#2 │ │ MA90#3 │   │
│   │  ONE SSD            │                │ SSD #1 │ │ SSD #2 │ │ SSD #3 │   │
│   │                     │                │ :3820  │ │ :3820  │ │ :3820  │   │
│   │  :3820 ─┐           │                └────┬───┘ └────┬───┘ └────┬───┘   │
│   │  :3821 ─┼─► 1 DISK  │                     │          │          │       │
│   │  :3822 ─┘           │                     └──────────┼──────────┘       │
│   │                     │                                │                   │
│   │  Sled dies =        │                     Any 1 sled can fail           │
│   │  ALL DATA LOST      │                     Data survives                 │
│   └─────────────────────┘                                                    │
│                                                                               │
│   Cost: $30-45                            Cost: $135 (3 sleds + adapters)   │
│   Fault tolerance: NONE                   Fault tolerance: 1 sled failure   │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

The "3-way quorum" exists only so Crucible's consensus protocol can function. All 3 regions live on the **same physical disk**. If proper-raptor dies, everything is gone.

**For real fault tolerance**: Buy 2 more MA90s (~$60) and 2 more USB adapters (~$30), then run 1 downstairs per sled. Total: ~$135 for a truly redundant setup.

## Performance

With 4K block size (critical: don't use the default 512B):

| Metric | Value | Notes |
|--------|-------|-------|
| Sequential Write | ~60 MB/s | Limited by M.2 SATA SSD |
| Sequential Read | ~80 MB/s | Limited by M.2 SATA SSD |
| Random 4K IOPS | ~3,000 | Typical for SATA SSDs |
| Round-trip Latency | ~2-3ms | Network + storage combined |

Not amazing, but perfectly adequate for VM templates, ISOs, backups, and light workloads. The 2.5GbE network (312 MB/s theoretical) is not the bottleneck; the SATA SSD is.

**Important**: Use `--block-size 4096` when creating regions. The default 512B block size causes significant performance degradation due to protocol overhead.

## Bill of Materials

| Item | Cost | Notes |
|------|------|-------|
| ATOPNUC MA90 (used) | ~$30 | eBay, AliExpress |
| USB 2.5GbE adapter (RTL8156) | ~$15 | Amazon, AliExpress |
| 2.5GbE switch with SFP+ uplink | ~$60 | Shared across all hosts |
| **Total (1 sled, testing only)** | **~$45** | No fault tolerance |
| **True 3-way (3 sleds)** | **~$135** | Real distributed storage |

## Why Bother?

1. **Learning**: Understand distributed storage consensus without expensive hardware
2. **Testing**: Evaluate Crucible before committing to a larger deployment
3. **Bragging Rights**: Run the same storage software as Oxide's $200k+ racks
4. **Upgrade Path**: Start with 1 sled, add more when you're ready for real replication

## Scripts and Automation

Everything is scripted for reproducibility in the [home](https://github.com/pandero-systems/home) repository:

```bash
# Create downstairs regions on MA90
./scripts/crucible/create-vm-disk-volumes.sh

# Deploy NBD clients to all Proxmox hosts
./scripts/crucible/attach-volumes-to-proxmox.sh

# Build Crucible binaries from source (in K8s)
kubectl apply -f scripts/crucible/k8s/crucible-build-job.yaml
```

Full deployment runbook: [`docs/crucible-deployment-runbook.md`](../crucible-deployment-runbook.md)

## Conclusion

For $30-45, you can run Oxide Computer's Crucible distributed storage in your homelab. It won't survive hardware failures (unless you buy more sleds), but it's a fantastic way to learn about distributed storage, experiment with the same technology used in enterprise racks, and maybe even use it for non-critical workloads.

The real magic is in the software: Crucible's quorum-based consensus, generation numbers for split-brain prevention, and the clean separation between upstairs (client-side) and downstairs (storage-side). The hardware can be as cheap as you want.

**Next steps for me**: Buy 2 more MA90s and actually distribute the downstairs processes. Stay tuned.

---

**Related Posts**:

- [Crucible Deployment Runbook](../crucible-deployment-runbook.md)
- [MA90 MAAS Deployment Guide](../ma90-crucible-deployment-complete-guide.md)

**Resources**:

- [Oxide Crucible GitHub](https://github.com/oxidecomputer/crucible)
- [Oxide Computer Company](https://oxide.computer/)
- [Crucible Architecture Overview](https://github.com/oxidecomputer/crucible/blob/main/doc/README.md)
