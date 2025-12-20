#!/bin/bash
# Check windows-eval cluster provisioning status
set -e

PROXMOX_HOST="pumped-piglet.maas"
RANCHER_VM_IP="192.168.4.200"
LINUX_VM_IP="192.168.4.202"

echo "=== Cluster Provisioning Status ==="
echo ""

echo "=== Rancher UI Status ==="
HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" https://rancher.homelab/)
echo "Rancher HTTP: $HTTP_CODE"
echo ""

echo "=== Linux Control Plane VM (202) ==="
ssh root@${PROXMOX_HOST} "ssh -o StrictHostKeyChecking=no ubuntu@${LINUX_VM_IP} 'uptime && echo \"\" && systemctl is-active rancher-system-agent'" 2>/dev/null || echo "Cannot reach VM 202"
echo ""

echo "=== Check if RKE2 is running on VM 202 ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'systemctl is-active rke2-server 2>/dev/null || systemctl is-active rke2-agent 2>/dev/null || echo \"RKE2 not yet installed\"'" 2>/dev/null
echo ""

echo "=== Rancher System Agent Logs (last 10 lines) ==="
ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'sudo journalctl -u rancher-system-agent --no-pager -n 10'" 2>/dev/null || echo "Cannot get logs"
