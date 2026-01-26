#!/bin/bash
# Deploy crucible-nbd-server to all Proxmox hosts and configure shared storage
#
# This creates an NBD block device on each Proxmox host connected to the
# 3 downstairs on proper-raptor, providing Ceph-like shared storage.
#
set -e

CRUCIBLE_HOST="ubuntu@192.168.4.189"
PROXMOX_HOSTS="pve still-fawn pumped-piglet chief-horse"
DOWNSTAIRS_TARGETS="192.168.4.189:3810,192.168.4.189:3811,192.168.4.189:3812"

echo "=== Deploying crucible-nbd-server to Proxmox hosts ==="

# Step 1: Copy binary from proper-raptor to each Proxmox host
echo "=== Step 1: Copying crucible-nbd-server binary ==="
for host in $PROXMOX_HOSTS; do
    echo "Copying to $host..."
    # Copy via intermediate (proper-raptor -> local -> proxmox)
    scp ${CRUCIBLE_HOST}:/home/ubuntu/crucible-nbd-server /tmp/crucible-nbd-server
    scp /tmp/crucible-nbd-server root@${host}.maas:/usr/local/bin/
    ssh root@${host}.maas "chmod +x /usr/local/bin/crucible-nbd-server"
    echo "  Done: $host"
done

# Step 2: Ensure nbd kernel module is loaded
echo "=== Step 2: Loading nbd kernel module ==="
for host in $PROXMOX_HOSTS; do
    echo "Configuring $host..."
    ssh root@${host}.maas << 'EOF'
# Load nbd module
modprobe nbd max_part=8

# Make it persistent
echo "nbd" >> /etc/modules-load.d/nbd.conf 2>/dev/null || true
echo "options nbd max_part=8" > /etc/modprobe.d/nbd.conf
EOF
    echo "  Done: $host"
done

# Step 3: Create systemd service for crucible-nbd
echo "=== Step 3: Creating systemd services ==="
for host in $PROXMOX_HOSTS; do
    echo "Creating service on $host..."
    ssh root@${host}.maas "cat > /etc/systemd/system/crucible-nbd.service" << EOF
[Unit]
Description=Crucible NBD Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/crucible-nbd-server -t ${DOWNSTAIRS_TARGETS}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    ssh root@${host}.maas "systemctl daemon-reload"
    echo "  Done: $host"
done

echo ""
echo "=== Deployment complete ==="
echo ""
echo "NEXT STEPS (manual for safety):"
echo ""
echo "1. Start the NBD service on ONE host first to test:"
echo "   ssh root@pve.maas 'systemctl start crucible-nbd'"
echo ""
echo "2. Check if NBD device appears:"
echo "   ssh root@pve.maas 'lsblk | grep nbd'"
echo ""
echo "3. Format the device (ONLY ONCE, on first host):"
echo "   ssh root@pve.maas 'mkfs.ext4 /dev/nbd0'"
echo ""
echo "4. Add to Proxmox as shared storage:"
echo "   - Datacenter -> Storage -> Add -> Directory"
echo "   - Or use pvesm command"
echo ""
echo "5. Start on remaining hosts:"
echo "   for host in still-fawn pumped-piglet chief-horse; do"
echo "     ssh root@\${host}.maas 'systemctl enable --now crucible-nbd'"
echo "   done"
