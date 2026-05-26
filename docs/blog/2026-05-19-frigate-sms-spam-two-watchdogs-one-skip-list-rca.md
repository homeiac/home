# Two Watchdogs, One Skip List, and an ImagePolicy That Could Roll You Back to 2026-02-16

**Date:** 2026-05-19
**Tags:** frigate, sms, alerts, watchdog, flux, image-automation, gitops, rca, homelab, lessons-learned

> Three 192.168.1.x cameras have been down for ~27 hours. The in-cluster Frigate health checker was told to ignore them a month ago. The Pixel-7 SMS gateway was paging me anyway, every 30 minutes, for the last 1650 minutes. There was a *second* watchdog I'd forgotten about, with its own skip list, and the IaC pipeline that should have fixed it was structurally broken in a way that would have made the *oldest* commit "latest."

## TL;DR

I have two Frigate monitors: a K3s CronJob (in-cluster, alerts via Alertmanager) and an external bash watchdog on `pve` (out-of-cluster, alerts via SMS). They were built deliberately as independent paths — if K3s itself goes down, the external one still pages. The downside of independence: they don't share state. When I retired three 192.168.1.x cameras a month ago (commit `20cb3f9`, refs #187), I updated only the K3s checker's `FRIGATE_HC_SKIP_CAMERAS`. The external watchdog kept seeing 3/4 cameras at `camera_fps=0`, tripping `majority_down`, and SMSing.

Fix should have been a one-line `SKIP_CAMERAS=…` on the cron entry. It was, but pushing the commit exposed a second bug: the Flux `ImagePolicy` for `pve-nut` used `alphabetical desc` over bare 7-character git SHAs. With the three real tags in ghcr today — `[e6e2d9b, 9d5fdfe, 5cde4ad]` — `alphabetical desc` would have picked **`e6e2d9b`**, the *oldest* commit (Feb 16), as "latest" and rolled the deploy back to before SMS alerting existed.

Two commits, one Flux-bot tag-bump, one emergency SSH override, and the cron file on `pve` now contains the skip list. SMS stopped at 11:55 local; the next watchdog tick at 11:58 logged `Healthy - ok:0:2`.

## Timeline (Pacific)

| Time | Event |
|------|-------|
| 2026-04-18 12:02 | `20cb3f9`: K3s health checker `FRIGATE_HC_SKIP_CAMERAS` set to `[old_ip_camera, living_room, hall]`. External watchdog left alone. |
| 2026-05-18 ~08:30 | (last SMS observation prior to today) |
| 2026-05-19 ~11:00 | "i keep getting sms alerts for frigate even though i have temporarily 'retired' 2 cameras" |
| 11:10 | Agent diagnoses: two monitors, only one knows about retired cameras. External watchdog default `SKIP_CAMERAS=reolink_doorbell` is the culprit. |
| 11:14 | "huh? doorbell is working" — the watchdog's "flaky WiFi" comment was stale; doorbell is actually one of two healthy cameras. Skip list corrected to just the 3 retired cameras. |
| 11:18 | `9d5fdfe`: `scripts/pve-nut/deploy.sh` updated, pushed. CI builds `pve-nut:9d5fdfe`. |
| 11:25 | Investigating Flux state: `imagepolicy.pve-nut` still pinned to `5cde4ad`. `imagerepository` scan finds tags `[e6e2d9b, 9d5fdfe, 5cde4ad]`. |
| 11:30 | Realized `alphabetical desc` on git SHAs is structurally broken — `e6e2d9b` would beat `9d5fdfe` purely on first hex char. New code would never deploy; *old* code would. |
| 11:35 | SMS still firing every 30 min while pipeline diagnosed. Applied emergency `/etc/cron.d/frigate-watchdog` override directly on `192.168.4.122` with the corrected `SKIP_CAMERAS`. Cleared `/var/run/frigate-watchdog-state`. |
| 11:38 | Manual watchdog run reports `Healthy - ok:0:2` (0 down of 2 monitored). SMS stops. |
| 11:55 | **Last** SMS observed: `Cameras STILL DOWN 1650min (3/4)` — 27.5 hours of paging across the incident. |
| 12:02 | `c08d962`: workflow emits `<run_number>-<short_sha>`; `ImagePolicy` switched to `numerical asc` with extract pattern `^(\d+)-[a-f0-9]{7}$`. Matches the working `frigate-health-checker` pattern. |
| 12:03 | CI build 4 publishes `pve-nut:4-c08d962`. |
| 12:06 | Forced `imagerepository` reconcile → scan picks up the new tag. `imagepolicy` re-evaluates → resolves `4-c08d962`. |
| 12:09 | `f0eb395`: Flux bot commits the image tag bump on `job-deploy.yaml`. |
| 12:11 | `nut-pve-deploy` Kustomization applied; Job re-runs from the new image; cron file rewritten *from IaC* (no longer from the SSH override). |
| 12:12 | Steady state: `cat /etc/cron.d/frigate-watchdog` on `pve` shows `SKIP_CAMERAS='old_ip_camera,living_room,hall'`. Next two watchdog ticks log `Healthy - ok:0:2`. |

