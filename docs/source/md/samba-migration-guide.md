# Samba Migration to Flux Guide

This guide covers migrating the existing Samba deployment to Flux GitOps management while preserving all data and credentials.

## Pre-Migration State

**Current Setup:**
- Manual deployment in `samba` namespace
- Data stored on `/mnt/smb_data` (2TB drive on k3s-vm-still-fawn)
- Users: `sambauser`, `alice` with credentials in `samba-users` secret
- Share: `secure` share with proper permissions
- Network: hostNetwork mode on ports 445, 139

## Migration Steps

### Phase 1: Prepare Flux Manifests (✅ Complete)

Flux manifests created in `gitops/clusters/homelab/apps/samba/`:
- `namespace.yaml` - Samba namespace
- `configmap.yaml` - Volume configuration  
- `deployment.yaml` - Samba deployment (starts with replicas: 0)
- `kustomization.yaml` - Resource coordination

### Phase 2: Backup Secrets

**⚠️ CRITICAL: Secrets are NOT stored in git repository**

1. **Backup existing secret** (already done):
   ```bash
   kubectl get secret samba-users -n samba -o yaml > ~/samba-users-backup.yaml
   ```

2. **Verify backup**:
   ```bash
   ls -la ~/samba-users-backup.yaml
   ```

### Phase 3: Deploy Flux Manifests

1. **Commit and push** Flux manifests:
   ```bash
   git add gitops/clusters/homelab/apps/samba/
   git add gitops/clusters/homelab/kustomization.yaml
   git commit -m "Add Samba Flux manifests with replicas: 0

   - Create namespace, configmap, and deployment
   - Start with 0 replicas for safe migration
   - Preserves existing data location /mnt/smb_data
   - Secret managed externally (not in git)
   
   refs #86"
   git push
   ```

2. **Verify Flux deployment** (should create namespace/configmap only):
   ```bash
   kubectl get all -n samba
   # Should show original deployment still running
   ```

### Phase 4: Execute Migration

1. **Scale down current deployment**:
   ```bash
   kubectl scale deployment samba -n samba --replicas=0
   ```

2. **Wait for pod termination**:
   ```bash
   kubectl get pods -n samba -w
   ```

3. **Apply secret manually**:
   ```bash
   kubectl apply -f ~/samba-users-backup.yaml
   ```

4. **Enable Flux deployment**:
   ```bash
   # Edit deployment.yaml to change replicas: 0 to replicas: 1
   # Commit and push changes
   ```

### Phase 5: Validation

1. **Check pod status**:
   ```bash
   kubectl get pods -n samba -o wide
   ```

2. **Verify LoadBalancer service**:
   ```bash
   kubectl get svc -n samba samba-lb
   # Should show EXTERNAL-IP: 192.168.4.53
   ```

3. **Test IP connectivity**:
   ```bash
   # Test from any network device
   ping 192.168.4.53
   nc -zv 192.168.4.53 445
   ```

4. **Verify data integrity**:
   ```bash
   kubectl exec -n samba deployment/samba -- ls -la /shares
   ```

5. **Test user access via IP**:
   ```bash
   # From client machine:
   smbclient //192.168.4.53/secure -U sambauser
   smbclient //192.168.4.53/secure -U alice
   ```

### Phase 6: DNS Configuration (Recommended)

1. **Add DNS override in OPNsense**:
   - Services → Unbound DNS → Overrides → Host Overrides
   - Add: `samba.homelab` → `192.168.4.53`

2. **Test DNS resolution**:
   ```bash
   nslookup samba.homelab
   ping samba.homelab
   ```

3. **Test user access via DNS**:
   ```bash
   smbclient //samba.homelab/secure -U sambauser
   smbclient //samba.homelab/secure -U alice
   ```

## Rollback Plan

If issues arise during migration:

1. **Scale down Flux deployment**:
   ```bash
   kubectl patch deployment samba -n samba -p '{"spec":{"replicas":0}}'
   ```

2. **Restore original deployment**:
   ```bash
   # Apply saved original deployment manifest
   kubectl apply -f original-samba-deployment.yaml
   ```

3. **Scale back up**:
   ```bash
   kubectl scale deployment samba -n samba --replicas=1
   ```

## Post-Migration Benefits

- **GitOps Managed**: All future updates via git commits
- **Consistent**: Follows same pattern as other applications
- **Versioned**: Full deployment history in git
- **Automated**: Flux handles reconciliation
- **Secure**: Credentials never stored in repository

## Future Enhancements

