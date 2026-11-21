#!/usr/bin/env bash
# Read-only deployment prerequisites. SSH credentials come from the SSH agent.
set -euo pipefail
ssh -o BatchMode=yes -o ConnectTimeout=10 "root@${1:-pumped-piglet.maas}" 'bash -s' <<'REMOTE'
set -euo pipefail
echo '=== Storage, templates, next ID ==='
pvesm status
pvesm list local --content vztmpl
pvesh get /cluster/nextid
pvesh get /cluster/resources --type vm --output-format json
echo '=== Host networking and tools ==='
ip -brief address show vmbr0
cat /etc/resolv.conf
command -v cryptsetup || true
command -v ntfs-3g || true
getent hosts pumped-piglet.maas github.com
echo '=== Filesystems ==='
lsblk -o NAME,TRAN,FSTYPE,LABEL,UUID,PARTUUID,MOUNTPOINTS
echo '=== Cluster GitOps and ingress ==='
qm guest exec 105 -- /bin/sh -c 'kubectl get gitrepositories,kustomizations -n flux-system; kubectl get gitrepository flux-system -n flux-system -o jsonpath="{.spec.url}{\"\\n\"}{.spec.ref}{\"\\n\"}"; kubectl get ingress,ingressroute -A; kubectl get svc traefik -n kube-system; kubectl get secret -n kube-system -o custom-columns=NAME:.metadata.name,TYPE:.type'
REMOTE
