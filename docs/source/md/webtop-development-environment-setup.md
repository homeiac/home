# Webtop Development Environment Setup Guide

This guide documents the complete setup of a web-based Ubuntu XFCE development environment using LinuxServer.io Webtop running in a Docker LXC container on Proxmox VE.

## Architecture Overview

```
Proxmox Host (still-fawn.maas)
├── ZFS Dataset: local-2TB-zfs/dev-workspace (/data/dev-workspace)
│   ├── webtop-config/     # Webtop application settings
│   ├── webtop-home/       # User home directory (/home/abc)
│   ├── projects/          # Development projects
│   └── shared/            # Shared files
│
└── LXC Container 104 (docker-webtop.maas)
    ├── Docker LXC with pre-installed Docker
    ├── Mount: /data/dev-workspace → /home/devdata
    ├── Network: 192.168.4.230/24 (DHCP from MAAS)
    └── DNS: docker-webtop.maas → 192.168.4.230
    
    └── Docker Container: webtop
        ├── Image: lscr.io/linuxserver/webtop:ubuntu-xfce
        ├── Volumes: External ZFS storage mounted via LXC
        ├── Ports: 3000 (HTTP), 3001 (HTTPS)
        └── Access: https://docker-webtop.maas:3001
```

## Prerequisites

- Proxmox VE host with ZFS storage
- MAAS DNS configuration for `.maas` domain resolution
- Network access to 192.168.4.x subnet
- Proxmox VE Helper Scripts (community-scripts/ProxmoxVE)

## Step 1: Create ZFS Dataset for External Storage

Create a dedicated ZFS dataset for development data that persists outside containers:

```bash
# Create ZFS dataset with dedicated mount point
zfs create -o mountpoint=/data/dev-workspace local-2TB-zfs/dev-workspace

# Create organized directory structure
mkdir -p /data/dev-workspace/{webtop-config,webtop-home,projects,shared}

# Set ownership for LXC UID mapping (100000 + 1000 = 101000)
chown -R 101000:101000 /data/dev-workspace/
```

**Why ZFS Dataset:**
- **Snapshots**: Easy point-in-time backups before major changes
- **Compression**: Automatic space savings for source code
- **Integrity**: Built-in checksumming and error correction
- **Performance**: Optimized for development workloads
- **Portability**: Can be replicated to other systems

## Step 2: Create Docker LXC Container

Use the automated Proxmox VE Helper Scripts method:

```bash
# Set environment variables for automation
export STORAGE="local-2TB-zfs"
export var_disk="50"        # 50GB disk space
export var_ram="8192"       # 8GB RAM for development
export var_cpu="4"          # 4 CPU cores
export var_unprivileged="1" # Unprivileged container

# Remove SSH environment variables to bypass detection
unset SSH_CLIENT SSH_CONNECTION SSH_TTY

# Execute Docker LXC creation script
curl -fsSL https://github.com/community-scripts/ProxmoxVE/raw/main/ct/docker.sh | bash
```

**Container Specifications:**
- **ID**: 104 (automatically assigned)
- **Hostname**: docker-webtop (manual rename required)
- **OS**: Debian 12 with Docker pre-installed
- **Resources**: 4 cores, 8GB RAM, 50GB disk
- **Network**: DHCP on vmbr0 bridge
- **Type**: Unprivileged container for security

## Step 3: Configure LXC Container

### Rename and Configure Container

```bash
# Rename container to descriptive hostname
pct set 104 -hostname docker-webtop

# Set timezone to Pacific
pct exec 104 -- timedatectl set-timezone America/Los_Angeles

# Add mount point for external ZFS dataset
pct stop 104
pct set 104 -mp0 /data/dev-workspace,mp=/home/devdata,shared=1
pct start 104
```

### Verify LXC Mount Point

```bash
# Check mount inside container
pct exec 104 -- ls -la /home/devdata/
# Should show: webtop-config, webtop-home, projects, shared (owned by 1000:1000)

# Verify ZFS dataset access
pct exec 104 -- df -h /home/devdata
# Should show ZFS filesystem mounted
```

## Step 4: Deploy Webtop Container

Deploy the Ubuntu XFCE Webtop container with external storage:

```bash
pct exec 104 -- docker run -d \
  --name=webtop \
  --security-opt seccomp=unconfined \
  -e PUID=1000 \
  -e PGID=1000 \
  -e TZ=America/Los_Angeles \
  -e SUBFOLDER=/ \
  -e TITLE=Webtop \
  -p 3000:3000 \
  -p 3001:3001 \
  -v /home/devdata/webtop-config:/config \
  -v /home/devdata/webtop-home:/home/abc \
  -v /home/devdata/projects:/home/abc/projects \
  -v /home/devdata/shared:/home/abc/shared \
  --restart unless-stopped \
  lscr.io/linuxserver/webtop:ubuntu-xfce
```

