#!/usr/bin/env bash
# Build only ntfsdecrypt with upstream issue #87's certificate OID fix.
# Do not replace the distro's NTFS driver or install a new libntfs shared library.
set -euo pipefail
host=${1:-pumped-piglet.maas}
ssh -o BatchMode=yes "root@$host" 'bash -s' <<'REMOTE'
set -euo pipefail
[[ $(hostname -s) == pumped-piglet && $EUID == 0 ]]
directory=$(mktemp -d /root/ntfsdecrypt-build.XXXXXX)
cd "$directory"
curl -fsSL https://codeload.github.com/tuxera/ntfs-3g/tar.gz/refs/tags/2022.10.3 -o source.tar.gz
echo '8bd7749ea9d8534c9f0664d48b576e90b96d45ec8803c9427f6ffaa2f0dde299  source.tar.gz' | sha256sum -c -
tar -xzf source.tar.gz
cd ntfs-3g-2022.10.3
python3 - <<'PY'
from pathlib import Path
p=Path('ntfsprogs/ntfsdecrypt.c')
text=p.read_text()
old='purpose_oid[purpose_oid_size - 1]'
assert text.count(old)==1
p.write_text(text.replace(old,'purpose_oid[sizeof(purpose_oid) - 1]'))
PY
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gcc make pkg-config autoconf automake libtool libgcrypt20-dev libgnutls28-dev
./autogen.sh > "$directory/build.log" 2>&1
./configure --disable-ntfs-3g --enable-crypto --disable-shared --enable-static >> "$directory/build.log" 2>&1
make -j2 -C libntfs-3g >> "$directory/build.log" 2>&1
make -j2 -C ntfsprogs ntfsdecrypt >> "$directory/build.log" 2>&1
install -d -m 700 /root/filebrowser-backups
if [[ -f /usr/local/sbin/filebrowser-ntfsdecrypt ]]; then
    cp /usr/local/sbin/filebrowser-ntfsdecrypt "/root/filebrowser-backups/ntfsdecrypt-$(date +%Y%m%dT%H%M%S)"
fi
install -m 700 ntfsprogs/ntfsdecrypt /usr/local/sbin/filebrowser-ntfsdecrypt
ldd /usr/local/sbin/filebrowser-ntfsdecrypt
echo "Corrected helper installed; source, GPL license, and build log retained in $directory"
REMOTE
