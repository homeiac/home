#!/usr/bin/env bash
# Trigger a Job replacement when encrypted settings change. Hash ciphertext,
# never decrypted settings, so the public revision does not reveal inventory.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
bundle="$root/gitops/clusters/homelab/apps/photo-enrichment/immich-wifi"
shasum -a 256 "$bundle/network.sops.yaml" | cut -d ' ' -f 1 > "$bundle/network-revision"
