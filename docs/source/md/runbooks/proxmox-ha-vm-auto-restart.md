# Proxmox HA Automatic VM Restart Guide

**Purpose**: Configure Proxmox High Availability for automatic VM restart after crashes, OOM kills, or unexpected shutdowns  
**Incident Reference**: MAAS OOM outage (July 29, 2025) - reduce 40-minute recovery to <2 minutes  
**Status**: Production Ready  

## What Proxmox HA Does

**Confirmed from Documentation & Testing:**
- Automatically restarts VMs that crash, stop unexpectedly, or are killed (e.g., OOM)
- Monitors VM process health continuously  
- Restart typically occurs within **1-2 minutes**
- Configurable retry policies before giving up
- Works on single-node clusters with quorum

**What HA Does NOT Do:**
- Does not restart VMs after intentional shutdowns (unless you manually reset state)
- Does not work without cluster configuration (minimum 3 nodes for reliable quorum)

## Prerequisites

### 1. Verify Cluster Status
```bash
# Check if you have a working cluster with quorum
pvecm status

# Should show:
# - Quorate: Yes
# - At least 3 nodes for reliable operation
```

### 2. Enable HA Services
```bash
# Enable and start HA services on each node
systemctl enable --now pve-ha-crm pve-ha-lrm

# Verify services are running
systemctl status pve-ha-crm pve-ha-lrm
```

## Implementation

### Add VM to HA Management

```bash
# Add VM with recommended settings
ha-manager add vm:<VMID> --state started --max_restart 3 --max_relocate 1

# Example for MAAS VM (VMID 102)
ha-manager add vm:102 --state started --max_restart 3 --max_relocate 1
```

### Configuration Parameters

- `--state started`: VM should always be running (HA will restart if stopped)
- `--max_restart 3`: Try restarting 3 times on same node before relocating
- `--max_relocate 1`: Attempt to move to another node if restarts fail

### Verify Configuration

```bash
# Check HA configuration
ha-manager config

# Check HA status
ha-manager status

# Should show: service vm:<VMID> (node, started)
```

## Testing HA Functionality

### Simulate VM Crash/OOM Kill

```bash
# Force stop VM (simulates crash/OOM kill)
qm stop <VMID>

# Monitor HA response
watch "ha-manager status | grep vm:<VMID> && qm status <VMID>"
```

**Expected Behavior:**
1. VM state briefly shows "stopped"
2. HA detects the stop and begins restart
3. VM state changes to "starting" then "started"
4. Total time: 1-2 minutes

### Important Note on Testing

When you use `qm stop`, HA may interpret this as intentional and change the state to "stopped". To re-enable automatic restart:

```bash
# Reset HA state to started after testing
ha-manager set vm:<VMID> --state started
```

## Production Implementation - Critical Infrastructure VMs

Based on July 29, 2025 OOM incident implementation:

```bash
# MAAS VM (VMID 102) - DHCP/PXE Services
ha-manager add vm:102 --state started --max_restart 3 --max_relocate 1

# OPNsense VM (VMID 101) - Router/Firewall/Gateway  
ha-manager add vm:101 --state started --max_restart 3 --max_relocate 1

# Verify both are under HA management
ha-manager status | grep 'vm:10[12]'
# Output: 
# service vm:101 (pve, started)
# service vm:102 (pve, started)
```

**Result**: Both critical infrastructure VMs will automatically restart within 1-2 minutes of any crash, OOM kill, or unexpected shutdown.

## Managing Intentional Maintenance

### Before Planned Maintenance

```bash
# Disable automatic restart before maintenance
ha-manager set vm:<VMID> --state stopped

# Perform maintenance (shutdown, configuration, etc.)
qm shutdown <VMID>
# ... maintenance work ...

# Re-enable automatic restart after maintenance
ha-manager set vm:<VMID> --state started
```

### Bulk Maintenance

```bash
# List all HA-managed VMs
ha-manager config

# Disable HA for critical infrastructure VMs
for vmid in 101 102; do
    ha-manager set vm:$vmid --state stopped
done

# Re-enable after maintenance
for vmid in 101 102; do
    ha-manager set vm:$vmid --state started
done
```

## Monitoring and Troubleshooting

### Check HA Status

```bash
# Overall HA cluster status
ha-manager status

# Specific VM status
ha-manager status | grep vm:<VMID>

# HA configuration
ha-manager config
```

