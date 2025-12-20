#!/bin/bash
# Create Windows Server 2022 VM for RKE2 worker on pumped-piglet
set -e

PROXMOX_HOST="pumped-piglet.maas"
VMID=201
VM_NAME="windows-worker"
CORES=8
MEMORY=16384
DISK_SIZE="200G"
STORAGE="local-2TB-zfs"  # ZFS storage on pumped-piglet
BRIDGE="vmbr0"
IP="192.168.4.201"

# ISO names (must be uploaded first via 00-download-isos.sh)
WINDOWS_ISO="SERVER_EVAL_x64FRE_en-us.iso"  # Adjust to actual filename
VIRTIO_ISO="virtio-win.iso"

echo "=== Creating Windows Server 2022 VM on ${PROXMOX_HOST} ==="
echo ""
echo "VM Configuration:"
echo "  VMID: ${VMID}"
echo "  Name: ${VM_NAME}"
echo "  CPU: ${CORES} cores (host passthrough)"
echo "  RAM: ${MEMORY}MB"
echo "  Disk: ${DISK_SIZE}"
echo "  Target IP: ${IP}/24 (configure manually in Windows)"
echo ""

# Check if VM already exists
if ssh root@${PROXMOX_HOST} "qm status ${VMID}" 2>/dev/null; then
    echo "ERROR: VM ${VMID} already exists on ${PROXMOX_HOST}"
    echo "Run ./99-cleanup.sh first or choose a different VMID"
    exit 1
fi

# Check for ISOs
echo "Checking for required ISOs..."
ssh root@${PROXMOX_HOST} "
    ISO_PATH='/var/lib/vz/template/iso'

    # Find Windows ISO (flexible matching)
    WIN_ISO=\$(ls \${ISO_PATH}/*SERVER_EVAL*.iso 2>/dev/null | head -1 || ls \${ISO_PATH}/*SERVER*2022*.iso 2>/dev/null | head -1 || ls \${ISO_PATH}/*windows*.iso 2>/dev/null | head -1 || echo '')
    if [[ -z \"\$WIN_ISO\" ]]; then
        echo 'ERROR: Windows Server ISO not found in \${ISO_PATH}'
        echo 'Download from: https://www.microsoft.com/en-us/evalcenter/download-windows-server-2022'
        exit 1
    fi
    echo \"Found Windows ISO: \$WIN_ISO\"

    if [[ ! -f \${ISO_PATH}/${VIRTIO_ISO} ]]; then
        echo 'ERROR: VirtIO ISO not found: \${ISO_PATH}/${VIRTIO_ISO}'
        echo 'Run ./00-download-isos.sh first'
        exit 1
    fi
    echo 'Found VirtIO ISO'
"

# Get actual Windows ISO name
WINDOWS_ISO_ACTUAL=$(ssh root@${PROXMOX_HOST} "ls /var/lib/vz/template/iso/*SERVER_EVAL*.iso 2>/dev/null | head -1 | xargs basename || ls /var/lib/vz/template/iso/*SERVER*2022*.iso 2>/dev/null | head -1 | xargs basename || ls /var/lib/vz/template/iso/*windows*.iso 2>/dev/null | head -1 | xargs basename")

echo ""
echo "Creating VM ${VMID}..."
ssh root@${PROXMOX_HOST} "
    # Create VM with Windows-optimized settings
    qm create ${VMID} --name ${VM_NAME} --cores ${CORES} --memory ${MEMORY} \
        --net0 virtio,bridge=${BRIDGE} \
        --agent 1 \
        --ostype win11 \
        --cpu host \
        --scsihw virtio-scsi-pci \
        --bios ovmf \
        --machine q35 \
        --efidisk0 ${STORAGE}:1,efitype=4m

    # Create and attach disk
    qm set ${VMID} --scsi0 ${STORAGE}:${DISK_SIZE},cache=writeback,discard=on,iothread=1

    # Attach Windows ISO
    qm set ${VMID} --ide2 local:iso/${WINDOWS_ISO_ACTUAL},media=cdrom

    # Attach VirtIO ISO
    qm set ${VMID} --ide3 local:iso/${VIRTIO_ISO},media=cdrom

    # Boot from CD first
    qm set ${VMID} --boot order='ide2;scsi0'

    # Enable TPM for Windows 11/Server 2022
    qm set ${VMID} --tpmstate0 ${STORAGE}:1,version=v2.0
"

echo ""
echo "VM ${VMID} created successfully!"
echo ""
echo "=== Windows Installation Instructions ==="
echo ""
echo "1. Start VM: ssh root@${PROXMOX_HOST} 'qm start ${VMID}'"
echo "   Or via Proxmox UI"
echo ""
echo "2. Open console in Proxmox UI (VM ${VMID} -> Console)"
echo ""
echo "3. During Windows Setup:"
echo "   - When asked for drivers, click 'Load driver'"
echo "   - Browse to D:\\vioscsi\\2k22\\amd64 (VirtIO disk driver)"
echo "   - Also load D:\\NetKVM\\2k22\\amd64 (VirtIO network driver)"
echo "   - Then the disk will appear for installation"
echo ""
echo "4. After Windows install completes:"
echo "   - Set static IP: ${IP}/24, Gateway: 192.168.4.1, DNS: 192.168.4.1"
echo "   - Enable Remote Desktop"
echo "   - Install QEMU Guest Agent from D:\\guest-agent\\qemu-ga-x86_64.msi"
echo ""
echo "5. Then run: ./04-prep-windows-rke2.ps1 on the Windows VM"
echo ""
echo "Windows Evaluation is valid for 180 days."