- **External Secrets Operator**: Integrate with HashiCorp Vault or AWS Secrets Manager
- **Monitoring**: Add ServiceMonitor for Prometheus metrics
- **Backup**: Automated backup of samba configuration
- **High Availability**: Multi-node deployment with shared storage

## Files Modified

- `gitops/clusters/homelab/apps/samba/` - New Flux manifests (with MetalLB LoadBalancer)
- `gitops/clusters/homelab/kustomization.yaml` - Added samba app
- `docs/source/md/samba-migration-guide.md` - This migration guide

## Required DNS Configuration

**⚠️ Important**: After successful deployment, configure DNS for user-friendly access:

### OPNsense DNS Override Required
- **Service**: Samba LoadBalancer at `192.168.4.53`
- **DNS Entry**: `samba.homelab` → `192.168.4.53`
- **Configuration**: Services → Unbound DNS → Overrides → Host Overrides
- **Client Access**: Use `\\samba.homelab\secure` instead of `\\192.168.4.53\secure`

This follows the homelab DNS pattern where non-HTTP services get MetalLB IPs with corresponding DNS entries.

## Client Access Instructions

### Current Access Method

**Original Setup**: Samba runs with `hostNetwork: true` on `k3s-vm-still-fawn` (IP: 192.168.4.236)

**New MetalLB Setup**: Samba gets dedicated LoadBalancer IP via MetalLB for better network isolation and DNS integration.

**Connection Details:**
- **Server**: `192.168.4.53` (MetalLB LoadBalancer IP)
- **Alternative**: `samba.homelab.local` (with DNS configuration)
- **Share**: `secure`
- **Users**: `sambauser`, `alice`
- **Ports**: 445 (SMB), 139 (NetBIOS)

### MetalLB Benefits

- **Dedicated IP**: Clean separation from node networking
- **DNS Friendly**: Static IP perfect for DNS records
- **Better Security**: No hostNetwork mode required
- **Consistent Access**: IP won't change if pod reschedules
- **Load Balancing**: Could support multiple pods (though not recommended for file shares)

### Windows Access

#### Method 1: File Explorer
1. Open File Explorer
2. In address bar, type: `\\192.168.4.53\secure` or `\\samba.homelab.local\secure`
3. Enter credentials when prompted:
   - Username: `sambauser` or `alice`
   - Password: (from samba-users secret)

#### Method 2: Map Network Drive
1. Right-click "This PC" → "Map network drive"
2. Drive letter: Choose available letter
3. Folder: `\\192.168.4.53\secure` or `\\samba.homelab.local\secure`
4. Check "Connect using different credentials"
5. Enter username/password

#### Method 3: Command Line
```cmd
net use Z: \\192.168.4.53\secure /user:sambauser
# Enter password when prompted
```

### macOS Access

#### Method 1: Finder
1. Open Finder
2. Press `Cmd+K` (Go → Connect to Server)
3. Server Address: `smb://192.168.4.53/secure` or `smb://samba.homelab.local/secure`
4. Click "Connect"
5. Enter credentials when prompted

#### Method 2: Command Line
```bash
# Mount the share
sudo mkdir -p /Volumes/secure
mount -t smbfs //sambauser@192.168.4.53/secure /Volumes/secure

# Or using mount_smbfs
mount_smbfs //sambauser:password@192.168.4.53/secure /Volumes/secure
```

### Linux Access

#### Method 1: GUI (GNOME/KDE)
1. Open file manager
2. Go to "Other Locations" or "Network"
3. Enter: `smb://192.168.4.53/secure` or `smb://samba.homelab.local/secure`
4. Enter credentials when prompted

#### Method 2: Command Line (cifs-utils)
```bash
# Install cifs-utils if not present
sudo apt-get install cifs-utils  # Ubuntu/Debian
sudo yum install cifs-utils      # RHEL/CentOS

# Create mount point
sudo mkdir -p /mnt/samba-secure

# Mount the share
sudo mount -t cifs //192.168.4.53/secure /mnt/samba-secure \
  -o username=sambauser,password=yourpassword,uid=1000,gid=1000

# Or use credentials file
echo "username=sambauser" > ~/.smbcredentials
echo "password=yourpassword" >> ~/.smbcredentials
chmod 600 ~/.smbcredentials

sudo mount -t cifs //192.168.4.53/secure /mnt/samba-secure \
  -o credentials=/home/username/.smbcredentials,uid=1000,gid=1000
```

#### Method 3: smbclient
```bash
# Install smbclient
sudo apt-get install samba-common-bin

# Access share interactively
smbclient //192.168.4.53/secure -U sambauser

# List files
smbclient //192.168.4.53/secure -U sambauser -c "ls"

# Download file
smbclient //192.168.4.53/secure -U sambauser -c "get filename.txt"
```

