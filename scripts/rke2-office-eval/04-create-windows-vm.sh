#!/bin/bash
# Create Windows Server 2022 VM for RKE2 worker
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration - override with environment variables
PROXMOX_HOST="${PROXMOX_HOST:-}"
WINDOWS_IP="${WINDOWS_IP:-}"
VM_CORES="${VM_CORES:-8}"
VM_MEMORY="${VM_MEMORY:-16384}"
VM_DISK="${VM_DISK:-200G}"
STORAGE="${STORAGE:-local-lvm}"

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Create Windows Server 2022 VM for RKE2 worker node.

Options:
  --proxmox-host HOST   Proxmox host to create VM on
  --ip IP               IP address for Windows VM
  --storage POOL        Proxmox storage pool (default: local-lvm)
  --cores N             CPU cores (default: 8)
  --memory MB           RAM in MB (default: 16384)
  --disk SIZE           Disk size (default: 200G)
  -h, --help            Show this help

Prerequisites:
  - Windows Server 2022 evaluation ISO in /var/lib/vz/template/iso/
  - VirtIO drivers ISO (virtio-win.iso)

Example:
  $0 --proxmox-host pve.office.local --ip 192.168.1.201

EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --proxmox-host) PROXMOX_HOST="$2"; shift 2 ;;
        --ip) WINDOWS_IP="$2"; shift 2 ;;
        --storage) STORAGE="$2"; shift 2 ;;
        --cores) VM_CORES="$2"; shift 2 ;;
        --memory) VM_MEMORY="$2"; shift 2 ;;
        --disk) VM_DISK="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

if [[ -z "$PROXMOX_HOST" || -z "$WINDOWS_IP" ]]; then
    echo "ERROR: --proxmox-host and --ip are required"
    usage
fi

GATEWAY=$(echo "$WINDOWS_IP" | sed 's/\.[0-9]*$/.1/')

echo "=== Creating Windows Server 2022 VM on ${PROXMOX_HOST} ==="
echo ""
echo "IP:      ${WINDOWS_IP} (configure manually after install)"
echo "Gateway: ${GATEWAY}"
echo "Storage: ${STORAGE}"
echo "Cores:   ${VM_CORES}"
echo "Memory:  ${VM_MEMORY}MB"
echo "Disk:    ${VM_DISK}"
echo ""

# Find next available VMID
VMID=$(ssh root@${PROXMOX_HOST} "pvesh get /cluster/nextid")
echo "Using VMID: ${VMID}"

# Check for ISOs
echo ""
echo "=== Checking for required ISOs ==="
WINDOWS_ISO=$(ssh root@${PROXMOX_HOST} "ls /var/lib/vz/template/iso/*SERVER_EVAL*.iso 2>/dev/null | head -1 | xargs basename || ls /var/lib/vz/template/iso/*SERVER*2022*.iso 2>/dev/null | head -1 | xargs basename || echo ''")
VIRTIO_ISO=$(ssh root@${PROXMOX_HOST} "ls /var/lib/vz/template/iso/virtio-win*.iso 2>/dev/null | head -1 | xargs basename || echo ''")

if [[ -z "$WINDOWS_ISO" ]]; then
    echo "ERROR: Windows Server ISO not found"
    echo "Download from: https://www.microsoft.com/en-us/evalcenter/download-windows-server-2022"
    echo "Upload to: /var/lib/vz/template/iso/"
    exit 1
fi
echo "Windows ISO: ${WINDOWS_ISO}"

if [[ -z "$VIRTIO_ISO" ]]; then
    echo "ERROR: VirtIO ISO not found"
    echo "Download from: https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso"
    echo "Upload to: /var/lib/vz/template/iso/"
    exit 1
fi
echo "VirtIO ISO: ${VIRTIO_ISO}"

echo ""
echo "=== Creating VM ${VMID} ==="
ssh root@${PROXMOX_HOST} "
    qm create ${VMID} --name windows-worker --cores ${VM_CORES} --memory ${VM_MEMORY} \
        --net0 virtio,bridge=vmbr0 \
        --agent 1 \
        --ostype win11 \
        --cpu host \
        --scsihw virtio-scsi-pci \
        --bios ovmf \
        --machine q35 \
        --efidisk0 ${STORAGE}:1,efitype=4m

    qm set ${VMID} --scsi0 ${STORAGE}:${VM_DISK},cache=writeback,discard=on,iothread=1
    qm set ${VMID} --ide2 local:iso/${WINDOWS_ISO},media=cdrom
    qm set ${VMID} --ide3 local:iso/${VIRTIO_ISO},media=cdrom
    qm set ${VMID} --boot order='ide2;scsi0'
    qm set ${VMID} --tpmstate0 ${STORAGE}:1,version=v2.0
"

echo ""
echo "=== VM ${VMID} Created ==="
echo ""
echo "Start VM: ssh root@${PROXMOX_HOST} 'qm start ${VMID}'"
echo ""
echo "=== Windows Installation Instructions ==="
echo ""
echo "1. Open console in Proxmox UI (VM ${VMID} -> Console)"
echo ""
echo "2. During Windows Setup - Load VirtIO drivers:"
echo "   - Click 'Load driver' when disk not visible"
echo "   - Browse to D:\\vioscsi\\2k22\\amd64 (disk driver)"
echo "   - Browse to D:\\NetKVM\\2k22\\amd64 (network driver)"
echo ""
echo "3. After Windows install:"
echo "   - Set static IP: ${WINDOWS_IP}/24"
echo "   - Gateway: ${GATEWAY}"
echo "   - DNS: ${GATEWAY} (or your DNS server)"
echo "   - Enable Remote Desktop"
echo "   - Install QEMU Guest Agent: D:\\guest-agent\\qemu-ga-x86_64.msi"
echo ""
echo "4. Then run: ./05-register-windows-node.sh"
echo ""
echo "Windows Evaluation: 180 days"
