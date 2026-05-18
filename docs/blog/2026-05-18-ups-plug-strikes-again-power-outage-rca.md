# Same Lesson, Different Outage: The UPS Plug Strikes Again

**Date:** 2026-05-18
**Tags:** ups, nut, power-outage, rca, homelab, k3s, etcd, frigate, lessons-learned

> Three months ago I wrote [a blog post](../source/md/blog-ups-homelab-lesson-learned.md) about discovering pve was plugged into a surge-only outlet on my CyberPower CP1500. I learned the lesson. I documented the lesson. Then I unplugged things to move stuff around, plugged them back in, and re-learned the lesson the hard way.

## TL;DR

Power cut overnight. Most of the homelab came back automatically thanks to BIOS "Last State". pve didn't, because it was on a surge-only UPS outlet *again*. That cascaded: pve's MAAS VM wouldn't auto-start without pve → no DHCP/DNS → my Mac couldn't even reach the LAN. Once I physically power-cycled pve, a second latent bug emerged — `k3s-vm-pve` (VMID 107) had `onboot: 0`, so the K3s control-plane VM didn't auto-start either. That left etcd with 2/4 members → no quorum → K3s API unreachable → Frigate `HTTP 503 no available server`. Fix sequence took ~10 minutes once the cause was clear. Documented and committed the fixes the same morning.

## Timeline (Pacific)

| Time | Event |
|------|-------|
| ~22:00 (prior night) | Power outage begins |
| ~05:11 | AC restored. fun-bedbug, chief-horse, pumped-piglet auto-boot (BIOS Last State) |
| ~05:11 | pve **does not auto-boot** (was on surge-only outlet — never lost UPS power because it never had any, but BIOS post-boot policy may also not be "Last State") |
| ~08:07 | User physically power-cycles pve |
| ~14:00 | User opens a session: "is my cluster running, especially frigate?" |
| 14:05 | Mac shows `169.254.x.x` link-local; can't reach the homelab. False alarm: it's my Mac, not the cluster |
| 14:08 | DHCP renewed; Mac on 192.168.4.226. Real diagnosis begins |
| 14:10 | API shows `k3s-vm-pve` (VMID 107) stopped, `k3s-vm-still-fawn` (VMID 108) unknown |
| 14:11 | kubectl returns `ServiceUnavailable: the server is currently unable to handle the request` → etcd no quorum |
| 14:14 | `qm config 107` shows `onboot: 0` — root cause identified |
| 14:15 | `qm start 107 && qm set 107 --onboot 1` |
| 14:16 | K3s API back, all 4 nodes Ready |
| 14:16 | Frigate `HTTP 200`, 21.3 detection fps |
| 14:30 | 4 stuck pods (3 GPU workloads in `UnexpectedAdmissionError`, 1 metrics-server `Unknown`) force-deleted, replacements scheduled |

## Recovery

```
fun-bedbug      booted 05:11   (uptime 10h19m at diagnosis time)
chief-horse     booted 05:12   (uptime 10h18m)
pumped-piglet   booted 05:12   (uptime 10h18m)
pve             booted 08:07   ← 3 hours late, manual intervention
still-fawn      transient down → back
```

The 3-hour gap between pve and the rest is the signature of the bug: BIOS "Last State" worked everywhere it was configured, and didn't help on pve.

## Why no alert fired

Two alert paths are designed; neither delivered.

1. **Email via Prometheus → Grafana → Yahoo SMTP** ([docs/source/md/monitoring-alerting-guide.md](../source/md/monitoring-alerting-guide.md))
   - Prometheus runs on K3s. K3s went down with the cluster. Prometheus has node affinity to `k3s-vm-still-fawn`. Even if K3s had stayed up, this path also needs internet, which is the first thing to die in any real power outage.
   - **The email path is architecturally incapable of warning you about an outage that takes down K3s.**

2. **Out-of-band SMS via Pixel 7 hotspot** ([docs/source/md/blog-out-of-band-sms-disaster-recovery.md](../source/md/blog-out-of-band-sms-disaster-recovery.md))
   - The deployed `nut-notify.sh` has the SMS code. Secrets are in `sms-gateway-creds.sops.yaml`. Vars are present in `/opt/nut/.env` on pve. So the path is wired.
   - But `NUT never saw an ONBATT event` — `/var/log/nut-notify.log` doesn't exist, journalctl has zero `ONBATT`/`LOWBATT` entries for pve.
   - That means the script never ran, which means upsmon never observed the UPS going to battery. Because pve wasn't on the UPS. Same as February.

The only thing that did work in the test: a fake-ONBATT dry-run today confirmed **ntfy.sh push notifications deliver successfully** (message id `gRntAglIcn1Q`). Subscribe to `homelab-pve-ups-alerts` on your phone — that's the most reliable channel right now.

