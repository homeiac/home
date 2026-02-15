# MAAS VM Power-Cut Recovery

## Overview

After a power cut, the MAAS VM (`192.168.4.53` on pve host VMID 102) may be down. Without MAAS:
- No DHCP on 192.168.4.x network
- Mac's USB adapter gets link-local 169.254.x.x instead of 192.168.4.x
- Cannot reach any homelab infrastructure

## Symptoms

- Mac USB adapter shows `169.254.x.x` address (link-local)
- Cannot ping any `192.168.4.x` hosts
- Mac WiFi still works (different network segment)

## Prerequisites

- Physical access to Mac with USB Ethernet adapter
- SSH key access to Proxmox hosts configured
- Knowledge of MAAS VM ID (102) on pve host (192.168.4.122)

## Recovery Steps

### Step 1: Identify USB Adapter Interface

```bash
# Find the USB ethernet adapter interface name
networksetup -listallhardwareports | grep -A2 "USB 10/100"

# Usually en10, verify current state
ifconfig en10
```

### Step 2: Manually Assign Static IP

```bash
# Use .250 from the reserved range to avoid conflicts
sudo ifconfig en10 192.168.4.250 netmask 255.255.255.0
```

### Step 3: Verify Connectivity to Proxmox Host

```bash
# Ping pve (the MAAS host)
ping -c 3 192.168.4.122

# If successful, you have layer 2 connectivity
```

### Step 4: Start MAAS VM

```bash
# SSH to pve and check/start MAAS VM
ssh root@192.168.4.122

# Inside pve:
qm status 102      # Check MAAS VM status
qm start 102       # Start if not running

# Or as one-liner:
ssh root@192.168.4.122 "qm status 102 && qm start 102"
```

### Step 5: Wait for MAAS Services

```bash
# Wait for MAAS VM to boot and respond
ping 192.168.4.53

# MAAS takes ~2-3 minutes to fully start all services
# Wait until ping responds consistently
```

### Step 6: Restore DHCP on Mac

```bash
# Release manual IP and get DHCP from MAAS
sudo ipconfig set en10 DHCP

# Verify proper IP assigned
ipconfig getifaddr en10
# Should show 192.168.4.x (not 169.254.x.x)
```

### Step 7: Verify Full Connectivity

```bash
# Test connectivity to other hosts
ping 192.168.4.17    # still-fawn
ping 192.168.4.175   # pumped-piglet
ping 192.168.4.19    # chief-horse (HAOS)

# Verify HAOS/Voice PE
curl -s http://192.168.4.19:8123/api/ | head
```

### Step 8: Verify pve is Plugged into UPS

**Physical check**: Ensure the pve host power cable is connected to a UPS battery-backed outlet (not surge-only).

Most UPS units have two outlet types:
- **Battery + Surge**: Keeps running during outage (use this for pve)
- **Surge Only**: No battery backup (for non-critical devices)

```bash
# After physical verification, check pve uptime to confirm it stayed up
ssh root@192.168.4.122 "uptime"

# If pve rebooted recently, it wasn't on UPS battery backup
# Check last boot time
ssh root@192.168.4.122 "who -b"
```

## Troubleshooting

### Cannot Ping pve After Static IP

1. Check cable connection
2. Verify USB adapter shows `status: active` in ifconfig
3. Try different IP: `sudo ifconfig en10 192.168.4.251 netmask 255.255.255.0`

### MAAS VM Won't Start

```bash
# Check VM config
ssh root@192.168.4.122 "qm config 102"

# Check for storage issues
ssh root@192.168.4.122 "pvesm status"

# Check logs
ssh root@192.168.4.122 "journalctl -u pve-guests --since '5 min ago'"
```

### MAAS Running But No DHCP

MAAS services may take time to start after boot:

```bash
# Check MAAS services inside VM
ssh root@192.168.4.122 "qm guest exec 102 -- systemctl status maas-regiond"
ssh root@192.168.4.122 "qm guest exec 102 -- systemctl status maas-rackd"

# Restart DHCP service if needed
ssh root@192.168.4.122 "qm guest exec 102 -- systemctl restart maas-dhcpd"
```

## Network Reference

| Host | IP | Notes |
|------|-----|-------|
| MAAS VM | 192.168.4.53 | VMID 102 on pve |
| pve | 192.168.4.122 | MAAS host |
| still-fawn | 192.168.4.17 | K3s VM host |
| pumped-piglet | 192.168.4.175 | K3s VM host |
| chief-horse | 192.168.4.19 | HAOS host |
| Mac static (temp) | 192.168.4.250 | Reserved range |

## Prevention

### 1. Set MAAS VM to Auto-Start

```bash
ssh root@192.168.4.122 "qm set 102 --onboot 1"
```

### 2. Configure UPS Monitoring on pve

Install and configure NUT (Network UPS Tools) for graceful shutdown:

```bash
# SSH to pve
ssh root@192.168.4.122

# Install NUT
apt update && apt install -y nut

# Find your UPS
lsusb | grep -i ups
# Example: Bus 001 Device 003: ID 051d:0002 American Power Conversion UPS

# Configure NUT driver (/etc/nut/ups.conf)
cat >> /etc/nut/ups.conf << 'EOF'
[ups]
    driver = usbhid-ups
    port = auto
    desc = "APC UPS"
EOF

# Configure NUT mode (/etc/nut/nut.conf)
sed -i 's/MODE=none/MODE=standalone/' /etc/nut/nut.conf

# Configure monitoring (/etc/nut/upsmon.conf)
echo 'MONITOR ups@localhost 1 admin secret master' >> /etc/nut/upsmon.conf
echo 'SHUTDOWNCMD "/sbin/shutdown -h +0"' >> /etc/nut/upsmon.conf

# Start services
systemctl enable nut-server nut-monitor
systemctl start nut-server nut-monitor

# Verify UPS is detected
upsc ups@localhost
```

### 3. Configure Graceful VM Shutdown

```bash
# Enable HA shutdown policy for critical VMs
ssh root@192.168.4.122 "qm set 102 --onboot 1 --startup order=1"
```

### 4. Document Boot Order Dependencies

Critical boot order:
1. pve host (physical)
2. MAAS VM (VMID 102) - provides DHCP
3. Other VMs/LXCs

## Tags

maas, dhcp, power-cut, recovery, network, proxmox, vmid-102, pve

---

*Last updated: 2025-02-15*
*Incident: Mac USB adapter getting link-local IP after power outage*
