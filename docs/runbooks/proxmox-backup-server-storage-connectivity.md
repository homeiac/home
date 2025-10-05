# Runbook: Fix Proxmox Backup Server Storage Connectivity Issues

## Problem Statement
Proxmox Backup Server (PBS) storage repositories appear as inactive or inaccessible in Proxmox VE due to DNS resolution failures. The most common cause is missing DNS entries in MAAS for infrastructure containers that don't receive automatic DNS registration.

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

#### Step 2: Create DNS Resource in MAAS Web UI (Recommended)
1. **Access MAAS Web Interface**: Navigate to `http://192.168.4.53:5240/MAAS/`
2. **Go to Domains**: Click on **Domains** → **maas**
3. **Add DNS Resource**: Click **Add DNS resource**
4. **Configure DNS Entry**:
   - **Name**: `proxmox-backup-server`
   - **Type**: `A/AAAA record`
   - **Data**: `192.168.4.218` (current container IP)
5. **Save**: Click **Save DNS resource**

#### Step 3: Alternative - MAAS CLI Method
```bash
# If you have MAAS CLI configured
maas admin dnsresources create domain=maas name=proxmox-backup-server ip_addresses=192.168.4.218
```

#### Step 4: Fallback - Local DNS Override
```bash
# Only if MAAS access is not available
echo "192.168.4.218 proxmox-backup-server.maas proxmox-backup-server" >> /etc/hosts
```

### Option 2: Use IP Address Instead of Hostname (Not Recommended)

**Note**: This approach works but is not recommended for infrastructure services as it bypasses proper DNS architecture.

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

### Issue: DNS Entry Not Working After Creation
```bash
# Wait for DNS propagation (30-60 seconds)
sleep 60

# Test DNS resolution
host proxmox-backup-server.maas
nslookup proxmox-backup-server.maas 192.168.4.53

# Clear local DNS cache if needed
systemctl restart systemd-resolved
```

### Issue: Container IP Address Changed
```bash
# Get current container IP
pct exec 103 -- ip a show eth0 | grep "inet "

# Update DNS resource in MAAS with new IP
# Go to MAAS → Domains → maas → Edit DNS resource
# Update the IP address to match current container IP
```

### Issue: Authentication Failed
```bash
# Update fingerprint using hostname (after DNS is working)
pvesm set proxmox-backup-server --fingerprint "$(echo | openssl s_client -connect proxmox-backup-server.maas:8007 2>/dev/null | openssl x509 -fingerprint -sha256 -noout | cut -d'=' -f2)"
```

### Issue: Firewall Blocking
```bash
# Check if port 8007 is accessible
nc -zv proxmox-backup-server.maas 8007

# Check PBS container firewall
pct exec 103 -- iptables -L -n | grep 8007
```

## Prevention

### Best Practices
1. **Create DNS entries manually** for infrastructure containers in MAAS
2. **Use hostnames consistently** rather than IP addresses in configuration
3. **Document DNS entries** in configuration management
4. **Monitor DNS resolution** for critical services
5. **Keep MAAS DNS resources updated** when container IPs change

### Long-term Solutions
1. **Infrastructure Containers**: Always create manual DNS resources for critical services
2. **Monitoring**: Set up DNS resolution monitoring for backup services
3. **Documentation**: Maintain inventory of manual DNS entries created
4. **Automation**: Consider scripting DNS resource creation for new infrastructure containers

### Why Some Containers Don't Get Automatic DNS
- MAAS automatically creates DNS for some services (VMs with certain naming patterns, managed machines)
- Infrastructure containers like PBS may not follow patterns MAAS recognizes
- Containers with complex hostnames (multiple dashes) may not trigger automatic registration
- Manual DNS resource creation is the reliable solution for infrastructure services

## Rollback

### Remove DNS Entry from MAAS
1. **Access MAAS Web Interface**: Navigate to `http://192.168.4.53:5240/MAAS/`
2. **Go to Domains**: Click on **Domains** → **maas**
3. **Find DNS Resource**: Locate `proxmox-backup-server` entry
4. **Delete**: Click the delete button for the DNS resource

### Restore Storage Configuration (if using IP fallback)
```bash
# If you used IP addresses temporarily, revert to hostname
sed -i 's/server 192.168.4.218/server proxmox-backup-server.maas/' /etc/pve/storage.cfg
```

## Related Documentation
- [Proxmox Backup Server Administration Guide](https://pbs.proxmox.com/docs/)
- [Proxmox VE Storage Documentation](https://pve.proxmox.com/wiki/Storage)
- MAAS DNS configuration for homelab

## Tags
proxmox, pbs, storage, dns, connectivity, backup, maas, troubleshooting