## A confusing 60-second detour: legacy scripts

While diagnosing I read `scripts/pve/nut-notify.sh` and concluded the SMS path wasn't implemented. Wrong file. The deployed script is `scripts/pve-nut/scripts/nut-notify.sh`, packaged into the `ghcr.io/homeiac/pve-nut` image and pushed to pve by a K8s Job. The deployed copy already has SMS + ntfy code. The `scripts/pve/` files are pre-GitOps leftovers.

That bait-and-switch is exactly the kind of thing that wastes time during incidents. Deleted as part of this cleanup (#189). If you're an AI agent reading this in a future session: **`scripts/pve-nut/` is the source of truth**, ignore anything in `scripts/pve/` that ends in `-nut.sh`.

## Root causes

1. **pve plugged into surge-only outlet on the CyberPower CP1500.** Recurring physical mistake (Feb 2026 + May 2026). The CP1500's outlets are not visually distinct enough — the bank label is on the back of the unit. There is no software detection because the CP1500 doesn't expose per-outlet state.

2. **`k3s-vm-pve` (VMID 107) had `onboot: 0`.** Latent for an unknown duration — it survived 91 days of uptime before the outage exposed it. With the rest of the etcd cluster down to 2/4 quorum, this was the difference between "cluster comes back when pve does" and "cluster needs manual intervention even after pve is up."

3. **Alerting depends on the thing it's meant to warn about.** The email path runs through K3s; K3s goes down with the cluster. Acknowledged design limitation; the SMS + ntfy paths exist as the out-of-band layer, but only ntfy is testable without an actual outage.

## What changed today

- ✅ pve's power cable moved to a battery-backed outlet (the only real fix)
- ✅ `qm set 107 --onboot 1` — VMID 107 will auto-start on next pve boot
- ✅ End-to-end notification dry-run (fake ONBATT) — ntfy.sh confirmed working, SMS leg dry but path exercised
- ✅ Cleanup [#189](https://github.com/homeiac/home/issues/189) — removed `scripts/pve/{nut-notify.sh,setup-nut.sh,test-nut-status.sh}` to stop misleading future readers, including two hardcoded NUT auth passwords (`nutadmin`, `upsmonpass`) that were always a CLAUDE.md prime-directive violation
- ✅ Stuck pods force-deleted; replacements running on `k3s-vm-pumped-piglet-gpu`

## Open items

- [ ] **Physically label the CP1500 outlets** — "BATT" stickers on the left bank. Make the right thing obvious to your hands, not just to your docs.
- [ ] **Verify BIOS "Restore on AC Power Loss = Last State" on pve.** Other Proxmox hosts have it (proven empirically by today's outage); pve apparently does not.
- [ ] **Quarterly disaster drill.** [docs/runbooks/nut-tiered-shutdown.md:317](../runbooks/nut-tiered-shutdown.md:317) already calls for annual; the cron at `/etc/cron.d/nut-disaster-drill` runs first Saturday of each month. Confirm it actually executes and the SMS path lights up the next time it does.
- [ ] **Pin Prometheus off `k3s-vm-still-fawn`** OR accept that the email-via-Grafana alert path cannot survive an outage that takes the cluster down — and rely on ntfy/SMS as the canonical channels.
- [ ] **Rotate NUT internal passwords** (`nutadmin`, `upsmonpass`) since they were in git history.

## Lesson re-learned

The Feb 2026 post ended with: *"Next power outage, I'll be drinking coffee while my homelab rides it out."* This one didn't go quite that smoothly. The wiring regressed during a furniture rearrangement (or a cable swap, or just absent-minded outlet selection — I genuinely don't remember when it moved).

The real lesson isn't "don't make this mistake." Lesson #2 from this incident: **docs aren't a substitute for physical affordances.** A runbook that explains which outlets are battery-backed is useful — but a sticker on the front of the UPS is more useful, because it's right there in front of you at the moment you're plugging things in. The plug regression happened because the right thing wasn't obvious to my hands.

The other lesson: **alert paths need to survive the thing they're alerting about.** Anyone designing alerting for an outage has to start with the question "what's still on, and what runs there?" My answer right now is: a Pixel 7 with a cellular connection. That's the only piece guaranteed to survive a whole-house power cut. Anything that needs the homelab to be partially up is by definition a degraded path.

---

*Related: [The UPS That Wasn't: A Homelab Lesson](../source/md/blog-ups-homelab-lesson-learned.md) (2026-02-15), [Turning a Power Outage Scare into GitOps Gold](2026-02-15-ups-monitoring-gitops-disaster-to-opportunity.md), [Out-of-Band SMS Notifications for Homelab Disaster Recovery](../source/md/blog-out-of-band-sms-disaster-recovery.md), [NUT Tiered Shutdown Runbook](../runbooks/nut-tiered-shutdown.md)*
