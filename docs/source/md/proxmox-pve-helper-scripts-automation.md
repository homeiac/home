# Proxmox VE Helper Scripts Automation Guide

This document explains how to automate the Proxmox VE Helper Scripts (community-scripts/ProxmoxVE) for unattended LXC container creation.

## Overview

The Proxmox VE Helper Scripts are community-maintained bash scripts that simplify the creation of LXC containers with pre-configured applications. However, they are designed for interactive use with whiptail dialog boxes. This guide shows how to bypass the interactive prompts for automation.

## The Challenge

The helper scripts present multiple challenges for automation:

1. **SSH Detection**: Scripts detect SSH sessions and require confirmation
2. **Interactive Dialogs**: 20+ whiptail dialog boxes for configuration
3. **Storage Selection**: Complex storage pool selection logic
4. **Dynamic Configuration**: Different applications have different dialog sequences

## Solution: Environment Variable Override Method

After extensive research and testing, the most reliable automation method uses environment variables to override default values and bypass specific dialogs.

### Key Discovery: Environment Variable Bypass

The helper scripts check for preset environment variables before showing certain dialogs:

```bash
# From create_lxc.sh line 110-119
if [ "$CONTENT" = "rootdir" ] && [ -n "${STORAGE:-}" ]; then
  if pvesm status -content "$CONTENT" | awk 'NR>1 {print $1}' | grep -qx "$STORAGE"; then
    STORAGE_RESULT="$STORAGE"
    msg_info "Using preset storage: $STORAGE_RESULT for $CONTENT_LABEL"
    return 0
  fi
fi
```

### Critical Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `STORAGE` | Bypasses storage selection dialog | `local-2TB-zfs` |
| `var_disk` | Sets disk size in GB | `50` |
| `var_ram` | Sets RAM in MB | `8192` |
| `var_cpu` | Sets CPU cores | `4` |
| `var_unprivileged` | Sets container type | `1` |

### SSH Environment Bypass

The scripts detect SSH sessions through these environment variables:
- `SSH_CLIENT`
- `SSH_CONNECTION` 
- `SSH_TTY`

These must be unset to bypass SSH detection dialogs.

## Working Automation Script

```bash
#!/bin/bash
# proxmox-lxc-auto-create.sh
# Automated LXC container creation using PVE Helper Scripts

set -e

# Configuration
CONTAINER_ID="104"
HOSTNAME="docker-webtop" 
DISK_SIZE="50"
RAM_MB="8192"
CPU_CORES="4"
STORAGE_POOL="local-2TB-zfs"
SCRIPT_URL="https://github.com/community-scripts/ProxmoxVE/raw/main/ct/docker.sh"

# Check if container ID already exists
if pct status "$CONTAINER_ID" &>/dev/null; then
    echo "Container $CONTAINER_ID already exists"
    exit 1
fi

# Execute with environment overrides
export STORAGE="$STORAGE_POOL"
export var_disk="$DISK_SIZE"
export var_ram="$RAM_MB"
export var_cpu="$CPU_CORES"
export var_unprivileged="1"

# Remove SSH environment variables to bypass detection
unset SSH_CLIENT SSH_CONNECTION SSH_TTY

# Download and execute script
curl -fsSL "$SCRIPT_URL" | bash

echo "Container $CONTAINER_ID created successfully"
echo "Access via: pct enter $CONTAINER_ID"
```

## Alternative Methods Attempted

### 1. Expect Script Automation ❌

Attempted to automate whiptail dialogs using expect scripts:

```bash
#!/usr/bin/expect -f
set timeout 30
spawn bash -c "curl -fsSL https://github.com/community-scripts/ProxmoxVE/raw/main/ct/docker.sh | bash"

expect "*SSH DETECTED*" {
    send "\033\[D\r"  # Left arrow to select "Yes"
}
# ... 20+ more dialog expectations
```

**Issues:**
- Fragile dialog detection
- Different scripts have different sequences
- SSH detection still problematic
- Timeouts and race conditions

### 2. Configuration File Method ❌

Some scripts support a "Use Config File" option:

```bash
# config.conf
CTID=104
CTNAME=docker-webtop
CORES=4
RAM=8192
DISK_SIZE=50
```

**Issues:**
- Not all scripts support config files
- SSH detection bypass still required
- Limited configuration options
- Inconsistent implementation

