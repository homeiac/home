# How I Deploy Hardware-Accelerated NVR Containers: A Blueprint-Driven Methodology

**Date**: December 11, 2025
**Reading Time**: 12 minutes
**Tags**: homelab, frigate, coral-tpu, proxmox, lxc, devops, infrastructure-as-code

---

## The Problem with "Just SSH In and Figure It Out"

Every homelab enthusiast has been there. You find a cool project—in this case, [Frigate NVR](https://frigate.video/) with a [Google Coral TPU](https://coral.ai/)—and you think: "I'll just SSH in, run some commands, and have it working in an hour."

Four hours later, you're deep in Stack Overflow tabs, your config file has been edited seventeen times, and you can't remember which change broke what. Sound familiar?

After deploying Frigate with Coral USB passthrough to LXC containers multiple times (and failing spectacularly a few of those times), I developed a three-document methodology that transformed chaotic deployments into repeatable, debuggable processes.

## The Three-Document System

The methodology uses three interconnected documents:

```
Blueprint (PRESCRIPTIVE)       ← The "HOW" - complete instructions
     ↓ generates
Template (SKELETON)            ← The "FORM" - blank structure to fill
     ↓ filled during execution
Action Log (RECORD)            ← The "HISTORY" - what actually happened
```

Each serves a distinct purpose, and together they create a feedback loop that improves with every deployment.

---

## Document 1: The Blueprint

The blueprint is your source of truth. It contains everything needed to execute the deployment: prerequisites, scripts, phases, success criteria, and rollback procedures.

### What Makes a Good Blueprint

A blueprint isn't just documentation—it's executable knowledge. Here's the structure I use:

```markdown
# Blueprint: Frigate Coral USB TPU LXC Deployment

## Problem Statement
Why are we doing this? What challenge does it solve?

## Prerequisites
- Host requirements (packages, hardware)
- Software dependencies
- **Blocking conditions** (things that MUST exist before starting)

## Script Directory
| Script | Purpose |
|--------|---------|
| `01-check-prerequisites.sh` | Verify host packages |
| `02-verify-coral-usb.sh` | Confirm Coral USB detection |
...

## Execution Plan
### Phase 1: Pre-Flight
### Phase 2: Coral Firmware & Udev Rules (CRITICAL)
### Phase 3: Container Creation
...

## Success Criteria
| Criterion | Verification |
|-----------|--------------|
| Container starts | `pct status <VMID>` shows running |
| Coral detected | Inference speed 8-15ms |
...

## Rollback
How to undo everything if it goes wrong.

## Troubleshooting
Common issues and their solutions.
```

### Real Example: The Critical Phase That Was Missing

During my first deployment, the Coral USB stayed stuck in "bootloader mode" (`1a6e:089a` vendor ID) instead of initializing to the working state (`18d1:9302`).

The original blueprint only had permission-setting udev rules:

```bash
# Original (BROKEN) - only sets permissions
SUBSYSTEMS=="usb", ATTRS{idVendor}=="18d1", MODE="0666"
```

The fix required **firmware loading via dfu-util**—a critical step documented in a separate runbook but missing from the deployment blueprint:

```bash
# Fixed - loads firmware on detection, THEN sets permissions
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="1a6e", \
  RUN+="/usr/bin/dfu-util -D /usr/local/lib/firmware/apex_latest_single_ep.bin"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="18d1", MODE="0666"
```

This discovery led to adding three new scripts to the blueprint:
- `05a-install-dfu-util.sh`
- `05b-download-firmware.sh`
- `05c-create-udev-rules.sh`

**The lesson**: Blueprints must be complete. If you reference another document, either inline the critical parts or make the dependency explicit.

---

## Document 2: The Action Log Template

The template is a blank form that mirrors the blueprint's structure. During execution, you fill it in with timestamps, outputs, and status indicators.

### Why Not Just Use the Blueprint Directly?

Because execution diverges from plans. The template gives you:

1. **Structured space for outputs** - paste command results
2. **Timestamp tracking** - know when things happened
3. **Status indicators** - ✅/❌/⚠️ at a glance
4. **Issue documentation** - structured section for problems encountered

### Template Structure

```markdown
# Action Log Template: Frigate Coral LXC Deployment

## Document Header
**Date**: YYYY-MM-DD
**Operator**: [Name/AI Agent]
**GitHub Issue**: #XXX
**Status**: [Planning | In Progress | Completed | Failed]

---

## Pre-Operation State

### Host Information
- **Hostname**: [HOST_NAME]
- **IP Address**: [IP]
- **Proxmox Version**: [VERSION]

### Coral USB Detection
| Field | Value |
|-------|-------|
| Vendor ID | [1a6e/18d1] |
| Bus | [BUS] |
| Device | [DEV] |

---

## Phase 1: Pre-Flight Investigation

### Step 1.1: Check Prerequisites
**Script**: `01-check-prerequisites.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️
**Notes**: [NOTES]

---

### Step 1.2: Verify Coral USB
**Script**: `02-verify-coral-usb.sh`
**Timestamp**: [HH:MM]
...

---

## Phase 2: Coral Firmware & Udev Rules (CRITICAL)

### Step 2.1: Install dfu-util
**Script**: `05a-install-dfu-util.sh`
**Timestamp**: [HH:MM]
...

---

## Issues Encountered

### Issue 1: [Description]
**Severity**: [Low/Medium/High/Critical]
**Symptoms**:
- [Symptom 1]

**Root Cause**: [Analysis]

**Resolution**:
```bash
[Commands used]
```

**Prevention**: [How to prevent in future]

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | [Success/Partial/Failed] |
| **Start Time** | [HH:MM] |
| **End Time** | [HH:MM] |
| **Total Duration** | [X hours] |
```

### Key Template Sections

**Pre-Operation State**: Capture the "before" picture. You'll thank yourself when debugging.

**Phase Steps**: One section per script/action with timestamp, output, and status.

**Issues Encountered**: This is where learning happens. Document every deviation from the plan.

**Performance Comparison**: Before/after metrics prove the deployment achieved its goals.

---

## Document 3: The Action Log Instance

This is the filled-in template—your historical record of what actually happened during a specific deployment.

### Real Example: still-fawn Deployment

Here's an excerpt from an actual deployment:

```markdown
# Action Log: Frigate Coral LXC on still-fawn

**Date**: 2025-12-10 / 2025-12-11
**Operator**: Claude Code AI Agent
**GitHub Issue**: #168
**Target Host**: still-fawn (192.168.4.17)
**Container VMID**: 110
**Status**: ✅ Completed

---

## Pre-Operation State

### Host Information
- **Hostname**: still-fawn
- **IP Address**: 192.168.4.17
- **Proxmox Version**: 8.x
- **CPU**: Intel Core i5-4460 @ 3.20GHz (4 cores)
- **GPU**: AMD Radeon RX 580
- **Existing Containers**: 104 (docker-webtop)

---

## Phase 1.5: Fix /dev/dri (Blocking Issue)

**Issue**: `/dev/dri` did not exist on host - blocking PVE Helper Script

**Root Cause**: AMD GPU drivers (amdgpu) were blacklisted in
`/etc/modprobe.d/pve-blacklist.conf` - leftover from previous
NVIDIA RTX 3070 passthrough setup

**Fix Applied**:
1. Removed AMD driver blacklist entries
2. Ran `update-initramfs -u`
3. Rebooted host

**Status**: ✅ Resolved

---

## Phase 2: Coral Firmware & Udev Rules (CRITICAL FIX)

**Blueprint Issue Found**: Original `05-create-udev-rules.sh` only
set permissions, missing the critical `dfu-util` firmware loading rule

**Blueprint Updated**: Added new scripts:
- `05a-install-dfu-util.sh`
- `05b-download-firmware.sh`
- `05c-create-udev-rules.sh`

### Step 2.4: Reload Udev and Initialize Coral
**Timestamp**: 2025-12-11 03:35 UTC
**Before**: `1a6e:089a` (Global Unichip - bootloader)
**After**: `18d1:9302` (Google Inc - initialized)
**Status**: ✅ Coral initialized successfully

---

## Issues Encountered

### Issue 1: Blueprint Missing dfu-util Firmware Loading
**Severity**: High
**Symptoms**: Coral stayed in bootloader mode, never initialized

**Root Cause**: `05-create-udev-rules.sh` only set permissions,
missing the `RUN+=` dfu-util rule

**Resolution**: Created new scripts with complete firmware loading

**Prevention**: Updated blueprint Phase 2 with complete procedure

### Issue 3: Direct File Modification Without Backup
**Severity**: Process Violation
**Symptoms**: Attempted to modify Frigate config directly

**Root Cause**: Operator not following procedures

**Resolution**: Restored from backup, created proper scripts

**Prevention**: All config modifications must go through scripts
that backup first

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | ✅ Success |
| **Total Duration** | ~5 hours |
| **Coral Inference Speed** | 7.8ms |
| **CPU Load Reduction** | 98% |
| **Cameras Working** | 2/3 |
| **Old Recordings Preserved** | 88GB recordings + 1.1GB clips |

### Performance Comparison

| Metric | Before (OpenVINO/CPU) | After (Coral TPU) |
|--------|----------------------|-------------------|
| Load Average | 1.51 | 0.34 |
| CPU Usage | 67.7% | 1.6% |
| Inference Speed | 9.43ms | 10.0ms |
| Frigate CPU | ~287% | 6.2% |
```

### What the Action Log Reveals

This deployment took 5 hours—much longer than the "1 hour" I initially estimated. But the action log shows exactly why:

1. **Phase 1.5 was unexpected** - GPU driver blacklist from a previous project
2. **Phase 2 required blueprint fixes** - Missing firmware loading scripts
3. **Process violations occurred** - Direct config edits without backup

Without the action log, these lessons would be lost. The next deployment will be faster because the blueprint now includes all the fixes.

---

## The Feedback Loop

The real power of this system is the feedback loop:

```
Deploy using Blueprint
     ↓
Fill in Action Log Template
     ↓
Document Issues Encountered
     ↓
Update Blueprint with fixes
     ↓
Update Template if structure changed
     ↓
Next deployment is better
```

### Reconciliation: Keeping Documents in Sync

After every deployment, I reconcile the three documents:

1. **Blueprint → Template**: Does the template have sections for every blueprint phase?
2. **Action Log → Blueprint**: Did we discover issues that need blueprint updates?
3. **Template → Action Log**: Is the template structure sufficient for documenting real deployments?

Example reconciliation from this deployment:

| Issue Found | Blueprint Update | Template Update |
|-------------|------------------|-----------------|
| Phase 9 naming inconsistent | Already "Coral Verification" | Changed from "Final Verification" |
| Missing recordings migration | Added to Phase 10 | Added Step 10.4 |
| Stale follow-up actions | N/A | Removed "add cameras" (now Phase 11) |

---

## Why This Works for AI-Assisted Operations

I use Claude Code as my deployment operator, and this methodology is particularly effective for AI assistance:

1. **Structured context**: The blueprint gives the AI complete information
2. **Verification steps**: Each phase has explicit success criteria
3. **Error recovery**: Troubleshooting section provides remediation paths
4. **Learning capture**: Issues section ensures discoveries aren't lost

The action log also serves as a prompt for the AI: "Follow the blueprint, fill in the template, document any deviations."

---

## Getting Started

Want to try this methodology? Start simple:

### 1. Pick a Repeatable Task
Choose something you've done before (or will do again): setting up a new service, migrating a database, deploying to a new host.

### 2. Write the Blueprint First
Document what you know. Include:
- Prerequisites
- Step-by-step phases
- Success criteria
- Rollback procedure

### 3. Create the Template
Convert your blueprint into a fill-in-the-blank form with:
- Timestamp fields
- Output paste sections
- Status indicators
- Issues section

### 4. Execute and Document
Run through the deployment, filling in the template as you go. Be honest about what broke.

### 5. Reconcile
Update your blueprint with lessons learned. Adjust the template if the structure was insufficient.

---

## Conclusion

The blueprint/template/action-log methodology transforms ad-hoc deployments into repeatable, improvable processes. Each deployment makes the next one better.

For this Frigate + Coral deployment:
- **First attempt**: 4+ hours, multiple failures, undocumented fixes
- **With methodology**: 5 hours, all issues documented, blueprint improved
- **Next deployment**: Estimated 1-2 hours with updated blueprint

The time investment in documentation pays dividends in reliability and knowledge preservation.

---

## Resources

- [Blueprint: Frigate Coral LXC Deployment](../troubleshooting/blueprint-frigate-coral-lxc-deployment.md)
- [Action Log Template](../templates/action-log-template-frigate-coral-lxc.md)
- [Action Log: still-fawn Deployment](../troubleshooting/action-log-still-fawn-frigate-coral.md)
- [Frigate Documentation](https://docs.frigate.video/)
- [Google Coral Documentation](https://coral.ai/docs/)

---

*This post was written while deploying Frigate with Coral USB TPU passthrough to an LXC container on Proxmox VE. The deployment was executed by Claude Code AI agent, with human oversight for hardware operations (plugging in the USB device and moving the hard drive).*
