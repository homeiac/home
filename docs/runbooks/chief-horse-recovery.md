# Runbook: chief-horse Proxmox Recovery

## Overview
Recovery steps for chief-horse Proxmox host when management services are unavailable.

## Quick Diagnosis

### Symptoms → Likely Cause

| Symptom | Likely Cause | Jump to |
|---------|--------------|---------|
| Ping works, SSH key fails, web UI down | pve-cluster stopped | [pve-cluster Recovery](#pve-cluster-recovery) |
| Ping fails | Network/hardware issue | [Physical Access](#physical-access-required) |
| SSH works, web UI "?" icons | pveproxy needs restart | [Restart Proxmox Services](#restart-proxmox-services) |
| HAOS not responding | VM stopped | [Start HAOS VM](#start-haos-vm) |

## Recovery Procedures

### pve-cluster Recovery

**Symptoms:**
- SSH key auth fails (password works)
- pveproxy logs: `failed to load local private key`
- `/etc/pve/` is empty
- `qm list` fails with `Connection refused`

**Steps:**
```bash
# 1. SSH with password
ssh root@192.168.4.19

# 2. Check pve-cluster status
systemctl status pve-cluster
# Expected if broken: "inactive (dead)"

# 3. Start pve-cluster
systemctl start pve-cluster

# 4. Verify /etc/pve is mounted
ls /etc/pve/
# Should show: nodes/, storage.cfg, corosync.conf, etc.

# 5. Check cluster status
pvecm status
# Should show: Quorate: Yes

# 6. Restart dependent services
systemctl restart pvedaemon pvestatd pveproxy
```

### Restart Proxmox Services

```bash
# Restart all management services
systemctl restart pve-cluster pvedaemon pvestatd pveproxy

# Verify web UI accessible
curl -k https://192.168.4.19:8006 -o /dev/null -w "%{http_code}"
# Expected: 200
```

### Start HAOS VM

```bash
# Check VM status
qm list
# VMID 116 = HAOS

# Start if stopped
qm start 116

# Wait for boot (60-90 seconds)
sleep 60

# Verify HAOS API (from Mac or another host)
curl -s http://192.168.4.240:8123/api/ -o /dev/null -w "%{http_code}"
# Expected: 401 (auth required = working)
```

### Physical Access Required

If ping fails:
1. Check network cables
2. Check power
3. Connect monitor/keyboard
4. Check BIOS/boot messages

## Host Information

| Property | Value |
|----------|-------|
| Hostname | chief-horse |
| IP (LAN) | 192.168.4.19 |
| Proxmox Web | https://192.168.4.19:8006 |
| SSH | root@192.168.4.19 |

### VMs on chief-horse

| VMID | Name | Purpose | Auto-start |
|------|------|---------|------------|
| 109 | k3s-vm-chief-horse | K3s node (unused) | No |
| 116 | haos16.0 | Home Assistant OS | Yes |

### Critical Service: HAOS

| Property | Value |
|----------|-------|
| VMID | 116 |
| IP | 192.168.4.240 |
| Web UI | http://192.168.4.240:8123 |
| API Check | `scripts/haos/check-ha-api.sh` |

## Post-Recovery Verification

```bash
# 1. Proxmox cluster healthy
pvecm status | grep -E "Quorate|Nodes"

# 2. All expected VMs visible
qm list

# 3. HAOS responding
curl -s http://192.168.4.240:8123/api/ -o /dev/null -w "%{http_code}"

# 4. Web UI accessible
curl -sk https://192.168.4.19:8006 -o /dev/null -w "%{http_code}"

# 5. Re-add SSH key if needed
ssh-copy-id root@192.168.4.19
```

## Related Documentation
- RCA: [2026-01-01-chief-horse-pve-cluster-stopped.md](../rca/2026-01-01-chief-horse-pve-cluster-stopped.md)
- Similar: [2025-10-04-still-fawn-pve-cluster-failure.md](../rca/2025-10-04-still-fawn-pve-cluster-failure.md)

## Tags
proxmox, chief-horse, haos, recovery, pve-cluster, runbook