## Root causes

### 1. Two watchdogs, one skip list

The external watchdog was added in `999ea8b` (2026-03-08) precisely so the SMS path would survive K3s being unavailable. That's the right architecture — what was missing was a single source of truth for "which cameras are expected to be down right now."

The K3s checker has `FRIGATE_HC_SKIP_CAMERAS` as a manifest field. The external watchdog has `SKIP_CAMERAS` as a script-local default with a stale comment ("reolink_doorbell, flaky WiFi") that no longer reflected reality. When the K8s skip list was updated a month ago, nothing forced a parallel update on the watchdog. They drifted.

The minimum fix is what we did: pin `SKIP_CAMERAS` on the cron entry in `deploy.sh` with a comment explicitly tying it to the K8s manifest. A better fix is in the open items below.

### 2. `alphabetical desc` on git SHA tags is a footgun

The `pve-nut` `ImagePolicy` had:

```yaml
filterTags:
  pattern: '^[a-f0-9]{7}$'
policy:
  alphabetical:
    # Use descending order to get newest SHA (alphabetically later = newer commit)
    order: desc
```

That comment is wrong twice. First: git SHAs are random hex, so "alphabetically later" has no relationship to "newer commit." Second: per Flux's image-reflector semantics, `order: desc` and `order: asc` both sort *and then pick the last entry of the sorted list* — `desc` actually picks the alphabetically *lowest* tag, not highest. The whole construct was built on a misunderstanding.

For a long time it accidentally worked because there were only two tags. With three tags `[e6e2d9b, 9d5fdfe, 5cde4ad]`, the next reconcile would have picked `e6e2d9b` (Feb 16 commit) as "latest" and the Flux bot would have committed:

```
chore(flux): update pve-nut image to ghcr.io/homeiac/pve-nut:e6e2d9b
```

The deploy Job would re-run with the old `deploy.sh`, which has no `SKIP_CAMERAS` line. SMS resumes. I would have been chasing a phantom.

The correct pattern was already in the repo on `frigate-health-checker`: tag with `<run_number>-<short_sha>`, filter with `^(\d+)-[a-f0-9]{7}$`, sort `numerical asc`, extract `$1`. Copy-pasted that pattern wholesale.

### 3. Stale comments outliving the reality they described

The watchdog script's "flaky WiFi → skip reolink_doorbell" comment dates from when the doorbell was unreliable. The doorbell is now one of only two cameras the K8s checker actively monitors. When I first proposed a fix I tried to *merge* both skip lists rather than asking "is the rationale on each entry still true today?" — which would have silenced a working camera.

The general anti-pattern: when reconciling two diverged configs, don't union them. Check each entry against current state.

## What changed today

