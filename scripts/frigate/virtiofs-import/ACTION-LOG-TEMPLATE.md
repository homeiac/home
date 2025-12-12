# Action Log: VirtioFS Import Setup

## Execution Date: [DATE]

## Pre-flight Checks
- [ ] Proxmox version >= 8.4: `ssh root@pumped-piglet.maas pveversion`
- [ ] K3s cluster healthy (3 nodes Ready): `kubectl get nodes`
- [ ] Source data exists: `ssh root@pumped-piglet.maas "du -sh /local-3TB-backup/subvol-113-disk-0/frigate/"`

---

## Step 1: Create ZFS Dataset
- **Script**: `./01-create-zfs-dataset.sh`
- **Status**: [PENDING/SUCCESS/FAILED]
- **Output**:
```
[paste output here]
```

---

## Step 2: Copy Recordings
- **Script**: `./02-copy-recordings.sh`
- **Status**: [PENDING/SUCCESS/FAILED]
- **Duration**: [X minutes]
- **Output**:
```
[paste output here]
```

---

## Step 3: Create Directory Mapping
- **Script**: `./03-create-directory-mapping.sh`
- **Status**: [PENDING/SUCCESS/FAILED]
- **Output**:
```
[paste output here]
```

---

## Step 4: Attach VirtioFS to VM
- **Script**: `./04-attach-virtiofs-to-vm.sh`
- **Status**: [PENDING/SUCCESS/FAILED]
- **VM downtime**: [X seconds]
- **K3s rejoin time**: [X seconds]
- **Output**:
```
[paste output here]
```

---

## Step 5: Mount in VM
- **Script**: `./05-mount-in-vm.sh`
- **Status**: [PENDING/SUCCESS/FAILED]
- **Output**:
```
[paste output here]
```

---

## Step 6: Verify Frigate Access
- **Script**: `./06-verify-frigate-access.sh`
- **Status**: [PENDING/SUCCESS/FAILED]
- **Old recordings visible**: [YES/NO]
- **K3s cluster stable**: [YES/NO]
- **Output**:
```
[paste output here]
```

---

## Final Status
- **Overall**: [SUCCESS/PARTIAL/FAILED]
- **Notes**:

---

## Rollback (if needed)
- **Script**: `./99-rollback.sh`
- **Executed**: [YES/NO]
- **Reason**:

---

## References
- [Proxmox 8.4 VirtioFS Tutorial](https://forum.proxmox.com/threads/proxmox-8-4-virtiofs-virtiofs-shared-host-folder-for-linux-and-or-windows-guest-vms.167435/)
- [VirtioFS vs 9p Performance](https://www.phoronix.com/news/Linux-5.4-VirtIO-FS)
- Plan: `/Users/10381054/.claude/plans/wiggly-percolating-sunrise.md`
