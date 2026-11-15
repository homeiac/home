#!/bin/bash
# Restore the SOPS age key to this machine from any of its backups, and prove it works
#
# Usage (pick ONE source; see docs/runbooks/sops-age-key-recovery.md for which):
#   ./scripts/sops/restore-age-key.sh --from-file <sops-age-key.txt.age>  # cloud escrow download (asks passphrase)
#   ./scripts/sops/restore-age-key.sh --from-cluster                      # K8s secret flux-system/sops-age
#   ./scripts/sops/restore-age-key.sh --from-crucible                     # pve:/mnt/crucible-storage/secrets/sops/age.key
#   add --force to replace an existing, DIFFERENT key at the destination (old one is kept as .bak-<time>)
#
# Before installing, it checks the candidate key:
#   1. contains an AGE-SECRET-KEY
#   2. its public key is a recipient in .sops.yaml
#   3. it actually decrypts a committed *.sops.yaml file in this repo (output discarded)
# Then installs to ${SOPS_AGE_KEY_FILE:-~/.config/sops/age/keys.txt} with mode 0600.
# Idempotent: if the destination already holds the same key it says so and changes nothing.
#
# --from-cluster / --from-crucible need SSH to the Proxmox hosts (root@<host>), which needs this
# machine's SSH key in their authorized_keys. --from-file needs only the downloaded file + passphrase.
# Requires: age, sops (brew install age sops).

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly DEST="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
readonly K3S_HOST="${K3S_HOST:-root@192.168.4.175}"     # pumped-piglet (Proxmox host of K3s VM 105)
readonly K3S_VMID="${K3S_VMID:-105}"
readonly CRUCIBLE_HOST="${CRUCIBLE_HOST:-root@192.168.4.122}"  # pve
readonly CRUCIBLE_KEY=/mnt/crucible-storage/secrets/sops/age.key

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; }
die() { echo "ERROR: $*" >&2; exit 1; }

SRC="" FILE="" FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-file) SRC=file; FILE="${2:-}"; shift;;
    --from-cluster) SRC=cluster;;
    --from-crucible) SRC=crucible;;
    --force) FORCE=1;;
    -h|--help) usage; exit 0;;
    *) usage; die "unknown option: $1";;
  esac
  shift
done
[[ -n "$SRC" ]] || { usage; exit 1; }
for t in age age-keygen sops; do command -v "$t" >/dev/null || die "$t not installed (brew install age sops)"; done

TMP="$(mktemp -d)"; chmod 700 "$TMP"; trap 'rm -rf "$TMP"' EXIT
CAND="$TMP/keys.txt"
umask 077

case "$SRC" in
  file)
    [[ -f "$FILE" ]] || die "--from-file needs the downloaded sops-age-key.txt.age"
    head -c 64 "$FILE" | grep -q "age-encryption.org/v1" || die "$FILE is not an age-encrypted file"
    echo "Decrypting $FILE (type the escrow passphrase from your password manager):"
    age -d -o "$CAND" "$FILE"
    ;;
  cluster)
    echo "Reading K8s secret flux-system/sops-age via $K3S_HOST (VM $K3S_VMID)"
    ssh -o ConnectTimeout=10 "$K3S_HOST" \
      "qm guest exec $K3S_VMID --timeout 60 -- k3s kubectl -n flux-system get secret sops-age -o jsonpath='{.data.age\.agekey}'" \
      | python3 -c 'import json,sys,base64; d=json.load(sys.stdin); sys.stdout.write(base64.b64decode(d["out-data"]).decode())' > "$CAND"
    ;;
  crucible)
    echo "Reading $CRUCIBLE_HOST:$CRUCIBLE_KEY"
    ssh -o ConnectTimeout=10 "$CRUCIBLE_HOST" "cat $CRUCIBLE_KEY" > "$CAND"
    ;;
esac

# 1. looks like an age key
grep -q '^AGE-SECRET-KEY-1' "$CAND" || die "source did not contain an age secret key"
PUB="$(age-keygen -y "$CAND")"
echo "Candidate public key: $PUB"
# 2. matches the repo
grep -q "$PUB" "$REPO_ROOT/.sops.yaml" || die "this key is not a recipient in .sops.yaml - wrong key"
# 3. really decrypts a committed secret
# first committed encrypted secret (not the .sops.yaml config file itself)
TEST_FILE="$(cd "$REPO_ROOT" && git ls-files -- '*/*.sops.yaml' | while read -r f; do
  grep -q 'ENC\[AES256_GCM' "$f" && { echo "$f"; break; }; done)"
[[ -n "$TEST_FILE" ]] || die "no *.sops.yaml file in the repo to test with"
SOPS_AGE_KEY_FILE="$CAND" sops -d "$REPO_ROOT/$TEST_FILE" >/dev/null \
  || die "key failed to decrypt $TEST_FILE"
echo "Verified: decrypts $TEST_FILE"

# Install
mkdir -p "$(dirname "$DEST")"
if [[ -f "$DEST" ]]; then
  # compare the secret key itself (copies can differ only in their "# created" comment lines)
  if [[ "$(grep '^AGE-SECRET-KEY-1' "$CAND")" == "$(grep '^AGE-SECRET-KEY-1' "$DEST" 2>/dev/null)" ]]; then
    echo "Already installed at $DEST (same key) - nothing to do."; exit 0
  fi
  [[ $FORCE -eq 1 ]] || die "$DEST exists with a DIFFERENT key. Re-run with --force to replace it (a backup is kept)."
  cp -p "$DEST" "$DEST.bak-$(date +%Y%m%d-%H%M%S)"
  echo "Backed up the old key next to $DEST"
fi
install -m 600 "$CAND" "$DEST"
echo "Installed $DEST (0600)."
echo "sops finds it there by default; or: export SOPS_AGE_KEY_FILE=$DEST"
