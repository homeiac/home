# Using Oxide Crucible as a Secrets Backup for Your Homelab

**Date**: January 26, 2026
**Author**: Claude + Human collaboration
**Tags**: oxide, crucible, secrets, backup, homelab, sops, ssh, configuration

---

## The Problem: Where Do You Put the Stuff That Can't Go in Git?

Every homelab has secrets that can't be checked into version control:

- SOPS age keys (the key that decrypts your other keys)
- SSH private keys
- `.env` files with API tokens and passwords
- Home Assistant `secrets.yaml`
- Database credentials
- Certificate private keys

These files are critical. Lose them and you're locked out of your own infrastructure. But where do you store them safely?

Cloud storage? Now your secrets depend on someone else's infrastructure. Local backup drive? Single point of failure. Password manager? Doesn't handle files well.

## The Solution: Distributed Storage You Control

I already had [Oxide Crucible running on a $30 mini PC](/docs/blog/2026-01-25-budget-oxide-storage-sled.md) for VM storage experiments. Then it hit me: Crucible provides 12.5GB of distributed block storage to each of my 5 Proxmox hosts. That's plenty of space for configs and secrets.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Secrets Backup Architecture                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Mac (source of truth)                                          │
│   ~/.config/sops/age/keys.txt ─────┐                            │
│   ~/.ssh/id_ed25519_pve ───────────┼──► sync-secrets-to-crucible│
│   ~/code/home/.env ────────────────┘           │                │
│                                                │                │
│                                                ▼                │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              pve:/mnt/crucible-storage/                 │   │
│   │  secrets/                                               │   │
│   │  ├── sops/age.key                                       │   │
│   │  ├── ssh/id_ed25519_pve                                 │   │
│   │  └── env/homelab.env                                    │   │
│   │  services/                                              │   │
│   │  └── haos/20260126-231325/                              │   │
│   │      ├── configuration.yaml                             │   │
│   │      ├── automations.yaml                               │   │
│   │      └── secrets.yaml                                   │   │
│   └─────────────────────────────────────────────────────────┘   │
│                          │                                       │
│                          │ replicate-crucible-storage            │
│                          ▼                                       │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│   │still-fawn│ │pumped-   │ │chief-    │ │fun-      │          │
│   │  /mnt/   │ │piglet    │ │horse     │ │bedbug    │          │
│   │crucible- │ │  /mnt/   │ │  /mnt/   │ │  /mnt/   │          │
│   │storage/  │ │crucible- │ │crucible- │ │crucible- │          │
│   │          │ │storage/  │ │storage/  │ │storage/  │          │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│         │            │            │            │                 │
│         └────────────┴─────┬──────┴────────────┘                │
│                            │                                     │
│                            ▼                                     │
│              ┌─────────────────────────┐                        │
│              │    proper-raptor        │                        │
│              │    (Crucible storage)   │                        │
│              │    192.168.4.189        │                        │
│              └─────────────────────────┘                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## What Gets Backed Up

### Local Secrets (from Mac)

```bash
./scripts/crucible/sync-secrets-to-crucible.sh
```

| File | Purpose |
|------|---------|
| `~/.config/sops/age/keys.txt` | SOPS decryption key |
| `~/.ssh/id_ed25519_pve` | Proxmox SSH key |
| `~/code/home/.env` | Homelab credentials |

### Service Configs (from VMs/containers)

```bash
./scripts/crucible/backup-services-to-crucible.sh
```

| Service | Files Backed Up |
|---------|-----------------|
| Home Assistant | `configuration.yaml`, `automations.yaml`, `secrets.yaml`, `core.config_entries` |
| Frigate | `config.yml`, model list |
| Ollama | Model list, model details |

### Proxmox Host Configs

```bash
./scripts/crucible/backup-configs-to-crucible.sh
```

| Config | Purpose |
|--------|---------|
| `/etc/pve/*` | Cluster config, VM/LXC definitions, storage.cfg |
| `/etc/network/interfaces` | Network configuration |
| `/etc/systemd/system/crucible-*` | Crucible service definitions |
| ZFS pool/dataset lists | Storage topology |

## Replication: 5 Copies of Everything

The magic happens with replication. After backing up to pve, one command copies everything to all other hosts:

```bash
./scripts/crucible/replicate-crucible-storage.sh
```

```
[23:16:40] Starting Crucible storage replication
[23:16:40] Primary: pve
[23:16:40] Replicas: still-fawn.maas pumped-piglet.maas chief-horse.maas fun-bedbug.maas

=== still-fawn.maas ===
[23:16:41] Syncing secrets to still-fawn.maas...
[23:16:42] Syncing services to still-fawn.maas...

=== pumped-piglet.maas ===
[23:16:43] Syncing secrets to pumped-piglet.maas...
...

[23:16:48] Storage contents:
--- pve ---
44K    /mnt/crucible-storage/secrets/
104K   /mnt/crucible-storage/services/
--- still-fawn.maas ---
44K    /mnt/crucible-storage/secrets/
104K   /mnt/crucible-storage/services/
...
```

