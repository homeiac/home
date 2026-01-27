# RCA: fun-bedbug K3s VM Re-enable After Thermal Paste Replacement

**Date:** 2026-01-27
**Duration:** ~15 minutes (D-Bus fix + etcd cleanup)
**Severity:** Low (no production impact)
**Root Cause Category:** D-Bus service not running after reboot + stale etcd data

---

## Summary

Successfully re-enabled the K3s control plane VM on fun-bedbug (VMID 114) via Crossplane GitOps. The node had been disabled since 2026-01-25 due to thermal issues (92°C+ under load). After cleaning and applying new thermal paste, temperatures dropped dramatically, allowing the node to rejoin the cluster.

**Temperature improvement: 92°C → 54.5°C (37.5°C reduction)**

**Bonus: No more fan noise.** The internal fan was constantly at max RPM trying to cool the overheating APU. Now runs quietly.

---

## Timeline

| Time (PST) | Event |
|------------|-------|
| 2026-01-18 | K3s VM on fun-bedbug disabled due to thermal throttling (92°C) |
| 2026-01-25 | VM formally stopped via Crossplane (`started: false`) |
| 2026-01-26 | Physical maintenance: case cleaning + thermal paste replacement |
| 2026-01-27 13:00 | Crossplane GitOps change pushed (`started: true`) |
| 2026-01-27 13:06 | Crossplane failed to start VM - D-Bus socket missing |
| 2026-01-27 13:14 | D-Bus service started manually |
| 2026-01-27 13:14 | VM started, K3s began joining cluster |
| 2026-01-27 13:15 | etcd join failed - stale etcd data from previous attempt |
| 2026-01-27 13:16 | Cleared etcd data, K3s restarted |
| 2026-01-27 13:17 | Node joined cluster successfully |
| 2026-01-27 13:18 | Crossplane reconciled, showing SYNCED: True |

---

## Technical Details

### Issue 1: D-Bus Service Not Running

**Symptom:**
```
org.freedesktop.DBus.Error.FileNotFound: Failed to connect to socket /run/dbus/system_bus_socket: No such file or directory
```

**Root Cause:**
- D-Bus was stopped during a reboot on Jan 26
- Socket activation (`dbus.socket`) failed to trigger D-Bus on the Jan 26 15:40 boot
- Proxmox services (pvedaemon) started before D-Bus was activated
- `qm start` requires D-Bus for inter-process communication

**Resolution:**
```bash
ssh root@fun-bedbug.maas "systemctl start dbus"
```

**Why D-Bus Wasn't Auto-Started:**
- D-Bus uses socket activation (no `WantedBy=` in unit file)
- Something in the boot sequence bypassed socket activation
- Likely a race condition between pvedaemon and dbus.socket

### Issue 2: Stale etcd Data

**Symptom:**
```
Failed to test etcd connection: failed to get etcd status: rpc error: code = Unavailable desc = connection error: desc = "transport: authentication handshake failed: context deadline exceeded"
```

**Root Cause:**
- Previous K3s join attempts (Jan 16-18) left etcd data in `/var/lib/rancher/k3s/server/db/etcd/`
- The stale data contained invalid member IDs and certificates
- K3s couldn't rejoin with mismatched etcd state

**Resolution:**
```bash
ssh root@fun-bedbug.maas "qm guest exec 114 -- bash -c 'systemctl stop k3s && rm -rf /var/lib/rancher/k3s/server/db/etcd/* && systemctl start k3s'"
```

---

## Thermal Improvement Results

### Before (2026-01-18)
| Metric | Value |
|--------|-------|
| Temperature | 92°C (critical threshold: 100°C) |
| vCPUs | 2 |
| Load Average | 2.90 |
| Status | Thermal throttling, VM disabled |

### After Thermal Paste Replacement (2026-01-27)
| Metric | Value |
|--------|-------|
| Temperature | **54.5°C** (normal threshold: 70°C) |
| vCPUs | 1 |
| Load Average | 0.18 |
| Status | Running, joined cluster |

**Temperature delta: -37.5°C**

The ATOPNUC MA90's AMD A9-9400 APU (2016 Bristol Ridge, 15W TDP) was likely suffering from dried-out original thermal paste after years of operation.

**Side benefit:** The internal fan no longer runs at max RPM constantly. Before the thermal paste replacement, the fan was audibly struggling to keep up, creating noticeable noise in the homelab. Now the unit runs quietly.

---

## Current Cluster State

```
NAME                       STATUS   ROLES                       AGE     INTERNAL-IP
k3s-vm-fun-bedbug          Ready    control-plane,etcd          27s     192.168.4.192
k3s-vm-pumped-piglet-gpu   Ready    control-plane,etcd,master   3d14h   192.168.4.210
k3s-vm-pve                 Ready    control-plane,etcd          46h     192.168.4.193
k3s-vm-still-fawn          Ready    control-plane,etcd,master   3d14h   192.168.4.212
```

4-node K3s cluster with all nodes as control-plane + etcd members.

---

## Lessons Learned

### 1. D-Bus Socket Activation is Not Reliable on fun-bedbug

**Action:** Consider adding explicit D-Bus startup to Proxmox boot sequence or monitoring for missing D-Bus socket.

### 2. Clear etcd Data Before Rejoining After Long Outage

**Action:** When a K3s control-plane node has been offline for days, clear etcd state before rejoining:
```bash
rm -rf /var/lib/rancher/k3s/server/db/etcd/*
```

### 3. Thermal Paste Replacement is Worth It for Old Hardware

**Action:** The dramatic 37.5°C improvement justifies the effort. Consider thermal paste replacement for other aging homelab hardware.

---

## Prevention

| Item | Action |
|------|--------|
| D-Bus monitoring | Add check for `/run/dbus/system_bus_socket` existence in host health checks |
| etcd cleanup script | Create snippet that clears etcd before K3s start on cold boot |
| Thermal monitoring | Alert if fun-bedbug exceeds 70°C |

---

## Related

- Crossplane VM config: `gitops/clusters/homelab/instances/k3s-vm-fun-bedbug.yaml`
- Thermal runbook: `docs/runbooks/fun-bedbug-thermal-management.md`
- Cloud-init snippet: `scripts/k3s/snippets/k3s-server-fun-bedbug.yaml`

**Tags:** fun-bedbug, k3s, crossplane, dbus, etcd, thermal, thermal-paste, proxmox, atopnuc, amd-a9