- ✅ `9d5fdfe` — `scripts/pve-nut/deploy.sh` writes the cron entry with `SKIP_CAMERAS='old_ip_camera,living_room,hall'`. Comment in the script ties the value to `FRIGATE_HC_SKIP_CAMERAS` in `cronjob-health-python.yaml` so the next person who edits one sees the other.
- ✅ `c08d962` — `.github/workflows/build-pve-nut.yaml` emits `<run_number>-<short_sha>`; `image-automation-pve-nut.yaml` uses `numerical asc` with extract. Also added the workflow file to its own `paths:` so workflow edits trigger rebuilds.
- ✅ `f0eb395` — Flux bot's tag bump to `4-c08d962`. The Job re-ran and wrote the corrected cron file from IaC. The temporary SSH override on `192.168.4.122` was overwritten by the Job, exactly as the discipline promises.
- ✅ Confirmed end-to-end: cron file on `pve` matches what's in git; two consecutive ticks logged `Healthy - ok:0:2`.

## Open items

- [ ] **Single source of truth for the skip list.** The right design is one ConfigMap (or env-from-Secret) consumed by both monitors. Today, `deploy.sh` carries the value in-band of the cron file; the K8s manifest carries the same value as an env var. Two places. Drift-prone. Likely fix: render a ConfigMap from the same value, have the deploy Job read it into the cron `SKIP_CAMERAS=`, have the K8s CronJob mount the same key.
- [ ] **Fix the other two ImagePolicies that share the bug.** Audit confirmed `proxmox-provisioner` and `ollama-scripts` both use `alphabetical desc` over bare 7-char SHA tags — the `proxmox-provisioner` policy carries the *same* copy-pasted "alphabetically later = newer commit" comment. Both are latent footguns; whether they bite depends on which tags happen to be in ghcr at reconcile time. Should be migrated to the `<run_number>-<short_sha>` pattern (separate PR; required CI workflow changes too).
- [ ] **Restore the 192.168.1.x cameras.** This is the actual incident-root, not just the alerting noise. The cameras are at 192.168.1.220 (`old_ip_camera`), 192.168.1.138 (`living_room`), 192.168.1.137 (`hall`). Per #187 the working theory is a network/VLAN path or the cameras being powered off. Once restored, *revert both skip lists in the same PR*.
- [ ] **Add a CI lint that flags `policy.alphabetical` over a SHA-shaped filter pattern.** Cheap shellcheck-style guardrail; would have caught this when it was first written.
- [ ] **Watchdog should log SMS sends with the message body**, not just `[INFO] SMS sent via 10.181.204.183`. The log line that confirmed the cause today was `Cameras STILL DOWN 1650min (3/4): old_ip_camera,living_room,hall` — but that was the *Alert content*, not the SMS send log. If I'd had to grep without context, the SMS send log on its own wouldn't have told me which alert fired.

## Lesson re-learned

The Feb 2026 plug-on-surge-outlet outage taught me [physical affordances beat docs](2026-05-18-ups-plug-strikes-again-power-outage-rca.md#lesson-re-learned). This one's the IaC version of the same lesson: **structural correctness beats best-effort comments.**

The `pve-nut` `ImagePolicy` shipped with a comment that confidently asserted "descending order to get newest SHA (alphabetically later = newer commit)." Both halves were wrong. Two months and three commits in, with the right random set of tags in ghcr, it would have silently rolled the deploy back to February. The comment looked reassuring; the structure was a coin flip.

The other piece of the same lesson: **don't have two systems that need to agree, with no mechanism forcing the agreement.** Two watchdogs by design is fine. Two skip lists by accident is not.

---

*Related: [Out-of-Band SMS Notifications for Homelab Disaster Recovery](../source/md/blog-out-of-band-sms-disaster-recovery.md), [Same Lesson, Different Outage](2026-05-18-ups-plug-strikes-again-power-outage-rca.md), [Frigate health checker restart loop RCA](../runbooks/frigate-health-checker-restart-loop-rca.md) (#187)*
