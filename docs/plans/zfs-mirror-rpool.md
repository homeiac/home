# ZFS Mirror rpool - still-fawn

## Context

still-fawn's boot SSD failed in January 2026. Replaced with a T-FORCE 2TB.
A second identical 2TB drive was added to create a ZFS mirror (RAID 1) for
rpool so the next drive failure doesn't require a reinstall.

## Current State

| Drive | Serial / disk-by-id | Role |
|-------|---------------------|------|
| sdb | `ata-T-FORCE_2TB_TPBF2211070040100214` | rpool (single vdev), ~209G used / 1.86T |
| sda | `ata-T-FORCE_2TB_TPBF2509220070101290` | New, unpartitioned |

## What the Script Does (5 idempotent steps)

1. **Clone partition table** - `sgdisk -R` copies BIOS boot, EFI, ZFS partitions
2. **Randomize GUIDs** - `sgdisk -G` so both disks have unique identifiers
3. **Configure boot** - `proxmox-boot-tool format/init` on new disk's ESP
4. **Attach mirror** - `zpool attach rpool <existing-part3> <new-part3>`
5. **Verify resilver** - Parse `zpool status` for progress/completion

## Execution

```bash
cd proxmox/homelab

# 1. Dry run first (no changes, shows what would happen)
poetry run homelab storage mirror apply --host still-fawn --dry-run

# 2. Apply (each step is idempotent - safe to re-run)
poetry run homelab storage mirror apply --host still-fawn

# 3. Monitor resilver
poetry run homelab storage mirror status --host still-fawn

# 4. Direct SSH check
ssh root@still-fawn.maas "zpool status rpool"
```

## Pre-flight Checks (auto-run before apply)

- Pool exists and ONLINE
- Both disks present at `/dev/disk/by-id/`
- New disk not in any pool
- Disk sizes match
- `sgdisk`, `proxmox-boot-tool`, `zpool` available
- Pool not resilvering/scrubbing

## Post-Apply Verification

After resilver completes, confirm:

```bash
# Mirror topology
ssh root@still-fawn.maas "zpool status rpool"
# Should show mirror-0 with both disks

# Boot redundancy
ssh root@still-fawn.maas "proxmox-boot-tool status"
# Should list both ESPs

# Test boot from either disk
# (requires physical intervention - pull one drive, verify boot)
```

## Configuration

Defined in `proxmox/homelab/config/cluster.yaml` under the still-fawn node:

```yaml
zfs_mirrors:
  - pool: rpool
    existing_disk: "ata-T-FORCE_2TB_TPBF2211070040100214"
    new_disk: "ata-T-FORCE_2TB_TPBF2509220070101290"
    zfs_partition: 3
    efi_partition: 2
    bios_boot_partition: 1
```

## Rollback

If something goes wrong mid-apply:
- Steps 1-3 don't touch the existing pool data
- Step 4 (attach) can be reversed: `zpool detach rpool <new-part3>`
- The existing single-disk rpool remains functional throughout
