#!/bin/bash
# Check HAOS VM (116) CPU usage on chief-horse
set -e

echo "=== HAOS VM CPU Usage ==="
echo "Proxmox host: chief-horse.maas"
echo ""

# Get QEMU process CPU for VM 116
echo "1. QEMU process for VM 116:"
ssh root@chief-horse.maas "ps aux | grep 'qemu.*116' | grep -v grep | awk '{print \"CPU: \" \$3 \"% | MEM: \" \$4 \"% | VSZ: \" \$5}'"
echo ""

# Get current load
echo "2. Host load average:"
ssh root@chief-horse.maas "uptime"
echo ""

# Top CPU processes
echo "3. Top 5 CPU processes on host:"
ssh root@chief-horse.maas "ps aux --sort=-%cpu | head -6"
