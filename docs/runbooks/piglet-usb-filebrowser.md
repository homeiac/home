# Piglet USB FileBrowser

FileBrowser Quantum **v2.0.2-stable** runs in unprivileged LXC **104** on
`pumped-piglet.maas`, with 1 CPU, 1 GiB RAM and an 8 GiB root volume on
`local-2TB-zfs`. Its binary SHA-256 is pinned in the deployment script.

Open **https://files.app.home.panderosystems.com** from the LAN or Tailscale.
Traefik uses the existing wildcard certificate and DNS. The Flux-managed
ExternalName service points to `pumped-piglet.maas:8088`. A systemd socket proxy
enters LXC 104's network namespace and connects to localhost:8080; it does not
depend on the container's DHCP address or require another DNS record. The proxy
drops to nobody after entering the namespace. No router forwarding is configured.

## Sources and protection

| Source | Stable partition identity | Host mount | Container mount |
| --- | --- | --- | --- |
| SSK | UUID EBFF-FC78 | /mnt/filebrowser/SSK | /srv/files/SSK |
| RASPBMC | UUID 1860-6D8F | /mnt/filebrowser/RASPBMC | /srv/files/RASPBMC |
| BitLocker | PARTUUID 00024711-01 | /mnt/filebrowser/BitLocker | /srv/files/BitLocker |

The existing daily cloud-backup jobs retain writable primary mounts at
`/mnt/ssk-cloud` and `/mnt/wd25-cloud`. FileBrowser receives separate host bind
views using `bind,ro,nosuid,nodev,noexec` in fstab. The LXC bind mounts additionally
use `ro=1`, and the service applies
`ReadOnlyPaths=/srv/files`. Source permissions disable create, modify and delete.
The BitLocker device-mapper mapping also uses `--readonly`; its NTFS filesystem
is mounted read-only using ntfs-3g. The USB ZFS backup pool is not a source.

Directory indexing is disabled to avoid scanning the entire USB disks. Browsing
and downloads work on demand. FFmpeg is not installed, so video transcoding and
FFmpeg-dependent previews are not enabled.

## Login

The username is `admin`. Run this privately to display the generated initial
password (the SSH argument can be omitted when `.maas` DNS works):

```bash
bash scripts/filebrowser/get-login.sh 192.168.4.175
```

The initial value is in LXC 104's root-only `/root/filebrowser-login.env`, outside
Git. Change it in the FileBrowser profile. The service's temporary bootstrap
environment file is removed after startup, so UI changes persist across restarts.
The initial-login file is not updated by a UI password change.

## Unlock BitLocker after a host reboot

```bash
bash scripts/filebrowser/unlock-bitlocker.sh 192.168.4.175
```

The password or recovery key is entered directly into cryptsetup's hidden SSH
terminal prompt. Five attempts are allowed per invocation; rerun after failure.
No key is saved. A successful unlock mounts NTFS read-only, configures `mp2`, and
restarts only FileBrowser's LXC so the bind mount sees the unlocked filesystem.
BitLocker remains locked after a host reboot until this command is run again.
Its source appears empty while locked. The exFAT mounts return automatically.

## Deploy and verify

```bash
bash scripts/filebrowser/deploy.sh 192.168.4.175
bash scripts/filebrowser/check-status.sh 192.168.4.175
bash scripts/filebrowser/verify-api.sh 192.168.4.175 https
```

The API check uses the bootstrap login file privately; after changing that
password, verify login in the browser instead. Status checks verify Proxmox
services and package consistency, mount flags, and kernel rejection of writes.
Deployment backs up host configuration under `/root/filebrowser-backups/`;
subsequent application updates also archive its stopped database and config
inside the LXC under `/root/filebrowser-backup-*.tgz`.

Debian 13's systemd requires `nesting=1` on this PVE 8 host for journald and mount
namespace support. The container remains unprivileged. Its startup unit requires
the two exFAT mount paths. A missing disk can prevent this LXC from starting,
while `nofail` prevents those USB mounts from blocking the host boot.

## Rollback

Remove `filebrowser-ingress.yaml` from the Traefik resources kustomization and
commit/push so Flux prunes the route. Stop `filebrowser-proxy.socket` and
`filebrowser-proxy.service`, then shut down LXC 104. Unmount the three
`/mnt/filebrowser/` paths and close `filebrowser-bitlocker` with cryptsetup.
Remove the FileBrowser bind-view lines from fstab; preserve the writable backup
mounts while the daily mirrors remain enabled. Compare against the saved backup
before restoration. Preserve LXC 104 until its application state
is no longer needed. None of these operations requires formatting a USB disk.
