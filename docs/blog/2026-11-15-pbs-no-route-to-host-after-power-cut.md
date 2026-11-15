# "No Route to Host": A Power Cut, a One-Shot DHCP Client, and Four Months Without Backups

**Date:** 2026-11-15
**Tags:** proxmox, pbs, dhcp, maas, corosync, quorum, power-outage, rca, homelab

> A vzdump task emailed me `could not activate storage 'homelab-backup' ... Can't connect to 192.168.4.211:8007 (No route to host)`. The proximate cause took five minutes to find: Proxmox Backup Server booted while the DHCP server was still dark and never asked again. The real story was worse — PBS hadn't been *running* since July, and the power cut that broke it tonight was also what brought it back.

## TL;DR

- **Tonight's error:** after a power cut, PBS (LXC 103 on `pumped-piglet`) was auto-started at 02:12 UTC while MAAS — which serves DHCP *and* NTP from VM 102 on `pve` — was still coming up. Debian's `ifupdown` runs `dhclient` once, waits ~60 s, gives up, **releases**, and never retries. The container came up IPv6-only (SLAAC/DHCPv6 from the router still worked), so every node got *No route to host* on the IPv4 address in `storage.cfg`.
- **The bigger finding:** corosync logs show `pumped-piglet` sat in a 2-of-6-vote partition (`{fun-bedbug, pumped-piglet}`) from **2026-07-24 to 2026-11-15**. `pve-guests`' boot-time `startall` waits for quorum forever, so PBS and the GPU K3s VM (105) never started. **Newest backup in the datastore: 2026-07-21.**
- **Fix:** `scripts/backup/fix-pbs-network.sh` re-acquires the lease and installs a `dhcp-ipv4-watchdog` systemd timer inside the container that retries DHCP every 2 minutes whenever eth0 has no IPv4.

## Timeline (UTC)

| Time | Event |
|------|-------|
| 2026-07-21 22:30 | Last successful PBS backup (vm/105, vm/116). |
| 2026-07-22 → 07-24 | `pumped-piglet` reboots twice; current boot starts 07-24 04:03. |
| 2026-07-24 04:05 | corosync: `Members[2]: 5 6` — only fun-bedbug + pumped-piglet. Not quorate (needs 4 of 6). `startall` blocks. |
| *(114 days)* | PBS and VM 105 down. Nobody notices — no backup job could even fail, because the job never reached a quorate node with the storage up. |
| 2026-11-15 ~00:00–02:30 | Power cut. `pve`, `chief-horse`, `still-fawn` go down and come back. `pve`'s previous boot ends 02:17, current boot 02:32. MAAS (on `pve`) unreachable from 02:00. |
| 02:09:33 | `pve` (node 1) rejoins → `Members[3]: 1 5 6`. |
| 02:12:43 | chief-horse joins → 4 votes, **quorate**. |
| 02:12:44 | The 114-day-old `startall` finally proceeds: `vzstart:103`, `qmstart:105`. |
| 02:12:45–02:13:46 | PBS `dhclient`: six `DHCPDISCOVER`s, `No DHCPOFFERS received`, `DHCPRELEASE of 192.168.4.211`. eth0 left with IPv6 only. |
| 02:30 | Backup job `vzdump:105` runs → `could not activate storage 'homelab-backup' ... No route to host`. Email to root. |
| 07:22 | `fix-pbs-network.sh`: `DHCPACK of 192.168.4.211 from 192.168.4.53`. Storage `active` on every node. |

## Diagnosis, in order

1. **`ping 192.168.4.211`** — 100% loss. But `pct status 103` → `running`, and `proxmox-backup-proxy` was `active`. Service up, network down.
2. **`ip addr` inside the container** — two global IPv6 addresses, *no* `inet`. The `iface eth0 inet dhcp` stanza had silently failed.
3. **Container journal** — the whole story in ten lines:
   ```
   dhclient: DHCPDISCOVER on eth0 to 255.255.255.255 port 67 interval 6
   ... (x6)
   dhclient: No DHCPOFFERS received.
   networking: error: eth0: dhclient: timeout failed to detect new ip addresses
   dhclient: DHCPRELEASE of 192.168.4.211 on eth0 to 192.168.4.53 port 67
   ```
   `ifupdown` kills dhclient after its timeout. Nothing ever retries. `networking.service` still reports "Finished".
4. **Why was DHCP down?** MAAS (192.168.4.53) is a VM on `pve`, which was mid-reboot from the power cut. The host journal on `pumped-piglet` shows its own MAAS hardware-sync failing with `No route to host` to 192.168.4.53 at 02:00.
5. **Why did PBS start at 02:12, not at host boot?** `pvesh[3716]: Starting CT 103` — PID 3716 on a host with 114 days of uptime. That is the boot-time `pve-guests` process, and it had been waiting on quorum since July. `journalctl -b -u corosync | grep QUORUM` confirmed it.

