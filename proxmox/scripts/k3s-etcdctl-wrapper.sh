#!/bin/bash
# k3s-etcdctl - Wrapper for etcdctl with K3s TLS configuration
#
# Installation:
#   sudo cp k3s-etcdctl-wrapper.sh /usr/local/bin/k3s-etcdctl
#   sudo chmod +x /usr/local/bin/k3s-etcdctl
#
# Usage:
#   k3s-etcdctl member list -w table
#   k3s-etcdctl endpoint health
#   k3s-etcdctl member remove <MEMBER_ID>

set -e

# Check if running on K3s master node
if [ ! -f /var/lib/rancher/k3s/server/tls/etcd/server-ca.crt ]; then
    echo "Error: K3s etcd TLS certificates not found." >&2
    echo "This script must be run on a K3s master node." >&2
    exit 1
fi

# Check if etcdctl is installed
if ! command -v etcdctl &> /dev/null; then
    echo "Error: etcdctl not found in PATH." >&2
    echo "Install with:" >&2
    echo "  cd /tmp" >&2
    echo "  wget -q https://github.com/etcd-io/etcd/releases/download/v3.5.12/etcd-v3.5.12-linux-amd64.tar.gz" >&2
    echo "  tar xzf etcd-v3.5.12-linux-amd64.tar.gz" >&2
    echo "  sudo mv etcd-v3.5.12-linux-amd64/etcdctl /usr/local/bin/" >&2
    exit 1
fi

# Set K3s etcd TLS environment variables
export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key

# Execute etcdctl with K3s local endpoint
exec etcdctl --endpoints=https://127.0.0.1:2379 "$@"
