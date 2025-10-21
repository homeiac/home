# Proxmox Hostname/FQDN Configuration Fix

## Problem

Proxmox pveproxy service hangs on HTTPS connections when the FQDN in `/etc/hosts` doesn't match the Proxmox node directory name in `/etc/pve/nodes/`.

## Root Cause

When a Proxmox node's `/etc/hosts` file has:
```
192.168.4.175 pumped-piglet.maas pumped-piglet
```

The system resolves `hostname -f` to `pumped-piglet.maas`, but Proxmox expects SSL certificates in `/etc/pve/nodes/pumped-piglet/` (without .maas suffix).

This causes pveproxy to look for certificates in `/etc/pve/nodes/pumped-piglet.maas/` which doesn't exist, resulting in SSL handshake failures.

## Solution

Fix the hostname order in `/etc/hosts` and cloud-init template:

```bash
# 1. Fix the cloud-init template (makes changes persistent)
sed -i 's/192.168.4.175 pumped-piglet.maas pumped-piglet/192.168.4.175 pumped-piglet pumped-piglet.maas/' /etc/cloud/templates/hosts.debian.tmpl

# 2. Update /etc/hosts immediately
sed -i 's/192.168.4.175 pumped-piglet.maas pumped-piglet/192.168.4.175 pumped-piglet pumped-piglet.maas/' /etc/hosts

# 3. Restart pveproxy
systemctl restart pveproxy
```

## Verification

```bash
# Test API responds
curl -k https://localhost:8006/api2/json/version

# Should return JSON with Proxmox version info
```

## Applied To

- pumped-piglet (192.168.4.175) - October 21, 2025