Now the same secrets exist on all 5 Proxmox hosts. If one host dies, four others have copies.

## The Scripts

All scripts are idempotent - safe to run repeatedly.

### sync-secrets-to-crucible.sh

```bash
#!/bin/bash
# Syncs local secrets from Mac to Crucible storage

LOCAL_SECRETS=(
    "sops/age.key:$HOME/.config/sops/age/keys.txt"
    "ssh/id_ed25519_pve:$HOME/.ssh/id_ed25519_pve"
    "env/homelab.env:$REPO_ROOT/proxmox/homelab/.env"
)

for pair in "${LOCAL_SECRETS[@]}"; do
    dest_path="${pair%%:*}"
    src_path="${pair#*:}"
    scp "$src_path" "root@pve:/mnt/crucible-storage/secrets/$dest_path"
done
```

### backup-services-to-crucible.sh

Uses `qm guest exec` to pull configs from HAOS VM:

```bash
# HAOS config lives at /mnt/data/supervisor/homeassistant/
ssh "root@chief-horse.maas" "
    qm guest exec 116 -- cat '$ha_config/configuration.yaml' | \
        jq -r '.[\"out-data\"]' > '$dest_dir/configuration.yaml'
    qm guest exec 116 -- cat '$ha_config/secrets.yaml' | \
        jq -r '.[\"out-data\"]' > '$dest_dir/secrets.yaml'
"
```

### replicate-crucible-storage.sh

Uses tar pipe through local machine (avoids SSH host key issues between Proxmox hosts):

```bash
for replica in "${REPLICA_HOSTS[@]}"; do
    ssh "root@$PRIMARY_HOST" "tar -C '$src' -cf - ." | \
        ssh "root@$replica" "tar -C '$dest' -xf -"
done
```

## Why This Works

1. **No cloud dependency** - Everything stays on your network
2. **Distributed** - 5 copies across 5 hosts
3. **Fast recovery** - Secrets are already on every Proxmox host
4. **Git-friendly** - Scripts are version controlled, secrets aren't
5. **Cheap** - Uses existing Crucible storage (costs $0 extra)

## Recovery Scenarios

### Lost my Mac

SSH to any Proxmox host, secrets are at `/mnt/crucible-storage/secrets/`:

```bash
ssh root@pve
cat /mnt/crucible-storage/secrets/sops/age.key
cat /mnt/crucible-storage/secrets/ssh/id_ed25519_pve
```

### Proxmox host died

Four other hosts have identical copies. Pick one.

### proper-raptor (Crucible storage) died

This is the single point of failure today. The `/mnt/crucible-storage` would become unavailable. But! The last-synced data still exists on each host's local mount until you disconnect NBD.

**Future improvement**: Add 2 more MA90 sleds (~$60) for true 3-way Crucible replication. Then even the storage backend survives hardware failure.

### Home Assistant config corrupted

Restore from timestamped backup:

```bash
ls /mnt/crucible-storage/services/haos/
# 20260125-231325/  20260126-080000/  ...

cat /mnt/crucible-storage/services/haos/20260125-231325/configuration.yaml
```

## Automation Ideas

Add to cron for automatic backups:

```bash
# Daily secrets sync (2 AM)
0 2 * * * /home/user/code/home/scripts/crucible/sync-secrets-to-crucible.sh

# Daily service backup (3 AM)
0 3 * * * /home/user/code/home/scripts/crucible/backup-services-to-crucible.sh

# Daily replication (4 AM)
0 4 * * * /home/user/code/home/scripts/crucible/replicate-crucible-storage.sh
```

Or trigger on git push with a hook.

## Total Cost

| Item | Cost |
|------|------|
| MA90 mini PC (Crucible storage) | $30 |
| USB 2.5GbE adapters (5x) | $75 |
| 2.5GbE switch | $60 |
| **Total** | **$165** |

For that, you get distributed secrets storage across 5 hosts with 12.5GB per host. Not bad for a homelab.

## Conclusion

Crucible wasn't designed for secrets backup. It's enterprise distributed block storage for VMs. But the primitives it provides - replicated storage accessible from multiple hosts - solve the secrets problem elegantly.

Sometimes the best tool for a job is the one you already have running.

---

**Related posts:**
- [Budget Oxide Storage Sled](/docs/blog/2026-01-25-budget-oxide-storage-sled.md)

**Scripts:**
- [scripts/crucible/sync-secrets-to-crucible.sh](/scripts/crucible/sync-secrets-to-crucible.sh)
- [scripts/crucible/backup-services-to-crucible.sh](/scripts/crucible/backup-services-to-crucible.sh)
- [scripts/crucible/backup-configs-to-crucible.sh](/scripts/crucible/backup-configs-to-crucible.sh)
- [scripts/crucible/replicate-crucible-storage.sh](/scripts/crucible/replicate-crucible-storage.sh)