## Root cause

Two independent latent faults, revealed by one power event:

1. **DHCP is one-shot at boot.** Any guest using `ifupdown` + DHCP that boots before MAAS is serving stays without IPv4 until someone intervenes. PBS is the worst possible victim: its storage definition is an IPv4 literal used by every node, and nothing on the PBS side looks broken (`systemctl` is green, IPv6 is up).
2. **A long-lived quorum partition went unmonitored.** For four months `pumped-piglet` could only see `fun-bedbug`. Nothing alerted. A boot-time `startall` that blocks forever is the documented PVE behaviour — but it means "the guests are set `onboot: 1`" is not the same as "the guests are running".

The power cut didn't cause the outage so much as end one and start another.

## The fix

### Immediate

```bash
scripts/backup/fix-pbs-network.sh --check   # read-only: IPv4, watchdog, port 8007, pvesm
scripts/backup/fix-pbs-network.sh           # repair lease + install watchdog (idempotent)
```

Result:
```
DHCPACK of 192.168.4.211 from 192.168.4.53
Container IPv4 on eth0: 192.168.4.211/24
PBS API 192.168.4.211:8007 reachable from pumped-piglet: yes
homelab-backup  pbs  active  2719365632  1891071360  828294272  69.54%
```
`pvesm status --storage homelab-backup` → `active` on still-fawn, chief-horse, fun-bedbug, pumped-piglet.

### Durable: a DHCP watchdog inside PBS

`scripts/backup/pbs-dhcp-watchdog/` — a systemd timer (`OnBootSec=2min`, `OnUnitActiveSec=2min`) running a 15-line script: if `eth0` has no IPv4, kill any stale v4 dhclient and run `dhclient -1` once. If MAAS is still down, the attempt fails and the timer tries again two minutes later. Worst-case recovery after MAAS returns: ~2 minutes, no human.

I chose this over a static IP in `pct config` because 192.168.4.211 is handed out by MAAS (it's recorded in the old lease file), and pinning it statically without a matching MAAS reservation risks a duplicate-IP conflict later. A static IP + MAAS reservation is still the cleaner end state — see follow-ups.

### Clock sanity across the cluster

MAAS also serves NTP, so a node that boots during a MAAS outage can start with a bad clock — and bad clocks make RCAs lie (my first read of `pumped-piglet`'s journal had me convinced it had rebooted). `scripts/proxmox/check-ntp-sync.sh` existed but had rotted:

- pumped-piglet's IP was `192.168.4.18` (it's `.175`); `pve` was missing entirely
- `#!/bin/bash` on macOS is bash 3.2 → `declare -A: invalid option`
- `((ISSUES++))` under `set -e` exits the script on the first issue found
- it only compared nodes to *each other*, so the whole cluster being wrong together would pass

Fixed all four, added a per-node check against the workstation clock and a `--fix` flag (`chronyc makestep`). Current result: all 5 reachable nodes synced, chrony offsets < 1 ms, ≤ 1 s skew between any pair.

## Lessons

- **"Service is active" ≠ "service is reachable".** PBS's own health was green the entire time. The only signal was on the *client* side.
- **Boot ordering after a power cut is a dependency graph you didn't draw.** DHCP, DNS and NTP all live in one VM on one host. Everything that boots faster than `pve` + MAAS is a candidate for this failure.
- **Blocking forever is a failure mode, not a wait.** A `startall` stuck for 114 days and a `dhclient` that gives up after 60 s are opposite bugs with the same result: guests that are "configured to run" but aren't.
- **Alert on absence.** No backup job failed for four months because none could run. A "newest PBS snapshot older than 48 h" alert would have caught this on July 23.

## Follow-ups

- [ ] **Run a full backup now** — nothing has been backed up since 2026-07-21: `ssh root@pumped-piglet.maas vzdump --all --storage homelab-backup --mode snapshot --exclude 103,108` (or wait for the next scheduled run of `backup-ff3d789f-f52b`).
- [ ] **Find why pumped-piglet was partitioned 07-24 → 11-15.** corosync showed `pmtud` dropping link MTU to 469 before rejoins — check the switch port / cabling to pumped-piglet and fun-bedbug.
- [ ] **Alert on quorum loss** and on **stale PBS snapshots** (> 48 h).
- [ ] Check whether VM 105 (GPU K3s node) being down since July was noticed elsewhere, and whether anything relied on it.
- [ ] Add a MAAS DHCP reservation for PBS (BC:24:11:AA:4D:60 → 192.168.4.211), then consider a static IP.
- [ ] Standardise host timezones (pve, still-fawn, fun-bedbug are PST; chief-horse, pumped-piglet are UTC) — mixed zones made this timeline harder to build.
- [ ] Apply the same DHCP watchdog to other `ifupdown`+DHCP LXCs that clients reach by IP.
