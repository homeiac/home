#!/bin/bash
# Coral USB TPU Passthrough Setup for pumped-piglet -> k3s-vm-pumped-piglet-gpu
# Run this script ON pumped-piglet.maas after physically connecting Coral USB

set -e

# Configuration
VM_ID=105
FIRMWARE_URL="https://raw.githubusercontent.com/google-coral/libedgetpu/master/firmware/apex_latest_single_ep.bin"
FIRMWARE_PATH="/usr/local/lib/firmware/apex_latest_single_ep.bin"
UDEV_RULES="/etc/udev/rules.d/95-coral-init.rules"

echo "=== Coral USB TPU Passthrough Setup ==="
echo "Target VM: $VM_ID (k3s-vm-pumped-piglet-gpu)"
echo ""

# Step 1: Check if Coral is connected
echo "[1/6] Checking for Coral USB device..."
if ! lsusb | grep -qE "(18d1:9302|1a6e:089a)"; then
    echo "ERROR: Coral USB not detected. Please connect it first."
    exit 1
fi
CORAL_STATE=$(lsusb | grep -E "(18d1|1a6e)" | head -1)
echo "Found: $CORAL_STATE"

# Step 2: Install prerequisites
echo ""
echo "[2/6] Installing prerequisites..."
apt-get update -qq
apt-get install -y -qq usbutils dfu-util

# Step 3: Download firmware
echo ""
echo "[3/6] Downloading Coral firmware..."
mkdir -p /usr/local/lib/firmware
if [ ! -f "$FIRMWARE_PATH" ]; then
    wget -q -O "$FIRMWARE_PATH" "$FIRMWARE_URL"
    echo "Downloaded firmware to $FIRMWARE_PATH"
else
    echo "Firmware already exists at $FIRMWARE_PATH"
fi

# Step 4: Create udev rules
echo ""
echo "[4/6] Creating udev rules with firmware loading..."
cat > "$UDEV_RULES" << 'EOF'
# Coral USB Accelerator initialization
# Rule 1: Load firmware when Coral detected in bootloader mode
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="1a6e", ATTR{idProduct}=="089a", \
  RUN+="/usr/bin/dfu-util -D /usr/local/lib/firmware/apex_latest_single_ep.bin"

# Rule 2: Set permissions when Coral is initialized (Google mode)
SUBSYSTEMS=="usb", ATTRS{idVendor}=="18d1", ATTRS{idProduct}=="9302", \
  OWNER="root", MODE="0666", GROUP="plugdev"

# Rule 3: Set permissions for bootloader mode too
SUBSYSTEMS=="usb", ATTRS{idVendor}=="1a6e", ATTRS{idProduct}=="089a", \
  OWNER="root", MODE="0666", GROUP="plugdev"
EOF
echo "Created $UDEV_RULES"

# Step 5: Reload udev and initialize Coral
echo ""
echo "[5/6] Reloading udev rules and initializing Coral..."
udevadm control --reload-rules
udevadm trigger
sleep 5

# Check if initialization succeeded
if lsusb | grep -q "18d1:9302"; then
    echo "SUCCESS: Coral initialized (18d1:9302 Google Inc.)"
else
    echo "WARNING: Coral still in bootloader mode (1a6e:089a)"
    echo "Attempting manual firmware load..."
    dfu-util -D "$FIRMWARE_PATH" 2>/dev/null || true
    sleep 3
    if lsusb | grep -q "18d1:9302"; then
        echo "SUCCESS: Coral initialized after manual load"
    else
        echo "ERROR: Could not initialize Coral. Try unplugging and replugging."
        exit 1
    fi
fi

# Step 6: Backup VM config and add USB passthrough
echo ""
echo "[6/6] Configuring USB passthrough to VM $VM_ID..."

VM_CONF="/etc/pve/qemu-server/$VM_ID.conf"
VM_BACKUP="/etc/pve/qemu-server/$VM_ID.conf.pre-coral-$(date +%Y%m%d)"

if [ ! -f "$VM_BACKUP" ]; then
    cp "$VM_CONF" "$VM_BACKUP"
    echo "Created backup: $VM_BACKUP"
fi

# Check if USB passthrough already configured
if grep -q "usb.*18d1:9302" "$VM_CONF"; then
    echo "USB passthrough already configured"
else
    qm set $VM_ID -usb0 host=18d1:9302
    echo "Added USB passthrough for Coral (18d1:9302)"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Restart the VM: qm stop $VM_ID && qm start $VM_ID"
echo "2. Verify Coral in VM: ssh ubuntu@k3s-vm-pumped-piglet-gpu 'lsusb | grep Google'"
echo "3. Apply K8s manifests: KUBECONFIG=~/kubeconfig kubectl apply -k k8s/frigate-016/"
echo ""
echo "Rollback command:"
echo "  cp $VM_BACKUP $VM_CONF && qm stop $VM_ID && qm start $VM_ID"