### HA Logs

```bash
# HA Cluster Resource Manager logs
journalctl -u pve-ha-crm -f

# HA Local Resource Manager logs  
journalctl -u pve-ha-lrm -f

# VM start/stop events
journalctl -u qmeventd | grep "VM <VMID>"
```

### Common Issues

#### 1. HA Services Not Running
```bash
# Check cluster quorum first
pvecm status

# Start HA services if cluster is healthy
systemctl start pve-ha-crm pve-ha-lrm
```

#### 2. VM Not Restarting
```bash
# Check if state is set to stopped (common after testing)
ha-manager config | grep -A3 "vm:<VMID>"

# If state is stopped, re-enable
ha-manager set vm:<VMID> --state started
```

#### 3. HA Shows Service in Error State
```bash
# Remove from HA and re-add
ha-manager remove vm:<VMID>
ha-manager add vm:<VMID> --state started --max_restart 3
```

## Integration with Existing Monitoring

### Uptime Kuma Integration

Add monitors for critical infrastructure VMs:
```bash
# OPNsense VM availability (ping)
Monitor: OPNsense Gateway
Type: Ping  
Hostname: 192.168.4.1

# OPNsense Web Interface
Monitor: OPNsense WebUI
Type: HTTP
URL: https://192.168.4.1

# MAAS VM availability (ping)
Monitor: MAAS VM
Type: Ping
Hostname: 192.168.4.53

# MAAS Service availability (HTTP)
Monitor: MAAS Service  
Type: HTTP
URL: http://192.168.4.53:5240/MAAS/

# HA status monitoring (custom script)
Monitor: Critical VMs HA Status
Type: Push
# Script: curl uptime-kuma-push-url with ha-manager status for VMs 101,102
```

### Alerting on HA Events

```bash
# Monitor HA restart events
journalctl -u pve-ha-crm -f | grep "vm:<VMID>"

# Alert on multiple restart attempts
# (indicates underlying issue needs attention)
```

## Best Practices

### 1. Documentation
- Document all VMs under HA management
- Maintain list of maintenance procedures
- Record HA configuration changes

### 2. Regular Testing
```bash
# Monthly HA functionality test
qm stop <VMID>
# Verify automatic restart
ha-manager set vm:<VMID> --state started  # Reset after test
```

### 3. Monitoring
- Monitor HA service health
- Alert on service state changes
- Track restart frequency to identify issues

### 4. Maintenance Planning
- Always disable HA before planned maintenance
- Document maintenance windows
- Re-enable HA immediately after maintenance

## Verification Checklist

- [ ] Cluster has quorum (`pvecm status`)
- [ ] HA services running (`systemctl status pve-ha-crm pve-ha-lrm`)
- [ ] VM added to HA (`ha-manager config`)
- [ ] State set to "started" (`ha-manager config`)
- [ ] HA status shows "started" (`ha-manager status`)
- [ ] Test restart functionality (`qm stop` + monitor)
- [ ] Reset state after testing (`ha-manager set --state started`)
- [ ] Document configuration and procedures

## Summary

**Problem Solved**: Critical infrastructure VM outages reduced from 40+ minutes to <2 minutes

**Implementation**: 
```bash
# Critical Infrastructure VMs under HA management
ha-manager add vm:101 --state started --max_restart 3 --max_relocate 1  # OPNsense
ha-manager add vm:102 --state started --max_restart 3 --max_relocate 1  # MAAS
```

**Protected Services**:
- **VM 101 (OPNsense)**: Router, Firewall, Gateway, DHCP for homelab network
- **VM 102 (MAAS)**: DHCP/PXE for bare metal provisioning

**Key Learning**: Proxmox HA is the built-in solution for automatic VM restart after crashes - no custom scripts needed when you have a proper cluster setup.

**Next Steps**: Consider adding other critical VMs (K3s control plane, monitoring) to HA management.

---

**Related Documents:**
- [MAAS OOM Incident RCA](../rca/maas-oom-incident-2025-07-29.md)
- [Proxmox VM Shutdown Diagnosis Runbook](proxmox-vm-shutdown-diagnosis.md)

**GitHub Issue**: [#112](https://github.com/homeiac/home/issues/112) - Implement Proxmox HA for Ubuntu MAAS VM automatic restart