### 3. Direct pct create ❌

Manual LXC creation bypassing helper scripts entirely:

```bash
pct create 104 local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst \
  --hostname docker-webtop \
  --memory 8192 \
  --cores 4 \
  --rootfs local-2TB-zfs:50
```

**Issues:**
- Loses all the value-add of helper scripts
- No application-specific configuration
- Manual Docker installation required
- Missing networking and security setup

## Best Practices

### 1. Environment Preparation

Always prepare the environment before script execution:

```bash
# Set required variables
export STORAGE="your-storage-pool"
export var_disk="50"
export var_ram="8192" 
export var_cpu="4"
export var_unprivileged="1"

# Clean SSH environment
unset SSH_CLIENT SSH_CONNECTION SSH_TTY
```

### 2. Error Handling

Include proper error checking:

```bash
# Verify storage pool exists
if ! pvesm status | grep -q "^$STORAGE_POOL"; then
    echo "Error: Storage pool $STORAGE_POOL not found"
    exit 1
fi

# Check available space
FREE_SPACE=$(pvesm status | awk -v pool="$STORAGE_POOL" '$1 == pool { print $6 }')
REQUIRED_KB=$((DISK_SIZE * 1024 * 1024))
if [ "$FREE_SPACE" -lt "$REQUIRED_KB" ]; then
    echo "Error: Insufficient space on $STORAGE_POOL"
    exit 1
fi
```

### 3. Verification

Always verify successful container creation:

```bash
# Wait for container to appear
for i in {1..30}; do
    if pct list | grep -q "^$CONTAINER_ID"; then
        echo "Container $CONTAINER_ID created successfully"
        break
    fi
    sleep 2
done

# Verify container configuration
pct config "$CONTAINER_ID"
```

## Script-Specific Considerations

### Docker Script

The Docker helper script (ct/docker.sh) has these defaults:

```bash
var_cpu="${var_cpu:-2}"        # Default 2 cores
var_ram="${var_ram:-2048}"     # Default 2GB RAM  
var_disk="${var_disk:-4}"      # Default 4GB disk
var_unprivileged="${var_unprivileged:-1}"  # Default unprivileged
```

Always override these for production use:

```bash
export var_cpu="4"      # Adequate for development
export var_ram="8192"   # 8GB for Docker containers
export var_disk="50"    # 50GB for projects and images
```

### Networking Configuration

Helper scripts typically configure DHCP networking. For static IPs, modify after creation:

```bash
# Set static IP after container creation
pct set "$CONTAINER_ID" -net0 name=eth0,bridge=vmbr0,ip=192.168.4.104/24,gw=192.168.4.1
```

## Troubleshooting

### Script Hangs on Storage Selection

**Symptom**: Script stops at storage selection dialog
**Solution**: Ensure `STORAGE` environment variable is set to valid storage pool

### SSH Detection Blocks Automation  

**Symptom**: Script exits with "Exiting due to SSH usage"
**Solution**: Unset all SSH environment variables before execution

### Container Creation Fails

**Symptom**: Script completes but container not created
**Solution**: Check Proxmox logs and verify storage pool availability

### Permission Errors

**Symptom**: "Operation not permitted" during container setup
**Solution**: Ensure script runs as root on Proxmox host

## Limitations

1. **Script Dependencies**: Method relies on internal script implementation
2. **Version Sensitivity**: Updates to helper scripts may break automation
3. **Limited Customization**: Some advanced options still require manual configuration
4. **Single Host**: Automation must run directly on Proxmox host

## Future Improvements

1. **API Integration**: Develop Proxmox API-based alternative
2. **Template System**: Create reusable container templates
3. **Configuration Management**: Integrate with infrastructure-as-code tools
4. **Monitoring**: Add automated verification and rollback capabilities

## References

- [Proxmox VE Helper Scripts Repository](https://github.com/community-scripts/ProxmoxVE)
- [Proxmox VE LXC Documentation](https://pve.proxmox.com/pve-docs/chapter-pct.html)
- [LXC Container Configuration](https://linuxcontainers.org/lxc/manpages/man5/lxc.container.conf.5.html)

---

*This automation method was developed through extensive testing and analysis of the helper script source code. While reliable, it should be tested thoroughly in development environments before production use.*