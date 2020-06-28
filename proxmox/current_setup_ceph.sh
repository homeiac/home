#!/bin/bash
set -e  # Exit on errors

CEPH_POOL="k3s-pool"
CEPH_VERSION="quincy"  # Change to "reef" if needed

# Get the list of Proxmox nodes
PROXMOX_NODES=$(pvesh get /nodes --output-format json | jq -r '.[].node')

# ---------------------------- Section 1: Install Ceph & Required Tools ----------------------------
install_ceph() {
    echo "🚀 Installing Ceph and required tools on all Proxmox nodes..."
    for node in $PROXMOX_NODES; do
        NODE_FQDN="${node}.maas"
        echo "🔹 Installing Ceph on $NODE_FQDN"
        ssh root@$NODE_FQDN "apt update -y && apt install -y ceph ceph-common ceph-fuse jq lvm2"
    done
}

# ---------------------------- Section 2: Ensure Bootstrap Key Exists ----------------------------
setup_bootstrap_key() {
    echo "🚀 Ensuring bootstrap key exists..."
    if [[ ! -f /var/lib/ceph/bootstrap-osd/ceph.keyring ]]; then
        echo "🔹 Creating missing bootstrap key on pve..."
        ceph auth get client.bootstrap-osd -o /var/lib/ceph/bootstrap-osd/ceph.keyring
        chown ceph:ceph /var/lib/ceph/bootstrap-osd/ceph.keyring
        chmod 600 /var/lib/ceph/bootstrap-osd/ceph.keyring
    fi

    echo "🔹 Copying bootstrap key to all nodes..."
    for node in $PROXMOX_NODES; do
        NODE_FQDN="${node}.maas"
        scp /var/lib/ceph/bootstrap-osd/ceph.keyring root@$NODE_FQDN:/var/lib/ceph/bootstrap-osd/ceph.keyring
        ssh root@$NODE_FQDN "chown ceph:ceph /var/lib/ceph/bootstrap-osd/ceph.keyring && chmod 600 /var/lib/ceph/bootstrap-osd/ceph.keyring"
    done
}

# ---------------------------- Section 3: Ensure MONs Exist ----------------------------
setup_monitors() {
    echo "🚀 Configuring Ceph MONs..."

    for node in $PROXMOX_NODES; do
        NODE_FQDN="${node}.maas"
        NODE_IP=$(ssh root@$NODE_FQDN "hostname -I | awk '{print \$1}'")

        echo "🔹 Checking for existing MON on $NODE_FQDN..."
        if ssh root@$NODE_FQDN "ceph mon dump | grep -q $NODE_IP"; then
            echo "✅ MON already exists on $NODE_FQDN, skipping creation."
        else
            echo "🔹 Creating MON on $NODE_FQDN using IP $NODE_IP..."
            ssh root@$NODE_FQDN "pveceph createmon"
        fi
    done
}

# ---------------------------- Section 4: Ensure ZFS Block Devices Exist ----------------------------
setup_zfs_block_device() {
    echo "🚀 Ensuring ZFS block devices exist..."

    for node in $PROXMOX_NODES; do
        if [[ "$node" == "pve" ]]; then
            NODE_FQDN="pve"  # No .maas for pve
            VG_NAME="rpool/data"
        elif [[ "$node" == "chief-horse" ]]; then
            NODE_FQDN="chief-horse.maas"
            VG_NAME="local-256-gb-zfs"
        elif [[ "$node" == "still-fawn" ]]; then
            NODE_FQDN="still-fawn.maas"
            VG_NAME="local-2TB-zfs"
        else
            continue
        fi

        echo "🔹 Checking if ZFS block device exists on $NODE_FQDN..."
        if ssh root@$NODE_FQDN "ls /dev/zvol/$VG_NAME/ceph-osd &>/dev/null"; then
            echo "✅ ZFS block device exists on $NODE_FQDN."
        else
            echo "❌ No ZFS block device found on $NODE_FQDN! Creating with thin provisioning (20GB)..."
            ssh root@$NODE_FQDN "zfs create -V 20G -s $VG_NAME/ceph-osd"
        fi
    done
}

