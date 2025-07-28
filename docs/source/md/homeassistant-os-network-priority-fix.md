# Home Assistant OS Network Interface Priority Fix

## Overview
This runbook documents how to fix DNS resolution issues in Home Assistant OS when multiple network interfaces cause the wrong interface to be used as the default route. This commonly occurs when Home Assistant has access to multiple networks but DNS queries need to go through a specific network.

## Problem Description

### Symptoms
- Home Assistant cannot resolve `.maas` domain hostnames (e.g., `frigate.maas`)
- DNS resolution works from other hosts on the same network
- Home Assistant has multiple network interfaces on different subnets
- Network connectivity exists between Home Assistant and target services

### Root Cause
Home Assistant OS automatically assigns default routes to all active interfaces, and the wrong interface may be selected as the primary default route. DNS queries follow the default route, so if the wrong interface is prioritized, DNS queries may go to a network where the DNS server doesn't exist.

### Example Scenario
```
Home Assistant VM with multiple interfaces:
- enp0s18: 192.168.4.240 (homelab network - has MAAS DNS at 192.168.4.53)
- enp0s19: 192.168.1.124 (different network - no MAAS DNS)  
- enp0s20: 192.168.86.22 (ISP network - uses ISP DNS)

Problem: DNS queries go through enp0s19 or enp0s20 instead of enp0s18
Solution: Set route metrics to prioritize enp0s18
```

## Prerequisites
- Home Assistant OS with console access
- Multiple network interfaces configured
- Basic understanding of networking concepts
- SSH access setup (see companion guide: homeassistant-os-ssh-access-setup.md)

## Diagnosis Steps

### Step 1: Identify the Problem
**Access Home Assistant console:**
```bash
# From terminal add-on
login
```

**Check current default routes:**
```bash
ip route show | grep default
```

**Example problematic output:**
```
default via 192.168.86.1 dev enp0s20 proto dhcp src 192.168.86.22 metric 100
default via 192.168.1.254 dev enp0s19 proto dhcp src 192.168.1.124 metric 101  
default via 192.168.4.1 dev enp0s18 proto dhcp src 192.168.4.240 metric 102
```

**Problem indicators:**
- Multiple default routes exist
- The desired network interface has a HIGHER metric number (lower priority)
- Wrong interface appears first in the list

### Step 2: Identify Network Interfaces
**Check interface details:**
```bash
ip addr show
```

**Example output:**
```
2: enp0s18: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP
    inet 192.168.4.240/24 brd 192.168.4.255 scope global dynamic noprefixroute enp0s18
3: enp0s19: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP  
    inet 192.168.1.124/24 brd 192.168.1.255 scope global dynamic noprefixroute enp0s19
4: enp0s20: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP
    inet 192.168.86.22/24 brd 192.168.86.255 scope global dynamic noprefixroute enp0s20
```

### Step 3: Test Current Default Interface
**Run Python test script:**
```bash
python3 -c "import socket; test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); test_sock.connect(('224.0.0.251', 1)); print('Default interface IP:', test_sock.getsockname()[0])"
```

**If output shows wrong IP (not the desired network), proceed with fix.**

## Implementation Steps

### Step 1: Access Root Shell
```bash
# From Home Assistant terminal add-on
login
```

### Step 2: Identify NetworkManager Connections
```bash
nmcli connection show
```

**Example output:**
```
NAME                UUID                                  TYPE      DEVICE
Supervisor enp0s20  7355c122-1706-3c72-b681-86ba326f2d4e  ethernet  enp0s20
Supervisor enp0s19  fa851b0a-fd3e-3924-8563-497ffa28a476  ethernet  enp0s19  
Supervisor enp0s18  ee1edc0b-350f-3211-869c-22c5ba611409  ethernet  enp0s18
```

### Step 3: Set Route Metrics (Lower = Higher Priority)
**Identify the target interface** (the one that should be default):
- In our example: `enp0s18` (192.168.4.240) should be default

**Set route metrics:**
```bash
# Set LOW metric (50) for desired default interface - HIGHEST PRIORITY
nmcli connection modify "Supervisor enp0s18" ipv4.route-metric 50

# Set HIGHER metrics for other interfaces - LOWER PRIORITY
nmcli connection modify "Supervisor enp0s19" ipv4.route-metric 200
nmcli connection modify "Supervisor enp0s20" ipv4.route-metric 300
```

### Step 4: Apply Configuration
```bash
# Reload NetworkManager configuration
nmcli connection reload

# Restart the primary connection
nmcli connection down "Supervisor enp0s18"
nmcli connection up "Supervisor enp0s18"
```

### Step 5: Reboot for Full Effect
```bash
reboot
```

**Wait 2-3 minutes for Home Assistant to fully restart.**

## Verification Steps

### Step 1: Access Console Again
```bash
# From terminal add-on after reboot
login
```

### Step 2: Verify Default Route Priority
```bash
ip route show | grep default
```

**Expected output (CORRECT):**
```
default via 192.168.4.1 dev enp0s18 proto dhcp src 192.168.4.240 metric 50
default via 192.168.1.254 dev enp0s19 proto dhcp src 192.168.1.124 metric 200
default via 192.168.86.1 dev enp0s20 proto dhcp src 192.168.86.22 metric 300
```

