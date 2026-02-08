# How Automated Backups Saved My Frigate Face Recognition Data

**Date**: 2026-02-08
**Tags**: frigate, backup, disaster-recovery, face-recognition, homelab, k3s

---

## The Incident

It was a Saturday afternoon when I noticed my Frigate NVR wasn't responding. A quick check revealed the problem: the still-fawn Proxmox host had gone offline, taking with it:

- The K3s VM running Frigate
- The Coral USB TPU for object detection
- The local-path PVC containing all my configuration
- **580 face training images** painstakingly collected over weeks

The VM's disk was gone. The PBS backup of the VM existed, but extracting individual files from a 700GB disk image isn't trivial. My heart sank thinking about re-training face recognition for my entire family.

Then I remembered: I had set up automated face backups a few weeks ago.

## The Backup Architecture That Saved the Day

Back in January, after a close call with a Frigate upgrade, I implemented a simple but effective backup strategy:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Daily at 3am                                                           │
│                                                                         │
│  pumped-piglet (Proxmox host)          Frigate (K3s pod)               │
│  ┌─────────────────┐                   ┌─────────────────┐             │
│  │ cron job        │──── HTTPS ───────▶│ /api/faces      │             │
│  │ backup script   │                   │ face images     │             │
│  └────────┬────────┘                   └─────────────────┘             │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────┐                                                   │
│  │ /local-3TB-backup/frigate-backups/                                  │
│  │ └── frigate-faces-YYYYMMDD.tar.gz                                   │
│  └─────────────────┘                                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

The key design decisions:

1. **Separate physical storage**: Backups stored on pumped-piglet's 3TB ZFS pool, completely separate from the K3s node
2. **API-based extraction**: No kubectl required on the Proxmox host - uses Frigate's HTTP API
3. **Daily schedule**: Runs at 3am whether my Mac is on or not
4. **7-day retention**: Keeps a week of history with automatic cleanup

## The Recovery

When I checked pumped-piglet, the backups were there:

```
$ ls -lh /local-3TB-backup/frigate-backups/
-rw-r--r-- 1 root root 2.6M Feb  6 03:00 frigate-faces-20260206.tar.gz
-rw-r--r-- 1 root root 2.6M Feb  5 03:00 frigate-faces-20260205.tar.gz
-rw-r--r-- 1 root root 2.6M Feb  4 03:00 frigate-faces-20260204.tar.gz
...
```

The Feb 7 and 8 backups were tiny (116 bytes) because Frigate was already down. But Feb 6 had everything I needed.

After migrating Frigate to pumped-piglet with NVIDIA GPU acceleration, I restored the faces:

```bash
# Extract backup
tar xzf frigate-faces-20260206.tar.gz -C faces-restore --strip-components=1

# Copy to pod
kubectl cp faces-all.tar.gz frigate/${POD}:/tmp/
kubectl exec -n frigate ${POD} -- tar xzf /tmp/faces-all.tar.gz -C /media/frigate/clips/faces/

# Verify
$ curl -s https://frigate.app.home.panderosystems.com/api/faces | jq
{
  "Adil": 36,
  "Asha": 153,
  "G": 380,
  "Waffles": 11
}
```

All 580 training images restored. Face recognition was back online within minutes.

## Lessons Learned

### 1. Backup to Separate Physical Storage

If I had backed up to the same node running Frigate, I'd have lost both. The 3TB ZFS pool on pumped-piglet is dedicated to backups and survives individual node failures.

### 2. API-Based Backups Are Resilient

The backup script uses Frigate's HTTP API through Traefik. It doesn't care which K3s node runs Frigate - as long as the service is reachable, backups work.

### 3. Test Your Restore Procedure

I discovered during this incident that the Frigate API doesn't reliably accept bulk uploads. Direct file copy to the pod was the solution. I've updated my runbook with this finding.

### 4. Small Data, Big Value

The entire face training dataset is only 2.6MB compressed. But the hours spent collecting good training images? Priceless. Sometimes the smallest backups are the most valuable.

## The Backup Script

For those interested, here's the core of the backup script:

```bash
#!/bin/bash
BACKUP_DIR="/local-3TB-backup/frigate-backups"
FRIGATE_URL="https://frigate.app.home.panderosystems.com"
DATE=$(date +%Y%m%d)

# Get list of faces
faces=$(curl -sk "${FRIGATE_URL}/api/faces" | jq -r 'keys[]')

# Download each face's images
mkdir -p "/tmp/faces-${DATE}"
for face in $faces; do
    mkdir -p "/tmp/faces-${DATE}/${face}"
    images=$(curl -sk "${FRIGATE_URL}/api/faces" | jq -r ".${face}[]")
    for img in $images; do
        curl -sk "${FRIGATE_URL}/api/faces/${face}/${img}" \
            -o "/tmp/faces-${DATE}/${face}/${img}"
    done
done

# Create tarball
tar czf "${BACKUP_DIR}/frigate-faces-${DATE}.tar.gz" -C /tmp "faces-${DATE}"

# Cleanup old backups (keep 7 days)
find "${BACKUP_DIR}" -name "frigate-faces-*.tar.gz" -mtime +7 -delete
```

## Conclusion

This incident validated my backup strategy. When still-fawn went down, I lost:
- A K3s node (rebuilt on pumped-piglet)
- A VM disk (data recovered from PBS where needed)
- Face training images (restored from dedicated backup in minutes)

The migration even resulted in improvements:
- Coral TPU inference: 28ms → 12ms (USB 3.0 on pumped-piglet)
- GPU decode: AMD VAAPI → NVIDIA NVDEC
- CPU usage: 39% → running smoothly

Sometimes infrastructure failures lead to better architecture. And backups make the difference between a stressful weekend and a minor inconvenience.

---

**Related Posts**:
- [Frigate Migration to pumped-piglet](/docs/troubleshooting/action-log-frigate-016-pumped-piglet.md)
- [Coral TPU Integration Guide](/proxmox/guides/google-coral-tpu-frigate-integration.md)

**Runbook**: [Frigate Face Backup and Restore](/docs/runbooks/frigate-face-backup-restore.md)
