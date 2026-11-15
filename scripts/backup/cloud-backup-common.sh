#!/bin/bash
# Shared settings for the cloud-backup scripts (Google Drive / OneDrive / Google Photos).
# Sourced by the other cloud-backup-*.sh scripts. Contains NO secrets.
# Design: docs/plans/cloud-drive-backup-and-reclaim.md
#
# Every value can be overridden from the environment, e.g.
#   CB_HOST=root@pumped-piglet.maas ./cloud-backup-measure.sh

# Proxmox host that runs rclone and holds the SSK disk
CB_HOST="${CB_HOST:-root@pumped-piglet.maas}"

# rclone release installed on the host (pinned; checksum-verified on install)
CB_RCLONE_VERSION="${CB_RCLONE_VERSION:-v1.76.0}"

# rclone config on the host. Holds OAuth tokens: never committed, never on the SMB share.
CB_RCLONE_CONF="${CB_RCLONE_CONF:-/root/.config/rclone/rclone.conf}"

# rclone remote names
CB_GDRIVE_REMOTE="${CB_GDRIVE_REMOTE:-gdrive-backup}"
CB_ONEDRIVE_REMOTE="${CB_ONEDRIVE_REMOTE:-onedrive}"
# OneDrive Personal Vault is locked and the Graph API cannot list it ("ObjectHandle is Invalid").
# Excluded from listings and backups; copy anything in it manually if needed.
CB_ONEDRIVE_EXCLUDE="${CB_ONEDRIVE_EXCLUDE:-/Personal Vault/**}"

# Where reports are written on the host
CB_REPORT_DIR="${CB_REPORT_DIR:-/var/lib/cloud-backup/reports}"

# SSK USB disk (secondary copy). Verified by serial before any destructive step.
CB_SSK_SERIAL="${CB_SSK_SERIAL:-DD56419883935}"
CB_SSK_LABEL="${CB_SSK_LABEL:-SSK}"

# SOPS-encrypted secret that already holds the Google Drive remote (used by postgres-gdrive-sync)
CB_GDRIVE_SOPS_SECRET="${CB_GDRIVE_SOPS_SECRET:-gitops/clusters/homelab/apps/postgres/rclone-secret.yaml}"

CB_SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)

# Run a command on the host
cb_ssh() { ssh "${CB_SSH_OPTS[@]}" "$CB_HOST" "$@"; }

# Repo root (scripts/backup/ -> repo)
CB_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# kubectl inside the K3s VM on the backup host (no kubeconfig needed on the workstation).
# Same mechanism as scripts/k3s/exec.sh: qm guest exec. Prints stdout+stderr, returns the exit code.
CB_K3S_VMID="${CB_K3S_VMID:-105}"
cb_kubectl() {
  local q; q="$(printf '%q ' "$@")"
  cb_ssh "qm guest exec $CB_K3S_VMID --timeout 120 -- bash -c $(printf '%q' "k3s kubectl $q")" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.stdout.write(d.get("out-data","")); sys.stderr.write(d.get("err-data","")); sys.exit(d.get("exitcode",1))'
}