**Key indicators of success:**
- Desired interface (`enp0s18`) appears first
- Has lowest metric number (50)
- Other interfaces have higher metrics (200, 300)

### Step 3: Test Default Interface
```bash
python3 -c "import socket; test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); test_sock.connect(('224.0.0.251', 1)); print('Default interface IP:', test_sock.getsockname()[0])"
```

**Should output:** `Default interface IP: 192.168.4.240`

### Step 4: Test DNS Resolution
```bash
nslookup frigate.maas
```

**Expected output:**
```
Server:    192.168.4.53
Address:   192.168.4.53#53

Name:      frigate.maas  
Address:   192.168.4.241
```

### Step 5: Test Network Connectivity
```bash
ping -c 3 frigate.maas
```

**Should succeed with responses from 192.168.4.241**

## Troubleshooting

### Default Route Didn't Change
**Problem**: Route metrics didn't take effect

**Solutions:**
1. **Check if changes were saved:**
```bash
nmcli connection show "Supervisor enp0s18" | grep route-metric
```

2. **Manually restart all connections:**
```bash
nmcli connection down "Supervisor enp0s18"
nmcli connection down "Supervisor enp0s19"  
nmcli connection down "Supervisor enp0s20"
nmcli connection up "Supervisor enp0s18"
nmcli connection up "Supervisor enp0s19"
nmcli connection up "Supervisor enp0s20"
```

3. **Force reboot:**
```bash
reboot
```

### DNS Still Not Working
**Problem**: Default route is correct but DNS fails

**Solutions:**
1. **Check DNS server accessibility:**
```bash
ping -c 3 192.168.4.53  # MAAS DNS server
```

2. **Check specific DNS resolution:**
```bash
nslookup frigate.maas 192.168.4.53
```

3. **Verify MAAS DNS has the record:**
```bash
# From another host on 192.168.4.x network
nslookup frigate.maas
```

### Multiple Interfaces Still Have Same Priority
**Problem**: NetworkManager reassigned same metrics

**Solutions:**
1. **Use larger metric differences:**
```bash
nmcli connection modify "Supervisor enp0s18" ipv4.route-metric 10
nmcli connection modify "Supervisor enp0s19" ipv4.route-metric 500
nmcli connection modify "Supervisor enp0s20" ipv4.route-metric 1000
```

2. **Remove gateways from non-primary interfaces:**
```bash
nmcli connection modify "Supervisor enp0s19" ipv4.gateway ""
nmcli connection modify "Supervisor enp0s20" ipv4.gateway ""
```

## Rollback Procedure

### Remove Custom Route Metrics
If the configuration causes issues:
```bash
# Reset route metrics to automatic
nmcli connection modify "Supervisor enp0s18" ipv4.route-metric ""
nmcli connection modify "Supervisor enp0s19" ipv4.route-metric ""
nmcli connection modify "Supervisor enp0s20" ipv4.route-metric ""

# Reload configuration
nmcli connection reload

# Reboot
reboot
```

### Alternative: Delete and Recreate Connection
```bash
# Delete problematic connection
nmcli connection delete "Supervisor enp0s18"

# NetworkManager will automatically recreate it
# Or manually restart network service
systemctl restart NetworkManager
```

## Configuration Persistence

The route metric changes made with `nmcli` are persistent across reboots. NetworkManager stores the configuration and automatically applies it on startup.

**Configuration location:**
```bash
ls /etc/NetworkManager/system-connections/
```

## Advanced Configuration

### Set DNS Server Per Interface
```bash
# Set specific DNS server for primary interface
nmcli connection modify "Supervisor enp0s18" ipv4.dns "192.168.4.53"

# Clear DNS for other interfaces (use DHCP)
nmcli connection modify "Supervisor enp0s19" ipv4.dns ""
nmcli connection modify "Supervisor enp0s20" ipv4.dns ""
```

### Monitor Route Changes
```bash
# Watch routing table changes
watch -n 1 'ip route show | grep default'

# Monitor network connections
watch -n 5 'nmcli connection show --active'
```

## Related Issues

### GitHub Issue Reference
- [Cannot Change Which Is The Default Network Adapter for Home Assistant #81433](https://github.com/home-assistant/core/issues/81433)

**Key insight from issue:**
> "The default adapter is what the OS reports as default (usually the default route). core can't change what the operating system is reporting and does not manage the system's routing table."

This confirms that the fix must be applied at the OS level (NetworkManager), not within Home Assistant Core.

## Best Practices

1. **Always set significant differences** in route metrics (50, 200, 300 vs 100, 101, 102)
2. **Test after each change** to ensure expected behavior
3. **Document your network topology** to understand which interface should be default
4. **Monitor after Home Assistant OS updates** as network configuration might reset
5. **Keep backup of working configuration** for quick restoration

## Network Architecture Considerations

When designing multi-network Home Assistant deployments:

- **Primary network** should have lowest route metric
- **Management networks** should have higher metrics
- **Guest/IoT networks** should have highest metrics
- **DNS servers** should be accessible from primary network
- **Service discovery** works best with consistent default routes

## Summary

This fix resolves DNS resolution issues in multi-network Home Assistant OS deployments by properly configuring route metrics to ensure DNS queries use the correct network interface. The solution is persistent and doesn't require ongoing maintenance.