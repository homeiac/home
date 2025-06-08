#!/bin/bash
# uninstall_ceph.sh
# This script will uninstall Ceph from all Proxmox nodes.
# It kills Ceph-related processes, removes packages, and cleans configuration directories.
# Ensure you have passwordless SSH access to all nodes.

# List your Proxmox node hostnames with the .maas postfix
nodes=(pve.maas rapid-civet.maas still-fawn.maas chief-horse.maas)

for node in "${nodes[@]}"; do
  echo "---------- Processing node: $node ----------"

  ssh root@"$node" bash -s <<'EOF'
    set -e

    echo "[Ceph Uninstall] Killing Ceph-related processes..."
    # Kill Ceph monitor, OSD, MDS, and other related processes.
    pkill -f ceph-mon || true
    pkill -f ceph-osd || true
    pkill -f ceph-mds || true
    pkill -f ceph-mgr || true
    pkill -f ceph-fuse || true

    # Give the system a moment to settle
    sleep 3

    echo "[Ceph Uninstall] Removing Ceph packages..."
    apt-get update
    apt-get remove --purge -y ceph ceph-common ceph-mds ceph-mon ceph-osd ceph-fuse ceph-base || true

    echo "[Ceph Uninstall] Cleaning Ceph directories..."
    rm -rf /etc/ceph /var/lib/ceph /var/log/ceph || true

    # Verify Ceph is no longer running
    if pgrep -f ceph >/dev/null 2>&1; then
      echo "[Verification] ERROR: Some Ceph processes are still running."
    else
      echo "[Verification] Success: No Ceph processes detected."
    fi

    echo "[Ceph Uninstall] Uninstallation completed on $(hostname)"
EOF

  echo "---------- Finished processing $node ----------"
  echo ""
done

echo "Ceph uninstallation finished on all nodes."
