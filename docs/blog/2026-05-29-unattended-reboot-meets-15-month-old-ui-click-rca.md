# An Unattended Reboot Met a 15-Month-Old UI Click

**Date:** 2026-05-29
**Tags:** proxmox, ceph, pve-cluster, systemd, unattended-upgrades, ssh, rca, homelab

> At 05:40 AM my Proxmox host `chief-horse` rebooted itself, applied some apt updates, and never came back the same way. Ten hours later I noticed Frigate was unreachable, Grafana was out, and my Voice PE greeting hadn't fired in days. The cause turned out to be a systemd ordering cycle planted by a "Install Ceph" button I clicked once in March 2025 — invisible for 15 months because nothing rebooted in a way that exercised it. The ceph cycle ate `pve-cluster.service`'s start job, which silently took down everything else: SSH key auth, `pveproxy`, the HAOS auto-start, and any management path that wasn't `ping`.

## TL;DR

`unattended-upgrades` triggered an orderly reboot at 05:40 AM on `chief-horse`. On the next boot, `systemd` detected a circular ordering between `ceph-mon@chief-horse.service` and `pve-cluster.service` and broke the cycle by **deleting the start job for `pve-cluster`**. Without `pve-cluster`, `/etc/pve` (the cluster's distributed filesystem) was never mounted. Without `/etc/pve`:

- `/root/.ssh/authorized_keys` (a symlink into `/etc/pve/priv/`) didn't exist → every SSH key auth attempt was rejected
- `pveproxy` couldn't read its certs → web UI dead (HTTP 000 on 8006)
- `qm` couldn't read VM configs → no VM management
- `pve-guests.service` couldn't run → HAOS (VM 116) wasn't auto-started

Manual remediation took ~20 minutes once I knew where to look — `password` SSH still worked (it doesn't need `authorized_keys`), and once I was in, `systemctl start pve-cluster` fixed everything in cascading order: `/etc/pve` mounted, key auth came back, `pveproxy` and `pvedaemon` started, `qm start 116` brought HAOS back.

Two other findings surfaced along the way: the Pixel 7 SMS gateway hotspot had been turned off since May 26, so the Frigate watchdog had been alerting every 30 minutes for ~11 hours into the void; and `pve` had the same orphan Ceph install as `chief-horse`, latent until its next reboot.

## Timeline (Pacific)

| Time | Event |
|------|-------|
| 2025-03-03 | Someone (probably me) clicked "Datacenter → Ceph → Install Ceph" on chief-horse's web UI. The installer ran `apt install ceph` and created `/etc/systemd/system/ceph-mon.target.wants/ceph-mon@chief-horse.service`. The configuration wizard was never finished. `/etc/ceph/` was never created. The service failed every boot. No one noticed because everything else kept working. |
| 2026-05-26 ~20:32 | Last successful Pixel 7 hotspot association. Hotspot toggle went off sometime after — for unrelated reasons. |
| 2026-05-29 05:36-39 | `pvescheduler` on chief-horse logs `cfs-lock 'file-replication_cfg' error: no quorum!` repeatedly for 4 minutes. (In hindsight: chief-horse was about to be shut down for the reboot; quorum was being lost as cluster comms went down.) |
| 2026-05-29 05:39:46 | `Stopping unattended-upgrades.service - Unattended Upgrades Shutdown...` — this is what triggered the reboot. apt config still had the default `Unattended-Upgrade::Automatic-Reboot "true"`. |
| 2026-05-29 05:39:53 | `pvesh: Stopping VM 116 (timeout = 180s)` — HAOS gracefully shut down. |
| 2026-05-29 05:40:31 | `systemd-poweroff.service` completes. `Reached target poweroff.target - System Power Off`. Clean shutdown. |
| 2026-05-29 05:41 | System boot. Kernel + networking come up. |
| 2026-05-29 05:41:38 | `systemd[1]: ceph-mon@chief-horse.service: Found ordering cycle on pve-cluster.service/start.` `systemd[1]: Job pve-cluster.service/start deleted to break ordering cycle.` Cluster filesystem will never mount this boot. |
| 2026-05-29 05:43:44 | corosync starts cleanly (no dependency on pve-cluster). chief-horse votes in cluster quorum from this point — *that's why everything looked superficially fine from the cluster's perspective for 10 hours.* |
| 2026-05-29 ~14:30 | User asks why HA Voice PE greeting hasn't fired. I check via Frigate API and notice Frigate is also unreachable. |
| 2026-05-29 ~14:45 | Frigate watchdog log shows it's been alerting every 30 min since ~03:25. `[WARN] SMS delivery failed - could not reach gateway` on every alert. Pixel 7 hotspot probe confirms `Pixel_7_2026` isn't broadcasting. |
| 2026-05-29 ~15:00 | Discover `pvecm status` from a working node sees chief-horse as a healthy cluster member (corosync vote). But every SSH attempt to chief-horse returns `Permission denied (publickey,password)`. pveproxy on chief-horse is dead too (`https://192.168.4.19:8006/` → HTTP 000). |
| 2026-05-29 ~15:20 | User confirms `ssh with password works`. Re-use existing `scripts/setup/copy-ssh-keys-to-proxmox.sh` (untracked, uses `expect` with `PROXMOX_ROOT_PASSWORD` from `.env`). `ssh-copy-id` reports `sh: 1: cannot create .ssh/authorized_keys: Directory nonexistent`. |
| 2026-05-29 15:26:39 | `systemctl start pve-cluster` on chief-horse via password SSH. `/etc/pve` mounts. `/etc/pve/priv/authorized_keys` becomes accessible. Cluster SSH trust restored immediately for all paths. |
| 2026-05-29 15:26:40 | `systemctl start pveproxy pvedaemon pvestatd pve-firewall pve-ha-crm pve-ha-lrm pvescheduler` — everything cascades up. `qm list` works. |
| 2026-05-29 15:27 | `qm start 116` — HAOS boots. `qm start 105` — Frigate's K3s node boots (separate problem: pumped-piglet's VM 105 had been stopped since ~03:30 for unrelated reasons; quorum issues from chief-horse going down had blocked earlier `qm start` attempts until chief-horse rejoined the cluster). |
| 2026-05-29 15:34 | HA UI at `http://192.168.1.124:8123/` returns HTTP 200. Voice PE / face-recognition pipeline back. |
| 2026-05-29 ~15:40 | Root cause located: `journalctl -u pve-cluster -b 0` shows the first start attempt was the manual 15:26 one. Searching wider: `Found ordering cycle on pve-cluster.service/start` at 05:41:38 on this boot. |
| 2026-05-29 ~15:50 | `apt purge ceph ceph-base ceph-mds ceph-mgr ceph-mgr-modules-core ceph-mon ceph-osd` on both affected hosts (`chief-horse` and `pve`). `systemd-analyze verify pve-cluster.service` returns clean. Failed-units list goes from 6 to 0 on chief-horse. |

## Root causes

### 1. The latent ordering cycle (Mar 2025 → May 2026)

`ceph-mon@<hostname>.service` declares dependencies that, on a Proxmox node where pmxcfs is the source of truth for cluster config, eventually circle back through `pve-cluster.service` for the host configuration it reads. As long as Ceph is actually configured (i.e. `/etc/ceph/` exists and ceph-mon can start), the cycle resolves in the normal direction at runtime. When Ceph is installed but **not** configured — a half-finished UI click — ceph-mon enters a failing-restart state, systemd notices it can't satisfy the dependency graph in one direction, and "breaks" the cycle by dropping the start job for the *other* end of it. Which happens to be `pve-cluster`.

This is operationally evil because:
- It only triggers on a fresh boot (a running system has both services in a stable state).
- The chosen victim (`pve-cluster`) is the *foundation* of every other Proxmox service on the host.
- The failure mode is silent — there's no "ALERT: PVE-CLUSTER NOT STARTED" anywhere; everything just doesn't work.
- corosync still runs (it doesn't depend on pve-cluster), so the cluster-as-a-whole sees the node as *online* with a healthy vote. From `pvecm status` on a remote node, chief-horse looked fine.

The Mar 3 2025 install left a `systemd` enablement symlink and 14 ceph packages (Ceph 16.2.15, full server suite — mon, mgr, mds, osd, fuse). The web UI's "Install Ceph" button is a one-click that runs `apt install ceph`. The configuration wizard is a separate step. If the user dismisses the wizard without finishing it, the packages stay, the enablement stays, the per-host `ceph-mon@<hostname>.service` stays — and the time bomb is armed.

I also had the same orphan install on `pve` from the same era; same hidden time bomb, just untriggered because `pve` hadn't rebooted in over a week.

### 2. Unattended auto-reboot, unsupervised

Debian's `unattended-upgrades` ships with `Automatic-Reboot "true"` enabled if a package update requires it (kernel updates, mostly). On a homelab where you don't have on-call rotation, this means a kernel update at 3 AM can reboot your hypervisor and you'll find out hours later when you happen to look.

For most Debian boxes that's fine. For a Proxmox host running the cluster filesystem your other hosts depend on, it isn't. The reboot itself was clean and the system itself recovered fine; what cost 10 hours was that the **post-reboot state** was unsupervised.

### 3. The alerting blind spot — Pixel 7 hotspot off

Independent of the chief-horse cascade: the [Frigate watchdog](2026-05-19-frigate-sms-spam-two-watchdogs-one-skip-list-rca.md) on `pve` had been doing its job perfectly — `[ALERT] Sent: Frigate STILL DOWN (570min)` every 30 minutes — and every single attempt had been logging `[WARN] SMS delivery failed - could not reach gateway`. The Pixel 7 hotspot (`Pixel_7_2026`, SSID for the out-of-band SMS gateway path) hadn't been associated with `wlan0` since May 26 at 8:32 PM. The phone was off, hotspot toggle off, or out of range.

`iwctl` showed wlan0 was happily connected to `wiremore2` (the home WiFi), but `10.181.204.183` (the Pixel 7's NAT subnet) is unreachable from there. The watchdog fell back to wlan0's default gateway — `192.168.86.1` (router), no SMS gateway there either.

Net effect: **the alerting subsystem was healthy and the symptom-detection subsystem was healthy. The delivery channel was the failure mode. And no part of the system noticed that the delivery channel was the failure mode.**

## What changed today

- ✅ `apt purge ceph ceph-base ceph-mds ceph-mgr ceph-mgr-modules-core ceph-mon ceph-osd` (+ autoremove) on `chief-horse` and `pve`. Ordering cycle eliminated on both. Failed-units list went from 6 → 0 on chief-horse. ~1 GB disk freed on each.
- ✅ Wrote `scripts/setup/disable-unattended-reboot.sh` and applied it to all reachable Proxmox hosts. Drops a `/etc/apt/apt.conf.d/52-no-auto-reboot` snippet setting `Unattended-Upgrade::Automatic-Reboot "false"`. Security updates still apply; reboots become opt-in.
- ✅ Committed `scripts/setup/copy-ssh-keys-to-proxmox.sh` (had been untracked) — the helper that uses `expect` + the `PROXMOX_ROOT_PASSWORD` from `.env` to repair SSH trust when the cluster's `authorized_keys` symlink isn't accessible. This is the script you reach for when `pve-cluster` is dead on a host.

## Open items

- [ ] **`fun-bedbug` is still down and hasn't been touched.** Per CLAUDE.md inventory it's flagged for thermal issues, so this may be expected. If it ever comes back, run `scripts/setup/disable-unattended-reboot.sh fun-bedbug.maas` and check for the orphan ceph install. (The script and the purge command are both safe to run on a clean host — they're idempotent / no-ops.)
- [ ] **Find and turn the Pixel 7 hotspot back on.** That was the actual root cause of "zero notifications" today, separate from chief-horse. Until that's restored, the watchdog will alert into the void on the next outage too.
- [ ] **Add a SMS-gateway health check.** The watchdog logs `SMS delivery failed` every alert but nothing else notices. Cheap fix: a daily `nut-notify`/`frigate-watchdog`-style dry-run that sends a test SMS and pages via ntfy.sh if delivery fails. (ntfy.sh is the canonical out-of-band channel that the 2026-05-18 RCA already established as reliable.)
- [ ] **Add a boot-time `systemctl --failed` check that pages.** Today, chief-horse came up with 6 failed units and the cluster-level view (`pvecm`) was happy. Some lightweight runbook-paging from a per-host cron would have caught this within 5 minutes instead of 10 hours.
- [ ] **Audit other Proxmox install-time UI clicks.** The pattern "click an install button → packages land → the wizard isn't finished → time bomb" probably applies to other features too (Ceph was just the example today). Worth a one-time grep for `*-pve` packages on each host that don't correspond to a configured feature.
- [ ] **Document the password-SSH path as the canonical escape hatch.** When the cluster filesystem is down on a node, `PROXMOX_ROOT_PASSWORD` in `proxmox/homelab/.env` is the only way back in. `scripts/setup/copy-ssh-keys-to-proxmox.sh` is the helper. This belongs in a runbook because it's the *exact* thing a future me will be panicking about not remembering.

## The meta-lesson

This is the third RCA in two weeks where the failure was **"a perfectly working alerting/management path turned out to depend on a thing that wasn't running."** The [2026-05-18 power outage RCA](2026-05-18-ups-plug-strikes-again-power-outage-rca.md) hit it with email-via-Grafana being structurally incapable of warning about a K3s outage. The [2026-05-19 SMS spam RCA](2026-05-19-frigate-sms-spam-two-watchdogs-one-skip-list-rca.md) hit it with two watchdogs needing to agree on a skip list with no mechanism forcing the agreement. Today's version: the chief-horse failure was invisible to every external observer (cluster quorum looked fine, ICMP worked, corosync vote present) but the *useful state* of the host — the parts you actually need to manage VMs and read configs — was gone.

There's a pattern here worth naming: **"surface-up, depth-down" failures.** The outermost signal (ping responds, vote counts, web UI on other nodes) says everything's fine. The innermost capability (run `qm`, mount the cluster filesystem, accept an SSH key) is dead. Every monitoring system I have is calibrated against the outer signal; none are calibrated against the inner capability.

The fix for that isn't another monitoring tool — it's writing the diagnostic *commands* down. "What's the actual question I need to ask to know if a Proxmox host is fully functional?" — `pvecm status`, `systemctl status pve-cluster`, `systemctl --failed`, `ls /etc/pve`, `qm list`. If I'd had a one-shot script per Proxmox host running those every 5 minutes and ntfy.sh-paging on any unexpected output, this would have been a 10-minute outage, not a 10-hour one.

---

*Related: [Same Lesson, Different Outage (Power Outage RCA)](2026-05-18-ups-plug-strikes-again-power-outage-rca.md), [Two Watchdogs, One Skip List (Frigate SMS Spam RCA)](2026-05-19-frigate-sms-spam-two-watchdogs-one-skip-list-rca.md), [Out-of-Band SMS Notifications for Homelab Disaster Recovery](../source/md/blog-out-of-band-sms-disaster-recovery.md)*
