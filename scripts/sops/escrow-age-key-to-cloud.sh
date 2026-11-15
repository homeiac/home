#!/bin/bash
# Store a passphrase-encrypted copy of the SOPS age key in Google Drive AND OneDrive (offsite escrow)
#
# Usage (interactive: you type a passphrase; inside Claude Code use `! <path>`):
#   ./scripts/sops/escrow-age-key-to-cloud.sh            # encrypt + upload + verify
#   ./scripts/sops/escrow-age-key-to-cloud.sh --verify   # read-only: both cloud copies present and identical
#
# Why: the age key decrypts every *.sops.yaml in this PUBLIC repo. Other copies (K8s secret
# flux-system/sops-age, Crucible on pve) are inside the homelab and need the laptop's SSH key to reach.
# This copy needs only a browser and the passphrase.
#
# What it uploads to <remote>:homelab-recovery/ on both $CB_GDRIVE_REMOTE and $CB_ONEDRIVE_REMOTE:
#   sops-age-key.txt.age   the key, encrypted with `age -p` (scrypt passphrase). Useless without it.
#   RECOVERY-README.txt    no secrets: what this is, public key, sha256, how to restore.
#
# Steps: encrypt ~/.config/sops/age/keys.txt -> decrypt it again (you type the passphrase a third
# time; proves you know it) -> upload via rclone on the backup host ($CB_HOST, streamed over SSH)
# -> download both copies back and compare sha256. The passphrase is never stored or logged.
# KEEP THE PASSPHRASE IN YOUR PASSWORD MANAGER. Without it this copy cannot be decrypted.
#
# Restore: scripts/sops/restore-age-key.sh --from-file <downloaded .age>
# Runbook: docs/runbooks/sops-age-key-recovery.md

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO_ROOT/scripts/backup/cloud-backup-common.sh"

readonly KEY="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
readonly DIR="homelab-recovery"
readonly NAME="sops-age-key.txt.age"
readonly REMOTES=("$CB_GDRIVE_REMOTE" "$CB_ONEDRIVE_REMOTE")

rcl() { cb_ssh "rclone --config '$CB_RCLONE_CONF' $*"; }
# sha256 of the remote copy; the empty-input hash if it is missing (rclone exits non-zero then)
remote_sha() { { rcl "cat '$1:$DIR/$NAME'" 2>/dev/null || true; } | shasum -a 256 | cut -d' ' -f1; }

verify() {
  local want="${1:-}" r sha first="" ok=1
  for r in "${REMOTES[@]}"; do
    sha="$(remote_sha "$r")"
    if [[ "$sha" == e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 ]]; then
      echo "  $r: MISSING $DIR/$NAME"; ok=0; continue
    fi
    echo "  $r: $DIR/$NAME sha256=${sha:0:16}…"
    [[ -z "$first" ]] && first="$sha"
    [[ "$sha" == "$first" ]] || { echo "  $r: DIFFERS from ${REMOTES[0]}"; ok=0; }
    [[ -z "$want" || "$sha" == "$want" ]] || { echo "  $r: DIFFERS from the file just uploaded"; ok=0; }
  done
  if [[ $ok -eq 1 ]]; then
    { rcl "cat '${REMOTES[0]}:$DIR/$NAME'" 2>/dev/null || true; } | head -c 64 | grep -q "age-encryption.org/v1" \
      || { echo "  not an age-encrypted file"; ok=0; }
  fi
  [[ $ok -eq 1 ]] && echo "OK: escrow present and identical in ${REMOTES[*]}" || { echo "ERROR: escrow incomplete"; return 1; }
}

if [[ "${1:-}" == "--verify" ]]; then verify; exit; fi
[[ -z "${1:-}" ]] || { sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

command -v age >/dev/null || { echo "ERROR: age not installed (brew install age)"; exit 1; }
[[ -t 0 ]] || { echo "ERROR: needs an interactive terminal for the passphrase"; exit 1; }
grep -q '^AGE-SECRET-KEY-1' "$KEY" || { echo "ERROR: $KEY has no age secret key"; exit 1; }
PUB="$(age-keygen -y "$KEY")"
grep -q "$PUB" "$REPO_ROOT/.sops.yaml" || { echo "ERROR: $KEY is not the key in .sops.yaml ($PUB)"; exit 1; }

TMP="$(mktemp -d)"; chmod 700 "$TMP"; trap 'rm -rf "$TMP"' EXIT
echo "Encrypting $KEY (public key $PUB)."
echo "Choose a strong passphrase and SAVE IT IN YOUR PASSWORD MANAGER now."
age -p -o "$TMP/$NAME" "$KEY"
echo
echo "Type the passphrase once more to prove the file decrypts:"
age -d "$TMP/$NAME" | cmp -s - "$KEY" || { echo "ERROR: decrypted copy does not match - nothing uploaded"; exit 1; }
SHA="$(shasum -a 256 "$TMP/$NAME" | cut -d' ' -f1)"
echo "Round-trip OK."

cat > "$TMP/RECOVERY-README.txt" <<TXT
Homelab SOPS age key - offsite escrow
=====================================
Created: $(date -u +%Y-%m-%dT%H:%M:%SZ)
File:    $NAME   (age passphrase-encrypted; contains the private key)
sha256:  $SHA
Public key (must match .sops.yaml in the repo): $PUB

The same file is stored in Google Drive and OneDrive under $DIR/.
The passphrase is in the owner's password manager. Without it this file is useless.

To restore on a new machine:
  1. git clone https://github.com/homeiac/home && cd home
  2. brew install age sops        (or your OS's packages)
  3. Download $NAME from this folder (browser is fine)
  4. ./scripts/sops/restore-age-key.sh --from-file ~/Downloads/$NAME
Full runbook: docs/runbooks/sops-age-key-recovery.md in the repo.
TXT

for r in "${REMOTES[@]}"; do
  echo "Uploading to $r:$DIR/"
  rcl "rcat '$r:$DIR/$NAME'" < "$TMP/$NAME"
  rcl "rcat '$r:$DIR/RECOVERY-README.txt'" < "$TMP/RECOVERY-README.txt"
done
echo "Verifying uploads"
verify "$SHA"
