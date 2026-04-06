# RCA: Frigate CrashLoopBackOff - Coral USB TPU State Corruption

**Date**: 2026-04-05
**Duration**: ~45 minutes
**Impact**: All 5 cameras offline, no object detection, no face recognition, no "Hello G" greetings
**Severity**: High

## Timeline

| Time (PT) | Event |
|-----------|-------|
| ~14:30 | HAOS VM 116 rebooted (chief-horse) for CPU core change (2→4) |
| ~14:48 | HA came back, Frigate face sensors reset to "Unknown" |
| ~15:10 | Frigate cameras confirmed working (Coral at 25ms) |
| ~22:35 | Flux reconciliation blocked by immutable Ollama Job, preventing health checker image update |
| ~22:57 | Frigate pod restarted, Coral USB TPU not detected |
| ~22:57 | Liveness probe kills Frigate after 60s (API never starts without Coral) |
| ~22:57-23:07 | CrashLoopBackOff - 6 rapid restarts corrupt Coral USB state further |
| ~23:02 | USB reset from host attempted - disconnected Coral from VM passthrough |
| ~23:02 | `qm set 105 -usb1` re-attached USB config but VM can't hotplug USB |
| ~23:07 | Liveness probe increased to 180s initialDelay (committed via Flux) |
| ~23:07 | VM 105 (pumped-piglet-gpu) rebooted to restore USB passthrough |
| ~23:07 | Frigate starts, Coral TPU found, all cameras streaming |

## Root Cause

**Three contributing factors:**

1. **Aggressive liveness probe** (initialDelaySeconds=60) killed Frigate before it could fully start when the Coral was slow to initialize. Each kill triggered a pod restart.

2. **Rapid USB device cycling** from 6+ pod restarts in quick succession corrupted the Coral USB TPU state. The USB interface wasn't properly released between restarts, leaving the device in a "claimed but not accessible" state.

3. **USB reset from host detached VM passthrough**. Running `usbreset` on the Proxmox host disconnected the Coral from the VM's USB passthrough. `qm set` updated the config but USB hotplug doesn't work for passthrough devices — requires VM reboot.

**Secondary factor:** Flux reconciliation was blocked for 40+ minutes by an immutable Ollama Job (`ollama-model-update-gemma4`). This prevented the health checker image update from deploying, though the health checker wouldn't have prevented this specific issue.

## Fix Applied

1. **Liveness probe relaxed**: `initialDelaySeconds` 60→180, `failureThreshold` 3→5. Gives Frigate 3+ minutes to start before probes kill it.
2. **VM rebooted** to restore Coral USB passthrough.
3. **Immutable Ollama Job deleted** to unblock Flux reconciliation.

## Prevention

- Never run `usbreset` on a USB device that's passed through to a VM — it breaks the passthrough. Reboot the VM instead.
- K8s Jobs are immutable once created. When renaming Jobs in GitOps manifests, delete the old Job before pushing.
- The health checker CronJob now runs with a working image (`21-2f5fed2`) and will detect camera failures going forward.

## Lessons Learned

1. **Liveness probes are a blunt instrument for stateful hardware.** Coral USB TPU has state that survives pod restarts but corrupts under rapid cycling. The health checker (with grace periods and confirmation thresholds) is better suited for restart decisions.
2. **USB passthrough ≠ USB access.** Host-level USB operations (reset, rebind) break VM passthrough. Always operate on USB devices from inside the VM, or reboot the VM.
3. **Immutable K8s resources block Flux globally.** One failed Job reconciliation blocks ALL resources in the kustomization. Monitor `flux get kustomization` for `ReconciliationFailed` status.

## Related

- [Frigate health checker restart loop RCA](../runbooks/frigate-health-checker-restart-loop-rca.md)
- [Coral USB TPU troubleshooting](../runbooks/frigate-tpu-troubleshooting.md)
- [Ollama Gemma 4 migration runbook](../runbooks/ollama-gemma4-migration.md)

**Tags**: frigate, coral, tpu, usb, crashloop, liveness-probe, flux, immutable-job, gpu, pumped-piglet
