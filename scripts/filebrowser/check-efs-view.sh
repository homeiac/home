#!/usr/bin/env bash
# Report only non-secret status and read-only mount flags.
set -euo pipefail
ssh -o BatchMode=yes "root@${1:-pumped-piglet.maas}" 'bash -s' <<'REMOTE'
systemctl is-active filebrowser-efs
python3 /usr/local/sbin/filebrowser-efs-view.py status
findmnt -rn -M /mnt/filebrowser/BitLocker-Decrypted -o SOURCE,FSTYPE,OPTIONS
blockdev --getro /dev/mapper/filebrowser-bitlocker
pct config 104 | sed -n '/^mp/p'
python3 - <<'PY'
import errno,os
from pathlib import Path
root=Path('/mnt/filebrowser/BitLocker')
view=Path('/mnt/filebrowser/BitLocker-Decrypted')
assert sorted(os.listdir(root))==sorted(os.listdir(view))
print('View directory names match original.')
for item in root.iterdir():
    if item.is_file() and item.stat().st_size>0:
        if int.from_bytes(os.getxattr(item,'system.ntfs_attrib'),'little') & 0x4000: continue
        with item.open('rb') as original,(view/item.name).open('rb') as exposed:
            assert original.read(4096)==exposed.read(4096)
        print('Normal file bytes pass through unchanged.')
        break
try:
    fd=os.open(view/'.efs-readonly-probe',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
except OSError as error:
    assert error.errno==errno.EROFS
    print('Host view write rejected: EROFS')
else:
    os.close(fd); (view/'.efs-readonly-probe').unlink()
    raise AssertionError('Writable view')
PY
REMOTE
