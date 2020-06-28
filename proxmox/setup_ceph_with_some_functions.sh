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

# ---------------------------- Section 4: Create Monitors (MONs) ----------------------------
create_mons() {
    echo "🚀 Creating Ceph MONs..."
    for node in $PROXMOX_NODES; do
        NODE_FQDN="${node}.maas"
        NODE_IP=$(ssh root@$NODE_FQDN "pvesh get /nodes/$node/network --output-format json | jq -r '.[] | select(.iface==\"vmbr0\") | .address'")

        if ceph mon dump | grep -q "$NODE_IP"; then
            echo "✅ MON already exists on $NODE_FQDN ($NODE_IP), skipping..."
            continue
        fi

        echo "🔹 Creating MON on $NODE_FQDN using IP $NODE_IP"
        ssh root@$NODE_FQDN "pveceph createmon --mon-address $NODE_IP"
    done
}

create_osds() {
    echo "🚀 Creating Ceph OSDs..."

    for node in $PROXMOX_NODES; do
        NODE_FQDN="${node}.maas"

        if [[ "$node" == "pve" ]]; then
            OSD_PATH="/dev/local-zfs/ceph-osd"
        elif [[ "$node" == "chief-horse" ]]; then
            OSD_PATH="/dev/local-256-gb-zfs/ceph-osd"
        elif [[ "$node" == "still-fawn" ]]; then
            OSD_PATH="/dev/local-2TB-zfs/ceph-osd"
        elif [[ "$node" == "rapid-civet" ]]; then
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
            ssh root@$NODE_FQDN "ceph-bluestore-tool prime-osd-dir --dev $OSD_PATH --path $OSD_PATH --no-mon-config"
            ssh root@$NODE_FQDN "ceph-osd -i $OSD_ID --mkfs --osd-data $OSD_PATH --osd-uuid $(uuidgen)"
            ssh root@$NODE_FQDN "chown -R ceph:ceph $OSD_PATH"

            echo "🔹 Activating OSD on $NODE_FQDN..."
            ssh root@$NODE_FQDN "systemctl enable ceph-osd@$OSD_ID"
            ssh root@$NODE_FQDN "systemctl start ceph-osd@$OSD_ID"

            continue
        fi

        echo "🔹 Checking for existing OSD on $NODE_FQDN using $OSD_PATH..."
        if ssh root@$NODE_FQDN "ceph-volume lvm list | grep -q '$OSD_PATH'"; then
            echo "✅ OSD already exists on $NODE_FQDN ($OSD_PATH), skipping creation."
            continue
        fi

        echo "🔹 Creating OSD on $NODE_FQDN using $OSD_PATH..."
        ssh root@$NODE_FQDN "pveceph createosd $OSD_PATH"
    done
}

