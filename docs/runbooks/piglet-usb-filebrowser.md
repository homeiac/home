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

Sidebar links are saved per user independently of source access. If a disk is
missing from Links, repair the admin sidebar without changing permissions:

```bash
bash scripts/filebrowser/fix-sidebar.sh 192.168.4.175 fix
```

This preserves custom links, backs up the profile on piglet, and adds any missing
SSK, RASPBMC, and BitLocker root links. Reload the browser afterward. The API
verification below also checks that all three sidebar links are present.

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

## Verify the EFS recovery certificate

The video `linuxfour_backup/iso_backup/vlc-record-2020-04-13-15h06m25s-MOVI0033.avi-.avi`
has NTFS EFS encryption in addition to BitLocker. Its file reads fail with EACCES
even as root, producing incomplete HTTP downloads. Its EFS certificate SHA-1
fingerprint is `6549B2CD28B2C0562ECFDD5A1A3B3E23A45C148C`.

The candidate PFX is at
`/mnt/filebrowser/SSK/cloud-backup/onedrive/Documents/encryption_key_certs_for_linuxfour_backup.pfx`.
Install and check the metadata reader, then run verification in a private terminal:

```bash
bash scripts/filebrowser/install-efs-verifier.sh 192.168.4.175
bash scripts/filebrowser/verify-efs-certificate.sh 192.168.4.175
bash scripts/filebrowser/check-efs-verification-result.sh 192.168.4.175
```

The hidden password prompt allows five attempts per run. The verifier loads the
private key only into process memory, compares its public key with the certificate,
and compares the certificate fingerprint with the video's EFS metadata. It does
not export the key, save the password, or decrypt/change the video. A
`verified_match` result confirms these checks; actual file recovery is a separate
step. The root-only result under `/run/filebrowser-efs-verification/` contains only
status, fingerprint, and verification booleans and disappears on reboot.

Metadata is read using `ntfscat`, which mounts read-only. Its force flag bypasses
the already-mounted exclusion; the helper first requires the underlying BitLocker
mapper to report block-level read-only. Existing FileBrowser mounts and backup
writers are untouched.

## Rollback

If the optional on-demand EFS view is active, stop LXC 104 before stopping
`filebrowser-efs.service`. To revert just EFS integration, change `mp2` back to
`/mnt/filebrowser/BitLocker,mp=/srv/files/BitLocker,ro=1,backup=0`, remove
`/etc/systemd/system/pve-container@104.service.d/efs-view.conf`, reload systemd,
disable/stop `filebrowser-efs.service`, and restart LXC 104. The original
BitLocker files remain encrypted and unchanged.

Remove `filebrowser-ingress.yaml` from the Traefik resources kustomization and
commit/push so Flux prunes the route. Stop `filebrowser-proxy.socket` and
`filebrowser-proxy.service`, then shut down LXC 104. Unmount the three
`/mnt/filebrowser/` paths and close `filebrowser-bitlocker` with cryptsetup.
Remove the FileBrowser bind-view lines from fstab; preserve the writable backup
mounts while the daily mirrors remain enabled. Compare against the saved backup
before restoration. Preserve LXC 104 until its application state
is no longer needed. None of these operations requires formatting a USB disk.

## On-demand EFS downloads (no persistent decrypted copies)

The optional host service `filebrowser-efs.service` runs `efs-view.py` through
Debian's `python3-fusepy`. It mounts a read-only view at
`/mnt/filebrowser/BitLocker-Decrypted`. LXC 104 binds that view read-only as its
existing `/srv/files/BitLocker` source; FileBrowser's URL and sidebar stay the
same. The original NTFS mount and underlying BitLocker mapper remain read-only.

Deployment and activation:

```bash
bash scripts/filebrowser/install-efs-view.sh 192.168.4.175
bash scripts/filebrowser/unlock-efs.sh 192.168.4.175
bash scripts/filebrowser/activate-efs-view.sh 192.168.4.175
bash scripts/filebrowser/verify-efs-download.sh 192.168.4.175
```

`unlock-efs.sh` must run in the user's own private terminal. It sends the password
over SSH to a root-only UNIX socket on piglet. The daemon verifies the PFX and
actually decrypts the sample video's AVI header before accepting it. The password
stays in process memory; it is never written to a file, environment variable,
command-line argument, or log. No private key is exported. A reboot or daemon
restart requires another EFS unlock. This is separate from BitLocker unlocking.

The adapter reads normal files directly. For encrypted files, it invokes the
dedicated `/usr/local/sbin/filebrowser-ntfsdecrypt` in read-only mode, supplies the password over a private
pipe, and streams its output. It keeps at most 1 MiB of recent decrypted bytes
per open file, with at most eight concurrent encrypted streams. No decrypted file
is materialized on disk. Forward seeks consume and discard preceding bytes;
backward seeks outside the buffer restart the decryptor. Large-file seeking and
repeat downloads can therefore be slower. Files encrypted with a different EFS
certificate still require their matching key.

After reboot, run `unlock-bitlocker.sh` first, then `unlock-efs.sh`. The BitLocker
helper preserves the on-demand view and refreshes the LXC bind mount. The EFS
service is ordered before LXC startup and waits until its FUSE mount is ready.
If the EFS daemon needs restarting, shut down LXC 104 first, restart the daemon,
then start LXC 104 so it gets the new mount. Unlock EFS again privately afterward.

`check-efs-view.sh` reports non-secret unlock status and mount flags.
`verify-efs-download.sh` checks a full authenticated HTTPS download against a
SHA-256 computed from the decrypted view, range reads, backward seeking, anonymous
access rejection, original EFS attributes, and kernel rejection of container
writes. Its data buffers are discarded; it does not save downloaded files.

### ntfsdecrypt certificate compatibility fix

The Debian 12 decryptor rejects valid EFS certificates because it truncates the
last character of the purpose OID returned by current GnuTLS. This was reproduced
on piglet using a synthetic EFS certificate. The maintainer's one-line fix is
documented in [ntfs-3g issue 87](https://github.com/tuxera/ntfs-3g/issues/87).

`build-ntfsdecrypt-fixed.sh` builds just the decryptor from the SHA-256-pinned
2022.10.3 source with that patch. Its libntfs code is statically linked; the distro
NTFS driver and shared libraries are not replaced. The build tree and GPL license
remain under `/root/ntfsdecrypt-build.*` on piglet. `diagnose-efs-reader.sh` tests
certificate parsing with a temporary synthetic PFX under `/run`, without reading
the user's PFX. The synthetic key is removed automatically.

Use `update-efs-view.sh` when updating an existing daemon: it backs up its files,
stops/restarts the LXC when needed to refresh the FUSE bind mount, and requires a
new private EFS unlock afterward. Status includes the last verification phase;
only PFX password failures prompt for another attempt. A later decryption failure
requires diagnosis rather than repeatedly entering the password.