## DNS Configuration (Recommended)

**MetalLB + OPNsense DNS = Perfect Integration!**

The homelab uses OPNsense Unbound DNS with the `.homelab` domain. Configure `samba.homelab` for clean access.

### OPNsense Unbound DNS Configuration

#### Step 1: Add DNS Override in OPNsense
1. **Access OPNsense Web Interface**
   - Navigate to your OPNsense router (typically `192.168.4.1` or similar)
   - Login with admin credentials

2. **Navigate to Unbound DNS Overrides**
   - Go to: **Services → Unbound DNS → Overrides**
   - Click **Host Overrides** tab

3. **Add Samba DNS Entry**
   - Click **+** (Add) button
   - **Host**: `samba`
   - **Domain**: `homelab`
   - **Type**: `A (IPv4 address)`
   - **IP**: `192.168.4.53` (Samba MetalLB LoadBalancer IP)
   - **Description**: `Samba file server`
   - Click **Save**

4. **Apply Configuration**
   - Click **Apply** to activate the DNS override
   - Restart Unbound DNS if prompted

#### Step 2: Verify DNS Resolution
Test from any device on the network:
```bash
# Test DNS resolution
nslookup samba.homelab
# Should return: 192.168.4.53

ping samba.homelab
# Should ping 192.168.4.53

# Test SMB port
telnet samba.homelab 445
nc -zv samba.homelab 445
```

### Client Access with DNS

#### Windows Access (DNS)
```cmd
# File Explorer - use DNS name
\\samba.homelab\secure

# Map network drive
net use Z: \\samba.homelab\secure /user:sambauser

# PowerShell test
Test-NetConnection samba.homelab -Port 445
```

#### macOS Access (DNS)
```bash
# Finder: Connect to Server
smb://samba.homelab/secure

# Command line mount
mount_smbfs //sambauser@samba.homelab/secure /Volumes/secure

# Test connectivity
nc -zv samba.homelab 445
```

#### Linux Access (DNS)
```bash
# GUI file managers
smb://samba.homelab/secure

# Command line mount
sudo mount -t cifs //samba.homelab/secure /mnt/samba-secure \
  -o username=sambauser,credentials=/home/user/.smbcredentials,uid=1000,gid=1000

# smbclient
smbclient //samba.homelab/secure -U sambauser

# Test connectivity
nc -zv samba.homelab 445
```

### Alternative DNS Options

#### Option 1: Local Hosts File (Per-Device)
If you can't access OPNsense, add to local hosts file:

**Windows**: Edit `C:\Windows\System32\drivers\etc\hosts`
**macOS/Linux**: Edit `/etc/hosts`
```
192.168.4.53  samba.homelab
```

#### Option 2: Router DNS Configuration
For non-OPNsense routers:
- Access router admin interface
- Find DNS/Static Routes/Host Names section
- Add: `samba.homelab` → `192.168.4.53`

#### Option 3: External DNS Operator (Future)
Deploy External DNS operator for automatic DNS management:
```yaml
# Future enhancement: Add to service.yaml
metadata:
  annotations:
    external-dns.alpha.kubernetes.io/hostname: samba.homelab
```

### DNS Benefits

1. **User-Friendly**: `\\samba.homelab\secure` vs `\\192.168.4.53\secure`
2. **Future-Proof**: DNS name stays same if IP changes
3. **Professional**: Consistent with enterprise practices
4. **Network-Wide**: All devices use same DNS name
5. **SSL/TLS Ready**: DNS names required for certificates

### Troubleshooting

#### Connection Issues
```bash
# Test SMB port connectivity
telnet 192.168.4.53 445
nc -zv 192.168.4.53 445

# Test LoadBalancer service
kubectl get svc -n samba samba-lb

# Test from cluster
kubectl exec -n samba deployment/samba -- netstat -tlnp | grep :445
```

#### Permission Issues
- Ensure user exists in samba-users secret
- Check file permissions on /mnt/smb_data
- Verify nobody:nogroup ownership

#### Network Issues
- Verify LoadBalancer service has external IP assigned
- Check MetalLB controller logs: `kubectl logs -n metallb-system deployment/controller`
- Ensure MetalLB IP pool has available addresses
- Test LoadBalancer connectivity: `ping 192.168.4.53`

## Security Notes

- Secrets backed up to `~/samba-users-backup.yaml` (local only)
- Never commit credential files to git repository
- Apply secrets manually on each cluster
- Consider External Secrets Operator for production environments
- SMB traffic is unencrypted - consider VPN for external access
- Use strong passwords for samba users
- Regular backup of /mnt/smb_data recommended