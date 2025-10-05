# Runbook: Fix Proxmox Backup Server Storage Connectivity Issues

## Problem Statement
Proxmox Backup Server (PBS) storage repositories appear as inactive or inaccessible in Proxmox VE due to DNS resolution failures or network connectivity issues.

## Symptoms
- PBS storage shows as "inactive" in Proxmox GUI
- Error: "Can't connect to proxmox-backup-server.maas:8007 (Name or service not known)"
- Backup jobs fail with connection errors
- Storage status shows 0 bytes available

## Pre-requisites
- SSH access to Proxmox nodes
- PBS container/VM running and accessible
- Knowledge of PBS container ID or location

## Detection

### Check Storage Status
```bash
# List all storage and their status
pvesm status

# Check specific PBS storage
pvesm status | grep -E "proxmox-backup|homelab-backup"
```

### Identify PBS Location
```bash
# Find PBS container on current node
pct list | grep -i backup

# Find PBS VM on current node  
qm list | grep -i backup

# Check all nodes in cluster
for node in $(pvecm nodes | grep -v Nodeid | awk '{print $3}'); do
    echo "=== Node: $node ==="
    ssh root@$node "pct list 2>/dev/null | grep -i backup"
    ssh root@$node "qm list 2>/dev/null | grep -i backup"
done
```

### Get PBS IP Address
```bash
# If PBS is in container (example: CT 103)
pct exec 103 -- ip a show eth0 | grep "inet "

# If PBS is in VM (example: VM 103)
qm guest cmd 103 network-get-interfaces | grep ip-address
```

## Resolution Steps

### Option 1: Fix DNS Resolution (Preferred)

#### Step 1: Check DNS Configuration
```bash
# Check current DNS servers
cat /etc/resolv.conf

# Test DNS resolution
host proxmox-backup-server.maas
nslookup proxmox-backup-server.maas
```

#### Step 2: Add DNS Entry to MAAS
```bash
# Access MAAS server (usually on pve node)
ssh ubuntu@maas.server

# Add DNS entry via MAAS CLI
maas admin dnsresources create domain=maas name=proxmox-backup-server ip_addresses=192.168.4.218
```

#### Step 3: Add Local DNS Override (Alternative)
```bash
# Add to /etc/hosts on all Proxmox nodes
echo "192.168.4.218 proxmox-backup-server.maas proxmox-backup-server" >> /etc/hosts
```

### Option 2: Use IP Address Instead of Hostname

#### Step 1: Update Storage Configuration
```bash
# Backup current configuration
cp /etc/pve/storage.cfg /etc/pve/storage.cfg.backup

# Replace hostname with IP address
sed -i 's/server proxmox-backup-server.maas/server 192.168.4.218/' /etc/pve/storage.cfg
```

#### Step 2: Verify Changes
```bash
# Check configuration
grep -A5 "pbs:" /etc/pve/storage.cfg

# Test storage connectivity
pvesm status | grep pbs
```

### Option 3: Update Storage via GUI

1. Navigate to Datacenter → Storage
2. Select the PBS storage entry
3. Click Edit
4. Change Server field from hostname to IP address
5. Save and verify connectivity

## Verification

### Test Storage Access
```bash
# Check storage is active
pvesm status | grep "proxmox-backup\|homelab-backup"

# List PBS datastores (requires authentication)
pvesm list <storage-name>

# Test backup functionality
vzdump 100 --storage proxmox-backup-server --mode snapshot
```

### Verify from Multiple Nodes
```bash
# Check storage visibility from all nodes
for node in $(pvecm nodes | grep -v Nodeid | awk '{print $3}'); do
    echo "=== Node: $node ==="
    ssh root@$node "pvesm status | grep pbs"
done
```

## Common Issues and Solutions

### Issue: Authentication Failed
```bash
# Update fingerprint
pvesm set proxmox-backup-server --fingerprint "$(echo | openssl s_client -connect 192.168.4.218:8007 2>/dev/null | openssl x509 -fingerprint -sha256 -noout | cut -d'=' -f2)"
```

### Issue: Different IPs on Different Nodes
```bash
# Ensure PBS has static IP
pct config 103 | grep net0
# Add: ,ip=192.168.4.218/24,gw=192.168.4.1
```

### Issue: Firewall Blocking
```bash
# Check if port 8007 is accessible
nc -zv 192.168.4.218 8007

# Check PBS container firewall
pct exec 103 -- iptables -L -n | grep 8007
```

## Prevention

### Best Practices
1. **Use Static IPs** for critical infrastructure services
2. **Document IP assignments** in configuration management
3. **Configure DNS properly** before using hostnames
4. **Monitor DNS resolution** for critical services

### Long-term Solutions
1. Configure MAAS to automatically register LXC containers
2. Use DHCP reservations with DNS registration
3. Implement service discovery mechanism
4. Set up monitoring for storage connectivity

## Rollback

### Restore Original Configuration
```bash
# Restore from backup
cp /etc/pve/storage.cfg.backup /etc/pve/storage.cfg

# Or manually revert
sed -i 's/server 192.168.4.218/server proxmox-backup-server.maas/' /etc/pve/storage.cfg
```

## Related Documentation
- [Proxmox Backup Server Administration Guide](https://pbs.proxmox.com/docs/)
- [Proxmox VE Storage Documentation](https://pve.proxmox.com/wiki/Storage)
- MAAS DNS configuration for homelab

## Tags
proxmox, pbs, storage, dns, connectivity, backup, maas, troubleshooting