setup_zfs_tuning() {
    echo "🚀 Tuning ZFS settings for Ceph..."

    for node in $PROXMOX_NODES; do
        if [[ "$node" == "pve" ]]; then
            NODE_FQDN="pve"
            ZPOOL_NAME="rpool/data"  # Fix for pve
        elif [[ "$node" == "chief-horse" ]]; then
            NODE_FQDN="chief-horse.maas"
            ZPOOL_NAME="local-256-gb-zfs"
        elif [[ "$node" == "still-fawn" ]]; then
            NODE_FQDN="still-fawn.maas"
            ZPOOL_NAME="local-2TB-zfs"
        else
            continue
        fi

        echo "🔹 Applying ZFS tuning on $NODE_FQDN..."
        ssh root@$NODE_FQDN <<EOF
            zfs set sync=disabled $ZPOOL_NAME
            zfs set atime=off $ZPOOL_NAME
            zfs set xattr=sa $ZPOOL_NAME
            zfs set recordsize=64K $ZPOOL_NAME
            echo "✅ ZFS tuning completed on $NODE_FQDN"
EOF
    done
}

# ---------------------------- Section 5: Ensure LVM Volume Groups Exist ----------------------------
setup_lvm_for_ceph() {
    echo "🚀 Configuring LVM-backed Ceph OSD storage..."

    for node in $PROXMOX_NODES; do
        if [[ "$node" == "pve" ]]; then
            NODE_FQDN="pve"
            VG_NAME="rpool/data"
        elif [[ "$node" == "chief-horse" ]]; then
            NODE_FQDN="chief-horse.maas"
            VG_NAME="local-256-gb-zfs"
        elif [[ "$node" == "still-fawn" ]]; then
            NODE_FQDN="still-fawn.maas"
            VG_NAME="local-2TB-zfs"
        else
            continue
        fi

        echo "🔹 Checking if volume group $VG_NAME exists on $NODE_FQDN..."
        if ssh root@$NODE_FQDN "vgs | grep -q '$VG_NAME'"; then
            echo "✅ Volume group $VG_NAME exists on $NODE_FQDN."
        else
            echo "❌ Volume group $VG_NAME not found on $NODE_FQDN! Creating..."

            # Fix: Properly escape slashes in `sed`
            ssh root@$NODE_FQDN <<EOF
                sed -i 's|filter = .*|filter = [ "a|/dev/zvol/.*|", "r|.*|" ]|' /etc/lvm/lvm.conf
                systemctl restart lvm2-lvmetad
                vgcreate $VG_NAME /dev/zvol/$VG_NAME/ceph-osd
EOF
        fi
    done
}

# ---------------------------- Section 6: Ensure OSDs Exist ----------------------------
create_osds() {
    echo "🚀 Creating Ceph OSDs..."

    for node in $PROXMOX_NODES; do
        NODE_FQDN="${node}.maas"

        case "$node" in
            "pve") OSD_PATH="/dev/local-zfs/ceph-osd";;
            "chief-horse") OSD_PATH="/dev/local-256-gb-zfs/ceph-osd";;
            "still-fawn") OSD_PATH="/dev/local-2TB-zfs/ceph-osd";;
            "rapid-civet")
                echo "🔹 Checking for existing OSD on $NODE_FQDN..."
                OSD_ID=$(ssh root@$NODE_FQDN "ls /var/lib/ceph/osd/ | grep -Eo '[0-9]+' | head -n 1" || echo "")

                if [[ -n "$OSD_ID" ]]; then
                    echo "✅ OSD already exists on $NODE_FQDN, skipping creation."
                    continue
                fi

                echo "🔹 Using directory-based OSD for $NODE_FQDN..."
                OSD_ID=$(ssh root@$NODE_FQDN "ceph osd create")
                OSD_PATH="/var/lib/ceph/osd/ceph-${OSD_ID}"

                ssh root@$NODE_FQDN "mkdir -p $OSD_PATH"
                ssh root@$NODE_FQDN "chown -R ceph:ceph $OSD_PATH"
                ssh root@$NODE_FQDN "systemctl enable ceph-osd@$OSD_ID && systemctl start ceph-osd@$OSD_ID"
                continue
                ;;
            *) continue;;
        esac

        echo "🔹 Checking for existing OSD on $NODE_FQDN..."
        if ssh root@$NODE_FQDN "ceph-volume lvm list | grep -q '$OSD_PATH'"; then
            echo "✅ OSD already exists on $NODE_FQDN, skipping creation."
            continue
        fi

        echo "🔹 Creating OSD on $NODE_FQDN using $OSD_PATH..."
        ssh root@$NODE_FQDN "pveceph createosd $OSD_PATH"
    done
}

# ---------------------------- Main Execution ----------------------------
# install_ceph
# setup_bootstrap_key
# setup_monitors
setup_zfs_block_device
setup_zfs_tuning
setup_lvm_for_ceph
create_osds

echo "✅ Ceph setup complete!"