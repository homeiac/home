#!/usr/bin/env bash
# Provision an unprivileged FileBrowser LXC and read-only USB mounts on piglet.
# Run via deploy.sh; never formats disks or stores BitLocker keys.
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
[[ $(hostname -s) == pumped-piglet && $EUID == 0 ]] || exit 1
ct=104
if [[ -f /etc/pve/lxc/$ct.conf ]]; then
    grep -q '^hostname: filebrowser$' /etc/pve/lxc/$ct.conf || exit 1
elif [[ $(pvesh get /cluster/nextid --vmid "$ct") != "$ct" ]]; then
    echo 'Container ID 104 is already occupied.' >&2; exit 1
fi
for uuid in EBFF-FC78 1860-6D8F; do
    [[ $(blkid -s TYPE -o value "/dev/disk/by-uuid/$uuid") == exfat ]] || exit 1
    if findmnt -rn -S "/dev/disk/by-uuid/$uuid" -o OPTIONS | grep -Eq '(^|,)rw(,|$)'; then
        echo "Refusing to reuse a writable mount for $uuid" >&2; exit 1
    fi
done
backup_dir=/root/filebrowser-backups/$(date +%Y%m%dT%H%M%S)
install -d -m 700 "$backup_dir"
cp /etc/fstab "$backup_dir/fstab"
[[ ! -f /etc/pve/lxc/$ct.conf ]] || cp /etc/pve/lxc/$ct.conf "$backup_dir/104.conf"
for existing in /etc/systemd/system/filebrowser-proxy.{socket,service}; do
    [[ ! -f $existing ]] || cp "$existing" "$backup_dir/"
done
echo "Configuration backup: $backup_dir"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends cryptsetup-bin ntfs-3g ca-certificates curl
install -m 700 "$SCRIPT_DIR/unlock-bitlocker-host.sh" /usr/local/sbin/filebrowser-unlock-bitlocker
for entry in EBFF-FC78:SSK 1860-6D8F:RASPBMC; do
    uuid=${entry%%:*}; label=${entry#*:}; target=/mnt/filebrowser/$label
    mkdir -p "$target"
    if ! grep -Fq "UUID=$uuid " /etc/fstab; then
        printf 'UUID=%s %s exfat ro,nosuid,nodev,noexec,nofail,x-systemd.device-timeout=10s,uid=100000,gid=100000,fmask=0133,dmask=0022 0 0\n' "$uuid" "$target" >> /etc/fstab
    fi
    mountpoint -q "$target" || mount "$target"
    [[ $(findmnt -rn -M "$target" -o UUID) == "$uuid" ]]
    findmnt -rn -M "$target" -o OPTIONS | grep -Eq '(^|,)ro(,|$)'
done
systemctl daemon-reload
if [[ ! -f /etc/pve/lxc/$ct.conf ]]; then
    pct create "$ct" local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst \
        --hostname filebrowser --unprivileged 1 --features nesting=1 --cores 1 --memory 1024 --swap 256 \
        --rootfs local-2TB-zfs:8 --net0 name=eth0,bridge=vmbr0,ip=dhcp,ip6=manual \
        --onboot 1 --startup order=40 --tags filebrowser \
        --mp0 /mnt/filebrowser/SSK,mp=/srv/files/SSK,ro=1,backup=0 \
        --mp1 /mnt/filebrowser/RASPBMC,mp=/srv/files/RASPBMC,ro=1,backup=0
fi
# Debian 13 systemd requires nested mount namespaces for credentials/journald on PVE 8.
if ! pct config "$ct" | grep -q '^features: .*nesting=1'; then
    pct set "$ct" --features nesting=1
    if pct status "$ct" | grep -q running; then pct shutdown "$ct" --timeout 30; fi
fi
# Mounts must be present before LXC binds them at boot. A missing drive may fail
# this container's start, but nofail means it cannot block the Proxmox host boot.
install -d /etc/systemd/system/pve-container@104.service.d
cat > /etc/systemd/system/pve-container@104.service.d/filebrowser-mounts.conf <<'UNIT'
[Unit]
RequiresMountsFor=/mnt/filebrowser/SSK /mnt/filebrowser/RASPBMC
UNIT
systemctl daemon-reload
pct status "$ct" | grep -q running || pct start "$ct"
for attempt in {1..30}; do
    if pct exec "$ct" -- test -d /run/systemd/system; then break; fi
    sleep 2
done
binary="$SCRIPT_DIR/linux-amd64-filebrowser"
curl -fL --retry 3 -o "$binary" https://github.com/gtsteffaniak/filebrowser/releases/download/v2.0.2-stable/linux-amd64-filebrowser
echo "5710dc6f51d77f1db884eace44f6952286c49f2ce40b6a59af37e0dc7c4a8bbd  $binary" | sha256sum -c -
pct exec "$ct" -- bash -c 'id filebrowser >/dev/null 2>&1 || useradd --system --home /var/lib/filebrowser --shell /usr/sbin/nologin filebrowser; install -d /etc/filebrowser /srv/files/BitLocker; install -d -o filebrowser -g filebrowser -m 700 /var/lib/filebrowser'
pct exec "$ct" -- bash -c 'systemctl stop filebrowser 2>/dev/null || true; if [[ -f /etc/filebrowser/config.yaml ]]; then umask 077; tar -czf "/root/filebrowser-backup-$(date +%Y%m%dT%H%M%S).tgz" /etc/filebrowser /var/lib/filebrowser; fi'
pct push "$ct" "$binary" /usr/local/bin/filebrowser --perms 0755
pct push "$ct" "$SCRIPT_DIR/config.yaml" /etc/filebrowser/config.yaml --perms 0644
pct push "$ct" "$SCRIPT_DIR/filebrowser.service" /etc/systemd/system/filebrowser.service --perms 0644
# Bootstrap credential stays in root-only files, outside Git and tool output.
pct exec "$ct" -- bash -c 'if [[ ! -f /var/lib/filebrowser/database.sqlite ]]; then umask 077; printf "FILEBROWSER_ADMIN_PASSWORD=%s\n" "$(head -c 24 /dev/urandom | base64)" > /root/filebrowser-login.env; cp /root/filebrowser-login.env /etc/filebrowser/bootstrap.env; fi; systemctl daemon-reload; systemctl enable filebrowser; systemctl restart filebrowser'
install -m 755 "$SCRIPT_DIR/proxy-container.sh" /usr/local/sbin/filebrowser-proxy-container
install -m 644 "$SCRIPT_DIR/filebrowser-proxy.socket" /etc/systemd/system/filebrowser-proxy.socket
install -m 644 "$SCRIPT_DIR/filebrowser-proxy.service" /etc/systemd/system/filebrowser-proxy.service
systemctl daemon-reload
systemctl enable --now filebrowser-proxy.socket
for attempt in {1..30}; do
    if curl -fsS --max-time 3 http://localhost:8088/ -o /dev/null; then
        # Let future UI password changes persist across restarts.
        pct exec "$ct" -- rm -f /etc/filebrowser/bootstrap.env
        echo 'FileBrowser is responding. Initial login is in LXC /root/filebrowser-login.env.'
        exit 0
    fi
    sleep 2
done
echo 'FileBrowser did not become healthy; inspect service logs privately.' >&2
exit 1
