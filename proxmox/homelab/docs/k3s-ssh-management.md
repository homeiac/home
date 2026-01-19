# K3s VM SSH Management

## Overview

The K3s SSH management module provides automated configuration of SSH settings on K3s VMs to ensure password authentication works correctly.

## Problem

Ubuntu cloud images used for K3s VMs have conflicting SSH configuration files:
- `50-cloud-init.conf`: Sets `PasswordAuthentication yes`
- `60-cloudimg-settings.conf`: Sets `PasswordAuthentication no` (overrides)

The higher-numbered file (60) loads last and disables password authentication, even though cloud-init intends to enable it.

## Solution

The `K3sSSHManager` fixes this by modifying `60-cloudimg-settings.conf` to set `PasswordAuthentication yes` and restarting the SSH service.

## Usage

### Validate Current State

Check if password authentication is enabled on all K3s VMs:

```bash
cd proxmox/homelab
poetry run homelab k3s-ssh-validate
```

Check a specific VM:

```bash
poetry run homelab k3s-ssh-validate --vm k3s-vm-chief-horse
```

### Fix SSH Configuration

Enable password authentication on all K3s VMs:

```bash
poetry run homelab k3s-ssh-fix
```

Fix a specific VM:

```bash
poetry run homelab k3s-ssh-fix --vm k3s-vm-pve
```

## Features

- **Idempotent**: Safe to run multiple times, only makes changes if needed
- **Automated**: Works via `qm guest exec` without needing SSH access first
- **Validated**: Includes validation command to check current state
- **Logging**: Provides detailed feedback on operations

## Default VM Mapping

The module knows about these K3s VMs by default:

| VM Name | Proxmox Host | VMID |
|---------|--------------|------|
| k3s-vm-chief-horse | chief-horse | 109 |
| k3s-vm-pumped-piglet-gpu | pumped-piglet | 105 |
| k3s-vm-pve | pve | 107 |
| k3s-vm-still-fawn | still-fawn | 108 |

## Implementation Details

### Module Location

`proxmox/homelab/src/homelab/k3s_ssh_manager.py`

### Key Methods

- `enable_password_auth()`: Fix SSH config and restart SSH service
- `validate_password_auth()`: Check if password auth is enabled
- `get_vm_ips()`: Get IP addresses of all K3s VMs

### CLI Integration

Commands are integrated into the unified `homelab` CLI:

```bash
poetry run homelab --help
```

Available K3s SSH commands:
- `k3s-ssh-validate`: Validate SSH configuration
- `k3s-ssh-fix`: Fix SSH password authentication

## Security Considerations

- **Password not stored**: The module only enables password authentication, it does not set or store passwords
- **No credentials in code**: All SSH access uses existing root keys to Proxmox hosts
- **Idempotent operations**: Safe to run repeatedly without side effects

## Future Enhancements

Potential future improvements:

1. Auto-detect K3s VMs instead of hardcoded mapping
2. Integrate into `homelab validate` and `homelab apply` workflows
3. Add SSH key management (copy keys between VMs)
4. Support custom SSH configurations via YAML config