### Environment Variables Explained

| Variable | Value | Purpose |
|----------|-------|---------|
| `PUID` | `1000` | User ID for file permissions |
| `PGID` | `1000` | Group ID for file permissions |
| `TZ` | `America/Los_Angeles` | Pacific timezone |
| `SUBFOLDER` | `/` | Root path for web interface |
| `TITLE` | `Webtop` | Browser title bar text |

### Volume Mappings

| Host Path | Container Path | Purpose |
|-----------|----------------|---------|
| `/home/devdata/webtop-config` | `/config` | Webtop application settings |
| `/home/devdata/webtop-home` | `/home/abc` | User home directory |
| `/home/devdata/projects` | `/home/abc/projects` | Development projects |
| `/home/devdata/shared` | `/home/abc/shared` | Shared files |

## Step 5: DNS Configuration

Configure DNS resolution for easy access:

### OPNsense Unbound DNS Override

1. **Access OPNsense**: Navigate to Services → Unbound DNS → Overrides
2. **Add Host Override**:
   - **Host**: `docker-webtop`
   - **Domain**: `maas`
   - **IP**: `192.168.4.230` (container's DHCP IP)
3. **Apply Changes**: Restart Unbound DNS service

### Verify DNS Resolution

```bash
# Test DNS resolution
nslookup docker-webtop.maas
# Should return: 192.168.4.230

# Test from different hosts
ping docker-webtop.maas
# Should reach 192.168.4.230
```

## Step 6: Access and Verification

### Web Access

**Primary Access (HTTPS)**: `https://docker-webtop.maas:3001`
- **Security**: Self-signed certificate (accept browser warning)
- **Authentication**: None required (internal network access)
- **Desktop**: Ubuntu XFCE desktop environment

**Alternative Access (HTTP)**: `http://docker-webtop.maas:3000`
- **Note**: Some features require HTTPS

### Verification Checklist

```bash
# 1. Container Status
pct exec 104 -- docker ps
# Should show: webtop container running

# 2. Port Accessibility  
curl -k -I https://docker-webtop.maas:3001
# Should return: HTTP/1.1 200 OK

# 3. External Storage
pct exec 104 -- ls -la /home/devdata/
# Should show: proper ownership (1000:1000) and directory structure

# 4. ZFS Dataset
zfs list | grep dev-workspace
# Should show: local-2TB-zfs/dev-workspace dataset

# 5. File Persistence Test
# Create file in Webtop web interface: /home/abc/test.txt
ls /data/dev-workspace/webtop-home/test.txt
# Should exist on host filesystem
```

## Configuration Details

### LXC Container Configuration

Located at `/etc/pve/lxc/104.conf`:

```
#Docker Webtop Development Environment
arch: amd64
cores: 4
features: keyctl=1,nesting=1
hostname: docker-webtop
memory: 8192
mp0: /data/dev-workspace,mp=/home/devdata,shared=1
net0: name=eth0,bridge=vmbr0,hwaddr=BC:24:11:FB:64:33,ip=dhcp,type=veth
onboot: 1
ostype: debian
rootfs: local-2TB-zfs:subvol-104-disk-0,size=50G
swap: 512
tags: community-script;docker
unprivileged: 1
```

**Key Settings:**
- `features: keyctl=1,nesting=1` - Enable Docker support in LXC
- `mp0: shared=1` - Enable shared mount for proper UID mapping
- `onboot: 1` - Auto-start container with Proxmox host
- `unprivileged: 1` - Security best practice

### Docker Container Configuration

Inspect the running Webtop container:

```bash
pct exec 104 -- docker inspect webtop
```

**Key Configuration:**
- **Image**: `lscr.io/linuxserver/webtop:ubuntu-xfce`
- **Restart Policy**: `unless-stopped`
- **Security**: `seccomp=unconfined` for desktop functionality
- **Networking**: Bridge mode with port forwarding

## Data Persistence Strategy

### Directory Structure

```
/data/dev-workspace/ (ZFS Dataset)
├── webtop-config/          # Webtop application configuration
│   ├── ssl/               # HTTPS certificates
│   ├── .config/           # Desktop environment settings
│   └── Desktop/           # Desktop files and shortcuts
├── webtop-home/           # User home directory
│   ├── .bashrc           # Shell configuration
│   ├── .profile          # Environment variables
│   └── Downloads/        # Downloaded files
├── projects/              # Development projects
│   ├── homelab/          # Homelab automation code
│   ├── scripts/          # Utility scripts
│   └── documentation/    # Project documentation
└── shared/               # Files shared between environments
    ├── templates/        # Code templates
    ├── tools/            # Portable development tools
    └── backups/          # Configuration backups
```

### Backup Strategy

```bash
# Create ZFS snapshot before major changes
zfs snapshot local-2TB-zfs/dev-workspace@before-vscode-install

# List snapshots
zfs list -t snapshot | grep dev-workspace

# Rollback to snapshot if needed
zfs rollback local-2TB-zfs/dev-workspace@before-vscode-install

# Regular automated snapshots
# Add to cron: 0 */6 * * * zfs snapshot local-2TB-zfs/dev-workspace@$(date +\%Y\%m\%d-\%H\%M)
```

## Troubleshooting

### Container Won't Start

**Symptom**: Docker container exits immediately
**Check**: `pct exec 104 -- docker logs webtop`
**Common Issues**:
- Permission errors on mounted volumes
- Missing ZFS mount point
- Insufficient container resources

### HTTPS Certificate Errors

**Symptom**: Browser shows security warnings
**Solution**: Accept self-signed certificate or install custom CA
**Alternative**: Use HTTP on port 3000 (limited functionality)

### File Permission Issues

**Symptom**: Cannot create/modify files in mounted directories
**Check**: 
```bash
# Verify ownership in LXC
pct exec 104 -- ls -la /home/devdata/
# Should show 1000:1000 ownership

# Verify ownership on host  
ls -la /data/dev-workspace/
# Should show 101000:101000 ownership (LXC UID mapping)
```

### Network Connectivity Issues

**Symptom**: Cannot access Webtop via hostname
**Check**:
```bash
# DNS resolution
nslookup docker-webtop.maas

# Network connectivity
ping 192.168.4.230

# Port accessibility
telnet docker-webtop.maas 3001
```

### Storage Space Issues

**Symptom**: Out of space errors in development environment
**Check**:
```bash
# ZFS dataset usage
zfs list local-2TB-zfs/dev-workspace

# Container disk usage
pct exec 104 -- df -h

# Docker space usage
pct exec 104 -- docker system df
```

## Performance Optimization

### Resource Allocation

```bash
# Monitor resource usage
pct exec 104 -- htop

# Adjust container resources if needed
pct set 104 -memory 16384  # Increase to 16GB
pct set 104 -cores 8       # Increase to 8 cores
```

### ZFS Optimization

```bash
# Enable compression for source code
zfs set compression=lz4 local-2TB-zfs/dev-workspace

# Set appropriate record size for small files
zfs set recordsize=64K local-2TB-zfs/dev-workspace

# Monitor compression ratio
zfs get compressratio local-2TB-zfs/dev-workspace
```

## Security Considerations

### Network Security

- **Internal Access Only**: Webtop should not be exposed to the internet
- **HTTPS Required**: Use port 3001 for secure access
- **Firewall Rules**: Restrict access to trusted networks only

### Container Security

- **Unprivileged LXC**: Reduces attack surface
- **No Privileged Docker**: Avoid `--privileged` flag
- **Regular Updates**: Keep base images and packages updated

### Data Security

- **ZFS Encryption**: Consider enabling encryption at rest
- **Access Controls**: Implement proper file permissions
- **Backup Encryption**: Encrypt backup snapshots for offsite storage

## Development Workflow Integration

### IDE Integration

- **VS Code Server**: Install code-server for web-based VS Code
- **Remote Development**: Use VS Code remote containers extension
- **Git Configuration**: Set up SSH keys and Git configuration

### Project Management

- **Version Control**: Initialize Git repositories in `/home/abc/projects`
- **Documentation**: Use `/home/abc/shared` for shared documentation
- **Templates**: Store project templates in `/home/abc/shared/templates`

## Next Steps

1. **Install Development Tools**: VS Code, Node.js, Python, Docker CLI
2. **Configure Git**: Set up SSH keys and repository access
3. **Install Extensions**: Add useful VS Code extensions and tools
4. **Connect to Services**: Integrate with Ollama AI backend (192.168.4.81)
5. **Automate Backups**: Set up automated ZFS snapshot schedule

## References

- [LinuxServer.io Webtop Documentation](https://docs.linuxserver.io/images/docker-webtop)
- [Proxmox VE LXC Documentation](https://pve.proxmox.com/pve-docs/chapter-pct.html)
- [ZFS Administration Guide](https://openzfs.github.io/openzfs-docs/man/8/zfs.8.html)
- [Docker Volume Documentation](https://docs.docker.com/storage/volumes/)

---

*This setup provides a robust, scalable development environment with proper data persistence, security, and performance optimization. The external ZFS storage ensures that your development work is protected and portable across different container deployments.*