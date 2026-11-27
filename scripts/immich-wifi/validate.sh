#!/usr/bin/env bash
# Validate local manifests/scripts; optionally ask the API for a non-mutating
# server-side dry run. Run from any directory in this checkout.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
bundle="$ROOT/gitops/clusters/homelab/apps/photo-enrichment/immich-wifi"
expected=$(shasum -a 256 "$bundle/network.sops.yaml" | cut -d ' ' -f 1)
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
[[ $(cat "$bundle/network-revision") == "$expected" ]] || { echo 'Refresh the encrypted network revision'; exit 1; }
sops --decrypt "$bundle/network.sops.yaml" >/dev/null
for script in "$bundle"/*.sh "$ROOT/scripts/immich-wifi/"*.sh; do bash -n "$script"; done
sh -n "$bundle/deploy.sh"
kubectl kustomize "$bundle" >/dev/null
kubectl kustomize "$ROOT/gitops/clusters/homelab/apps/photo-enrichment" >/dev/null
git -C "$ROOT" diff --check
if [[ ${1:-} == --server ]]; then
  export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
  # Reproduce Flux's decryption step before Kubernetes schema validation.
  # The temporary plaintext inventory never enters Git or command output.
  umask 077
  decrypted=$(mktemp -d)
  trap 'rm -rf "$decrypted"' EXIT
  cp -R "$bundle/." "$decrypted/"
  sops --decrypt "$bundle/network.sops.yaml" > "$decrypted/network.sops.yaml"
  # Jobs are immutable in place; Flux replaces them. Use unused dry-run names
  # so schema validation also works after the real Job has completed.
  echo 'nameSuffix: -validation' >> "$decrypted/kustomization.yaml"
  kubectl --request-timeout=30s apply --dry-run=server -k "$decrypted"
  kubectl --request-timeout=30s apply --dry-run=server -f "$bundle/../immich-pilot/ingress.yaml"
fi
echo 'Validation passed.'
