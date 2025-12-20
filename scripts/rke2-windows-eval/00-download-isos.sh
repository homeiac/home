#!/bin/bash
# Download Windows Server 2022 Evaluation ISO and VirtIO drivers
# These need to be uploaded to Proxmox storage manually or via API
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOWNLOAD_DIR="${SCRIPT_DIR}/isos"

mkdir -p "$DOWNLOAD_DIR"

echo "=== RKE2 Windows Eval - ISO Downloads ==="
echo ""
echo "Download these ISOs manually and upload to Proxmox:"
echo ""
echo "1. Windows Server 2022 Evaluation (180-day trial):"
echo "   https://www.microsoft.com/en-us/evalcenter/download-windows-server-2022"
echo "   - Select: ISO downloads"
echo "   - Choose: 64-bit edition, English"
echo "   - File: SERVER_EVAL_x64FRE_en-us.iso (~5GB)"
echo ""
echo "2. VirtIO Drivers for Windows:"
echo "   https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso"
echo ""

# Download VirtIO drivers (smaller, can auto-download)
VIRTIO_URL="https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso"
VIRTIO_FILE="${DOWNLOAD_DIR}/virtio-win.iso"

if [[ -f "$VIRTIO_FILE" ]]; then
    echo "VirtIO ISO already exists: $VIRTIO_FILE"
else
    echo "Downloading VirtIO drivers..."
    curl -L -o "$VIRTIO_FILE" "$VIRTIO_URL"
    echo "Downloaded: $VIRTIO_FILE"
fi

echo ""
echo "=== Upload to Proxmox ==="
echo ""
echo "Upload ISOs to pumped-piglet Proxmox storage:"
echo "  scp ${DOWNLOAD_DIR}/*.iso root@pumped-piglet.maas:/var/lib/vz/template/iso/"
echo ""
echo "Or via Proxmox UI: Datacenter -> pumped-piglet -> local -> ISO Images -> Upload"
echo ""
echo "After upload, run: ./01-create-rancher-vm.sh"
