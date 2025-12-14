# When AI Confidently Tells You to "Live With It" (And Is Completely Wrong)

**Date**: 2025-12-13
**Tags**: ai, claude, openmemory, frigate, homelab, lessons-learned

---

## The Fuckup

I asked Claude to help me figure out why my AMD GPU wasn't showing in my Frigate NVR dashboard. The Frigate stats API was returning:

```json
{
  "gpu_usages": {
    "intel-vaapi": {
      "gpu": "",
      "mem": ""
    }
  }
}
```

Claude investigated, ran some commands, confirmed VAAPI was working via `vainfo` and `radeontop`, then delivered this confident assessment:

> "This is a Frigate limitation - it only shows Intel VAAPI in the dashboard by default. The GPU **is working** (we proved it with vainfo, ffmpeg args, and radeontop), just the dashboard display doesn't support AMD."
>
> **Options:**
> 1. Live with it - GPU works, just no dashboard widget
> 2. Open a Frigate feature request for AMD GPU monitoring
> 3. Custom Grafana dashboard pulling from radeontop

Sounds reasonable, right? Authoritative. Backed by evidence. Three sensible options.

**It was complete bullshit.**

## What Actually Happened

The real issue was a missing environment variable: `LIBVA_DRIVER_NAME=radeonsi`. I had already solved this exact problem months ago when setting up Frigate on an LXC container. The working config was sitting in my repo at `proxmox/backups/frigate-app-config.yml`.

But it gets worse. Claude also:

1. **Edited the wrong file** - `k8s/frigate-016/deployment.yaml` instead of `gitops/clusters/homelab/apps/frigate/deployment.yaml` (which is what Flux actually deploys)
2. **Used `kubectl apply` directly** - violating GitOps principles and causing drift
3. **Didn't check if the env var was actually set** - a 5-second `kubectl exec ... env | grep LIBVA` would have revealed the problem

After I called bullshit and told Claude to actually investigate properly, the fix took 2 minutes:

```yaml
env:
  - name: LIBVA_DRIVER_NAME
    value: "radeonsi"
```

Result:

```json
{
  "gpu_usages": {
    "amd-vaapi": {
      "gpu": "1.67%",
      "mem": "2.16%"
    }
  }
}
```

## Why This Matters

The failure mode here isn't "AI doesn't know things." Claude clearly knows about VAAPI, Frigate, environment variables, and Kubernetes. The failure mode is:

**AI confidently claims something is impossible/a limitation when the user has already solved it before.**

This is arguably worse than not knowing. If Claude had said "I'm not sure why this isn't working," I would have immediately thought "wait, I fixed this before." Instead, the confident "this is a Frigate limitation" explanation sent me down a mental path of acceptance.

## The OpenMemory Experiment

We're building [OpenMemory](https://github.com/openMemoryOrg/openMemory) to give AI agents persistent memory across sessions. The hypothesis: if Claude had access to memories from previous sessions, it would have:

1. Queried for "frigate amd gpu vaapi"
2. Found the memory: "requires LIBVA_DRIVER_NAME=radeonsi env var"
3. Checked the env var first before making claims
4. Fixed it in 2 minutes instead of 45

### Memories We Stored

After this incident, we stored these procedural memories:

```
Memory 1: "Frigate AMD VAAPI GPU monitoring requires LIBVA_DRIVER_NAME=radeonsi
env var. Without it, dashboard shows empty intel-vaapi stats."

Memory 2: "Frigate K8s manifests are in gitops/clusters/homelab/apps/frigate/ -
Flux manages deployment. k8s/frigate-016/ is UNUSED. NEVER kubectl apply directly."

Memory 3: "Frigate on still-fawn uses AMD RX 580 + Coral TPU. Config requires:
preset-vaapi, LIBVA_DRIVER_NAME=radeonsi, /dev/dri mount, /sys mount for radeontop."
```

### The Test Scenario

We also stored a "reflection" memory documenting this entire fuckup as a test scenario. Future versions of OpenMemory integration should be validated against this case:

| Behavior | Without Memory | With Memory |
|----------|----------------|-------------|
| Makes confident incorrect claim | Yes | Should NOT happen |
| Suggests "live with it" for solved problem | Yes | Should NOT happen |
| Checks env var first | No | Should happen FIRST |
| Edits correct gitops file | No | Should happen |
| References previous solution | No | Should happen |
| Time to fix | ~45 min | <5 min |

## Lessons Learned

### For AI Users

1. **Be suspicious of confident "it's a limitation" claims** - especially for open source software with active communities
2. **Ask "have I solved this before?"** - your own history is valuable context
3. **Demand investigation before acceptance** - "check the env vars" should come before "open a feature request"

### For AI Developers

1. **Confidence calibration matters** - wrong + confident is worse than wrong + uncertain
2. **Memory prevents repeated mistakes** - same user, same problem, should get same solution
3. **"I don't know" is underrated** - better to investigate than to fabricate plausible-sounding limitations

### For OpenMemory

This incident is now a test case. When we query OpenMemory for "frigate amd gpu" in a future session, we should get back the env var fix immediately. If we don't, or if the agent still makes confident incorrect claims despite having the memory, we have a bug to fix.

## Conclusion

AI assistants are incredibly useful, but they have a dangerous failure mode: confident incorrectness. When an AI tells you something is impossible or a platform limitation, take it with skepticism - especially if you have a nagging feeling you've solved it before.

Persistent memory across sessions isn't just a convenience feature. It's a safety mechanism against AI bullshit.

---

*The Frigate dashboard now shows AMD GPU stats. The fix was one environment variable. The lesson cost 45 minutes of debugging and one frustrated user.*
