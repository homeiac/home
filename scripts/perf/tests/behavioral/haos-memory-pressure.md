# Test: HAOS Memory Pressure

Validates USE Method on Proxmox VM target and proper layered analysis.

## Setup

- HAOS VM 116 on chief-horse.maas running at 92% memory
- OpenMemory has NO relevant entries
- Proxmox host (chief-horse) resources are normal
- CPU, Disk, Network all normal on both layers

## Test Prompt

"Home Assistant is unresponsive"

## Expected Claude Behavior

1. **[FIRST]** Query OpenMemory:
   ```
   openmemory_query("home assistant unresponsive slow solved fix", k=5)
   ```
   Result: No relevant memories found

2. **[THEN]** Run USE Method on HAOS VM:
   ```bash
   scripts/perf/diagnose.sh --target proxmox-vm:116
   ```

3. **[DETECT]** USE Method shows (VM Layer):
   - CPU: OK
   - Memory: 92% utilization (WARN)
   - Disk: OK
   - Network: OK

4. **[LAYERED]** Also check host layer (chief-horse):
   - CPU: OK
   - Memory: OK (host has plenty)
   - Disk: OK
   - This confirms issue is in VM, not host

5. **[DEEP DIVE]** For memory issue:
   ```bash
   scripts/perf/memory-deep-dive.sh --target proxmox-vm:116
   ```
   Shows top memory consumers within HAOS

6. **[REPORT]** Findings:
   - "HAOS VM 116 memory at 92%"
   - "Top consumers: [integration names from ps output]"
   - "Host layer (chief-horse) is fine - issue is VM-specific"
   - Recommend: Increase VM RAM, or disable memory-heavy integrations

7. **[OPTIONAL STORE]** If user confirms resolution

## Failure Modes

- Assuming network issue without checking (common mistake for "unresponsive")
- Only checking VM layer, not host layer
- Stopping after finding memory issue without checking CPU/Disk/Network
- Not using the correct target context (proxmox-vm:116)
- Trying to SSH to HAOS (doesn't have SSH)

## Why This Test Matters

This tests:
1. Correct target context for Proxmox VMs
2. Layered analysis (VM + Host)
3. Not assuming "unresponsive" = network
4. Proper deep dive into identified resource issue

## Pass Criteria

- OpenMemory queried first (returns empty)
- Correct target: `proxmox-vm:116`
- Both VM and host layers checked
- All resources checked on VM (CPU, Memory, Disk, Network)
- Memory pressure correctly identified
- Not assumed to be network without evidence
