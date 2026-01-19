# Test: Frigate High CPU (New Issue)

Validates that Claude follows USE Method systematically for new issues.

## Setup

- OpenMemory has NO entries for "frigate cpu high"
- Frigate pod on still-fawn is running at 95% CPU
- All other resources (memory, disk, network) are normal

## Test Prompt

"Frigate seems slow, detections are delayed"

## Expected Claude Behavior

1. **[FIRST]** Query OpenMemory:
   ```
   openmemory_query("frigate slow delayed detection solved fix", k=5)
   ```
   Result: No relevant memories found

2. **[THEN]** Run USE Method:
   ```bash
   scripts/perf/diagnose.sh --target k8s-pod:frigate/frigate-coral-xxx
   ```
   Or if K8s pod context not working:
   ```bash
   scripts/perf/diagnose.sh --target ssh:root@still-fawn.maas
   ```

3. **[DETECT]** USE Method shows:
   - CPU: 95% utilization (WARN/ERROR)
   - Memory: OK
   - Disk: OK
   - Network: OK

4. **[DEEP DIVE]** For CPU issue:
   - Show `mpstat -P ALL 1 5` output
   - Show `pidstat 1 5` to identify process
   - Check if specific Frigate process (decode, detect) is hot

5. **[REPORT]** Findings:
   - "CPU utilization at 95% on still-fawn"
   - "Top CPU consumer: ffmpeg decode process"
   - Recommend: Check camera stream settings, reduce resolution

6. **[STORE]** After resolution:
   ```
   openmemory_lgm_store(
     node="act",
     content="Frigate slow detection - SOLVED. Root cause: High CPU from ffmpeg decode. Fix: <resolution>",
     tags=["frigate", "cpu", "performance", "solved"]
   )
   ```

## Failure Modes

- Skipping OpenMemory check and going straight to diagnostics
- Jumping to "check Coral TPU" without running USE Method first
- Only checking CPU without verifying other resources are OK
- Not running full USE checklist (E->U->S for all resources)
- Assuming it's network-related without data

## Why This Test Matters

This tests the full USE Method flow for a NEW issue (not in memory).
Claude should:
1. Check memory (find nothing)
2. Run systematic diagnosis
3. Follow E->U->S order
4. Check ALL resources, not just suspect CPU
5. Store the resolution for future reference

## Pass Criteria

- OpenMemory queried first (returns empty)
- USE Method script invoked
- All resources checked (CPU, Memory, Disk, Network)
- High CPU detected and reported
- Recommendation provided
- Resolution stored in OpenMemory after fix
