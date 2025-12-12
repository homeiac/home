# How I Mounted a ZFS Dataset into a K3s VM Using VirtioFS

*December 12, 2025*

I recently migrated my Frigate NVR from an LXC container to Kubernetes. Everything was working great—GPU acceleration, camera feeds, new recordings—but I had 118GB of old recordings sitting on the Proxmox host that the K8s pod couldn't see.

This is the story of how I solved it, the wrong turns I took, and what actually worked.

## The Problem

My setup:
- **Proxmox 8.4** with ZFS storage
- **K3s cluster** running in VMs on Proxmox
- **Old recordings** at `/local-3TB-backup/subvol-113-disk-0/frigate/` on the host
- **Frigate pod** needs to access these recordings at `/import`

The catch: VMs can't directly access ZFS datasets. Unlike LXC containers that can bind-mount host directories, VMs are isolated. The host filesystem might as well be on another planet.

## What I Tried (And Why It Failed)

### Attempt 1: 9p Virtio Filesystem

My first instinct was 9p, an older protocol for sharing host directories with VMs. I added the magic args to the VM config:

```bash
args: -fsdev local,security_model=passthrough,id=fsdev0,path=/local-3TB-backup/subvol-113-disk-0 -device virtio-9p-pci,id=fs0,fsdev=fsdev0,mount_tag=frigate-import
```

Result: K3s kept crashing. The VM would boot, then K3s would restart repeatedly. Etcd lost quorum. It was a mess.

**Lesson learned**: 9p has known stability issues and poor performance (benchmarks show 2-8x slower than alternatives).

### Attempt 2: Just Copy the Data

"Fine," I thought, "I'll just rsync the 120GB to the VM's storage."

```bash
rsync -avP /local-3TB-backup/subvol-113-disk-0/frigate/ /local-3TB-backup/frigate-import/
```

Speed: 5 MB/s. For 120GB. That's about 7 hours.

The problem? Frigate recordings are thousands of small 10-second video clips. Rsync's per-file overhead was killing performance.

I switched to `cp -a` which hit 30 MB/s—better, but still over an hour of copying.

Then it hit me: **why copy at all?**

## The Solution: VirtioFS

Proxmox 8.4 added native VirtioFS support. It's like 9p but actually works:

- **2-8x faster** than 9p
- **Stable** (no K3s crashes)
- **GUI configuration** (no manual args hacking)
- **Proper filesystem semantics**

Here's the key insight that saved me an hour of copying: I don't need to create a new dataset. I can mount the **existing** dataset directly and just point the pod to the `/frigate` subdirectory.

### Step 1: Create Directory Mapping

In Proxmox, create a directory mapping that points to the existing ZFS dataset:

```bash
pvesh create /cluster/mapping/dir \
  --id frigate-import \
  --map node=pumped-piglet,path=/local-3TB-backup/subvol-113-disk-0
```

Or via GUI: **Datacenter → Resource Mappings → Directory → Add**

### Step 2: Attach VirtioFS to VM

This requires a VM restart, but it's quick:

```bash
qm stop 105
qm set 105 --virtiofs0 frigate-import
qm start 105
```

My K3s node was back and Ready in 68 seconds.

### Step 3: Mount Inside the VM

Here's where I hit another snag. SSH wasn't working to the VM (port 22 refused), and `qm guest exec` failed because qemu-guest-agent wasn't installed.

**Solution**: Install the guest agent via a privileged Kubernetes pod:

```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: install-guest-agent
spec:
  nodeName: k3s-vm-pumped-piglet-gpu
  hostPID: true
  containers:
  - name: nsenter
    image: ubuntu:24.04
    command: ["sleep", "3600"]
    securityContext:
      privileged: true
    volumeMounts:
    - name: host
      mountPath: /host
  volumes:
  - name: host
    hostPath:
      path: /
EOF

kubectl exec install-guest-agent -- \
  nsenter -t 1 -m -u -i -n -- \
  apt-get install -y qemu-guest-agent

kubectl exec install-guest-agent -- \
  nsenter -t 1 -m -u -i -n -- \
  systemctl start qemu-guest-agent
```

