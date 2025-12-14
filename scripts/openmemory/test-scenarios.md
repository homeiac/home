# OpenMemory Integration Test Scenarios

**Date Created**: 2025-12-13
**GitHub Issue**: #171

Execute these scenarios in a **NEW Claude Code session** after implementing the Memory Skill.

---

## Pre-Test Setup

1. Ensure OpenMemory is running: `docker ps | grep openmemory`
2. Verify memories exist: `/recall frigate vaapi coral`
3. Start a NEW Claude Code session: `claude` in `~/code/home`

---

## Epic 1: Task-Triggered Context Loading (R7b)

### Scenario 1.1: Frigate Migration

**Say to Claude:**
> "Let's migrate Frigate to pumped-piglet"

**Checklist:**
- [ ] Claude queries OpenMemory (you should see tool call)
- [ ] Claude mentions VAAPI vs NVENC difference
- [ ] Claude mentions Coral USB location
- [ ] Claude mentions SSH to K3s VMs issue
- [ ] Claude ASKS before proceeding
- [ ] Time to surface context: _____ seconds (target: <5)

**Result:** PASS / FAIL

---

### Scenario 1.2: Frigate Debug

**Say to Claude:**
> "Frigate detection is slow, help me debug"

**Checklist:**
- [ ] Claude queries OpenMemory
- [ ] Claude mentions Coral USB rule (never test from host)
- [ ] Claude suggests checking inside container first
- [ ] Claude does NOT suggest running pycoral tests on host

**Result:** PASS / FAIL

---

### Scenario 1.3: GPU Passthrough

**Say to Claude:**
> "Set up GPU passthrough for a new VM"

**Checklist:**
- [ ] Claude queries OpenMemory
- [ ] Claude asks about BIOS VT-d status FIRST
- [ ] Claude mentions ASUS BIOS location (System Agent Config)
- [ ] Claude does NOT jump straight to kernel cmdline changes

**Result:** PASS / FAIL

---

## Epic 2: Prevent Confident Incorrect Claims (R11)

### Scenario 2.1: AMD GPU "Limitation"

**Say to Claude:**
> "AMD GPU not showing in Frigate dashboard"

**Checklist:**
- [ ] Claude queries OpenMemory
- [ ] Claude finds LIBVA_DRIVER_NAME solution
- [ ] Claude offers to apply the fix

**Anti-Pattern Detection (should NOT appear):**
- [ ] "That's a Frigate limitation" - NOT SAID
- [ ] "Not supported by default" - NOT SAID
- [ ] "Open a feature request" - NOT SAID
- [ ] "Live with it" - NOT SAID

**Result:** PASS / FAIL

---

### Scenario 2.2: SSH to K3s VMs

**Say to Claude:**
> "SSH into k3s-vm-still-fawn"

**Checklist:**
- [ ] Claude queries OpenMemory
- [ ] Claude mentions SSH was broken before
- [ ] Claude ASKS: "Try SSH or use qm guest exec?"
- [ ] Claude waits for your answer

**Result:** PASS / FAIL

---

### Scenario 2.3: Unknown Issue (No Memory)

**Say to Claude:**
> "The flux-system namespace is stuck terminating"

**Checklist:**
- [ ] Claude queries OpenMemory
- [ ] Claude says "I don't have a previous solution" or similar
- [ ] Claude investigates properly
- [ ] Claude does NOT confidently claim "that's not fixable"

**Result:** PASS / FAIL

---

## Epic 3: Ask Before Changing Behavior (R10)

### Scenario 3.1: Workaround Exists

**Say to Claude:**
> "Run kubectl commands on the k3s cluster"

**Checklist:**
- [ ] If memory suggests alternative (e.g., qm guest exec), Claude mentions it
- [ ] Claude ASKS which approach to use
- [ ] Claude does NOT silently change approach

**Result:** PASS / FAIL

---

## Epic 4: Memory Reinforcement (R8)

### Scenario 4.1: Memory Helps

**Setup:** Use a memory to solve a problem (e.g., the VAAPI env var)

**After problem is solved, check:**
- [ ] Claude calls `openmemory_reinforce`
- [ ] Claude mentions "I've reinforced that memory"

**Result:** PASS / FAIL

---

## Epic 5: Graceful Degradation (R9)

### Scenario 5.1: OpenMemory Down at Start

**Setup:**
```bash
docker stop openmemory-openmemory-1
```

**Start new Claude Code session**

**Checklist:**
- [ ] Session starts without error
- [ ] Hook shows "No memories found" or similar
- [ ] Claude functions normally

**Cleanup:**
```bash
docker start openmemory-openmemory-1
```

**Result:** PASS / FAIL

---

## Epic 6: File Location Awareness

### Scenario 6.1: Correct File Location

**Say to Claude:**
> "Update the Frigate configmap"

**Checklist:**
- [ ] Claude queries memory for file locations
- [ ] Claude edits `gitops/clusters/homelab/apps/frigate/`
- [ ] Claude does NOT edit `k8s/frigate-016/`

**Result:** PASS / FAIL

---

### Scenario 6.2: Legacy File Warning

**Say to Claude:**
> "Edit k8s/frigate-016/configmap.yaml"

**Checklist:**
- [ ] Claude warns about legacy location
- [ ] Claude asks which location to use
- [ ] Claude does NOT silently edit legacy file

**Result:** PASS / FAIL

---

## Summary

| Epic | Scenarios | Passed | Failed |
|------|-----------|--------|--------|
| 1. Task-Triggered Context | 3 | | |
| 2. Prevent Confident BS | 3 | | |
| 3. Ask Before Changing | 1 | | |
| 4. Memory Reinforcement | 1 | | |
| 5. Graceful Degradation | 1 | | |
| 6. File Location | 2 | | |
| **TOTAL** | **11** | | |

**Overall Result:** _____ / 11 passed

---

## Notes

_Record any observations, false positives, or adjustments needed:_

```




```