Now `qm guest exec` works:

```bash
ssh root@pumped-piglet.maas "qm guest exec 105 -- mount -t virtiofs frigate-import /mnt/frigate-import"
ssh root@pumped-piglet.maas "qm guest exec 105 -- bash -c 'echo \"frigate-import /mnt/frigate-import virtiofs defaults,nofail 0 0\" >> /etc/fstab'"
```

### Step 4: Update the Deployment

The deployment's hostPath needs to point to the frigate subdirectory:

```yaml
volumes:
  - name: old-recordings
    hostPath:
      path: /mnt/frigate-import/frigate  # Note: /frigate at the end
      type: Directory
```

### Step 5: Fix Service Selector (Bonus Bug)

After restarting the pod, `frigate.app.homelab` stopped working. The service had extra kustomize labels in its selector that the pod didn't have:

```yaml
selector:
  app: frigate
  app.kubernetes.io/component: nvr    # Pod doesn't have this
  app.kubernetes.io/name: frigate     # Or this
```

Fix: Delete and recreate the service without the extra labels.

## The Scripts

I've packaged all of this into reusable scripts:

**[scripts/frigate/virtiofs-import/](https://github.com/homeiac/home/tree/master/scripts/frigate/virtiofs-import)**

| Script | Purpose |
|--------|---------|
| `00-install-guest-agent.sh` | Install qemu-guest-agent via privileged pod |
| `04-attach-virtiofs-to-vm.sh` | Attach virtiofs device to VM |
| `05-mount-in-vm.sh` | Mount virtiofs via qm guest exec |
| `06-verify-frigate-access.sh` | Verify pod can access recordings |
| `07-fix-service-selector.sh` | Fix service selector mismatch |
| `08-run-import.sh` | Import old recordings into Frigate database |
| `09-verify-import.sh` | Verify recording import statistics |
| `99-rollback.sh` | Undo everything if needed |

## The Database Problem

After mounting, I could see the files but Frigate's UI showed nothing. The old recordings existed on disk but weren't in the database.

**The catch**: Frigate has no native import feature. The [documentation](https://docs.frigate.video/configuration/record/) is clear:

> "Tracked object and recording information is managed in a sqlite database at /config/frigate.db. If that database is deleted, recordings will be orphaned."

The original LXC backup only contained the recordings folder—no `frigate.db`. I needed to generate database entries from the files.

### The Import Script

I wrote a Python script that:
1. Scans `/import/recordings/` for all `.mp4` files
2. Parses the path (`YYYY-MM-DD/HH/camera/MM.SS.mp4`) to extract timestamps
3. Generates Frigate-style IDs (`{timestamp}.0-{random6chars}`)
4. Inserts records into `/config/frigate.db`

```python
# Key insight: timestamp from path
# 2025-12-09/17/reolink_doorbell/35.57.mp4
# → datetime(2025, 12, 9, 17, 35, 57).timestamp()
```

The Frigate container has Python3 with sqlite3, so the script runs directly in the pod:

```bash
kubectl cp import-old-recordings.py frigate/frigate-pod:/tmp/
kubectl exec -n frigate frigate-pod -- python3 /tmp/import-old-recordings.py
```

## Restoring from PBS Backups

After running the import script, I had recordings in the database but no Review UI entries. The old Frigate had detected events with thumbnails—where did that data go?

### Finding the Old Database

I checked the obvious places first:
- **fun-bedbug** (current Frigate host): Only 6 recordings from testing
- **still-fawn**: No Frigate data at all
- **/mnt/frigate-import**: Only recordings and clips—no database file

The original `frigate.db` was gone. I needed the old database to get the review segments back.

### PBS to the Rescue

Then I remembered: **Proxmox Backup Server**.

LXC 113 (the old Frigate container) had been backing up to the `homelab-backup` PBS datastore. I found backups dating back months:

```bash
pvesm list homelab-backup | grep 113
# homelab-backup:backup/ct/113/2025-12-06T06:35:41Z  159.40GB
```

The December 6 backup was 159GB—definitely had the database.

### Restore to Temporary Container

Rather than restore over the current system, I restored to a temporary container ID:

```bash
pct restore 9113 "homelab-backup:backup/ct/113/2025-12-06T06:35:41Z" \
  --storage local-3TB-backup \
  --unprivileged 1
```

Started the container and grabbed the database:

```bash
pct start 9113
pct exec 9113 -- ls -lh /config/frigate.db
# -rw-r--r-- 1 root root 58M Dec  6 06:30 /config/frigate.db
```

### Schema Mismatch Challenge

Copying the old database directly failed. The old Frigate had a `has_been_reviewed` column in the `reviewsegment` table that the new version doesn't have.

**Solution**: Extract just the data I needed (review segments and events) and insert into the new database with the correct schema.

### Safe Database Copy

First challenge: getting the database out of the container. `kubectl cp` corrupts binary files due to tar issues, so I used base64 encoding:

```bash
# Extract from temp container
pct exec 9113 -- cat /config/frigate.db | base64 > /tmp/old-frigate.db.b64

# Decode on host
base64 -d /tmp/old-frigate.db.b64 > /tmp/old-frigate.db

# Copy into Frigate pod
cat /tmp/old-frigate.db | base64 | kubectl exec -n frigate frigate-pod -i -- \
  bash -c 'base64 -d > /tmp/old-frigate.db'
```

### Merging the Data

Inside the pod, I merged the review segments and events:

```bash
kubectl exec -n frigate frigate-pod -- sqlite3 /config/frigate.db <<EOF
ATTACH DATABASE '/tmp/old-frigate.db' AS old;

INSERT OR IGNORE INTO reviews SELECT * FROM old.reviews;
INSERT OR IGNORE INTO reviewsegment
  SELECT camera, duration, end_time, has_been_reviewed, id,
         motion_box_count, person_box_count, review_id, severity,
         start_time, thumb_path, zones
  FROM old.reviewsegment;
INSERT OR IGNORE INTO event SELECT * FROM old.event;

DETACH DATABASE old;
EOF
```

### Thumbnail Symlinks

The old thumbnails were at `/import/clips/review/` but Frigate expected them at `/media/frigate/clips/review/`. Created symlinks:

```bash
kubectl exec -n frigate frigate-pod -- bash -c '
cd /media/frigate/clips/review
for f in /import/clips/review/*.jpg; do
  ln -sf "$f" "$(basename "$f")"
done
'
# Linked 2,507 thumbnail files
```

After restarting Frigate, the Review UI came alive with all the old detections, complete with thumbnails.

```bash
pct stop 9113
pct destroy 9113  # Clean up temp container
```

## Results

- **42,342 old recordings** imported into database
- **Total recordings**: 44,118 (old + new)
- **1,977 review segments** (Review UI entries)
- **3,820 events** with detection data
- **Date range**: May 31, 2025 → December 12, 2025
- **Old recordings with thumbnails** visible in Review UI
- **Zero copy time** (mounted existing dataset)
- **K3s cluster stable** (3/3 nodes Ready)
- **VirtioFS persistent** (survives reboots via fstab)

## Key Takeaways

1. **VirtioFS > 9p** for Proxmox 8.4+. It's faster, more stable, and has GUI support.

2. **Don't copy when you can mount.** My initial instinct was to copy 120GB. Mounting the existing dataset saved an hour.

3. **qemu-guest-agent is your friend.** When SSH fails, `qm guest exec` works—but only if the agent is installed. Use a privileged pod to install it.

4. **Frigate recordings need the database.** Files on disk are useless without corresponding entries in `frigate.db`. If you only backup recordings, you'll need to regenerate the database entries.

5. **PBS backups are gold.** When you need old database state, restore to a temp container, extract what you need, then destroy it.

6. **Kustomize labels can break services.** If you apply manifests directly (not via kustomize), watch out for selector mismatches.

7. **Document everything.** The action log I kept during this process made writing this post trivial and will help when I inevitably forget how this works in 6 months.

---

*Scripts: [github.com/homeiac/home/scripts/frigate/virtiofs-import](https://github.com/homeiac/home/tree/master/scripts/frigate/virtiofs-import)*
