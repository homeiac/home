# Documentation Templates Summary

**Created**: October 19, 2025
**Purpose**: Summary of documentation standards for GRUB/MAAS image fix

## Key Documentation Standards

### 1. **Action Log** (Real-time troubleshooting journal)
**Location**: `docs/troubleshooting/action-log-*.md`

**Format**:
```markdown
# Action Log: [Brief Title]

**Date**: [Date]
**Issue**: [One-line problem statement]
**Trace URL** (if applicable): [URL]

## Initial Plan
- **Goal**: [What we're trying to achieve]
- **Approach**: [How we'll approach it]
- **Success Criteria**: [How we know it worked]

## Investigation Phase
| Time | Command/Action | Result | Impact on Plan |
|------|---------------|--------|---------------|
| HH:MM | Command executed | What happened | ✓/❌ and next steps |
| HH:MM | Next action | Result | Plan adjustment |

## LESSONS LEARNED - [Topic] Protocol
- Critical validation rules discovered
- Mandatory steps to prevent future issues
```

**Purpose**: Chronicle every command, result, and decision in real-time during debugging

---

### 2. **RCA (Root Cause Analysis)** (Post-mortem analysis)
**Location**: `docs/source/rca/rca-YYYY-MM-DD-*.md`

**Format**:
```markdown
# Root Cause Analysis: [Issue] - [Date]

## Incident Summary
**Date**: YYYY-MM-DD
**Time Window**: HH:MM - HH:MM
**Duration**: X minutes
**Severity**: [Low/Medium/High]
**Status**: [Resolved/In Progress]

### Impact
- What broke
- What was affected
- Severity of impact

## Timeline
| Time | Event |
|------|-------|
| HH:MM | Event description |

## Root Cause Analysis
### Primary Root Cause
[Technical deep dive]

### Secondary Contributing Factors
[Other factors]

### Technical Details
[Code snippets, logs, configuration]

## Resolution
### Immediate Actions Taken
[What was done to fix it]

### Root Cause Resolution Status
- ✅ Completed items
- ❌ Outstanding items
- ⚠️ Warnings/caveats

## Prevention Measures
### Short-term (Completed)
### Long-term Recommendations
```

**Purpose**: Comprehensive post-incident analysis with root cause and prevention

---

### 3. **Runbook** (Repeatable procedures)
**Location**: `docs/runbooks/*.md` or `docs/source/md/runbooks/*.md`

**Format**:
```markdown
# [Task] Runbook

**Purpose**: [What this solves]
**Last Updated**: [Date]
**Incident Reference**: [Related RCA if applicable]

## Quick Diagnosis Checklist
### Symptoms
- [ ] Symptom 1
- [ ] Symptom 2

### Prerequisites
- [ ] Required access
- [ ] Required tools

## Step 1: [Action]
### [Sub-step]
```bash
# Command with explanation
command here
```

**✅ Success Criteria**: [What success looks like]
**❌ Failure Indicators**: [What failure looks like]

## Step 2: [Next Action]
[Repeat format]
```

**Purpose**: Step-by-step reproducible procedures for common tasks

---

### 4. **Hardware-Specific Guide** (Example: ATOPNUC MA90)
**Location**: `docs/source/md/guides/packer-maas-*.md`

**Format**: See `packer-maas-ma90.md`

**Key Elements**:
1. **The error that started it all** (exact error messages)
2. **Hardware quirks** (BIOS settings, boot order)
3. **Changes made** (exact file diffs, script content)
4. **Build + upload commands** (exact commands used)
5. **Next time checklist** (reproducible steps)

**Purpose**: Hardware-specific deployment notes with exact commands

---

## Application to Current Task: GRUB Fix for Intel Xeon P520

### Required Documentation

1. **Action Log**: `docs/troubleshooting/action-log-pumped-piglet-grub-fix.md`
   - Real-time chronicle of investigation
   - Every command executed
   - Every result and plan adjustment

2. **Hardware-Specific Guide**: `docs/source/md/guides/packer-maas-p520.md`
   - Based on `packer-maas-ma90.md` template
   - Intel Xeon P520 specific (NOT AMD)
   - Script name: `my-intel-xeon-changes.sh` (NOT `my-amd-changes.sh`)
   - Exact error messages from logs
   - BIOS/UEFI settings (Secure Boot enabled)
   - Build and deployment commands

3. **RCA** (if needed): `docs/source/rca/rca-2025-10-19-grub-cloud-amd64-uefi-conflict.md`
   - Why `grub-cloud-amd64` causes failures on UEFI-only systems
   - Technical analysis of package dependencies
   - Prevention measures for future images

### Script Naming Convention

**CRITICAL**: Script name must match hardware:
- ❌ `my-amd-changes.sh` (wrong - P520 is Intel Xeon)
- ✅ `my-intel-xeon-changes.sh` (correct)
- ✅ `my-p520-changes.sh` (also acceptable)

### Reference: AMD MA90 vs Intel P520

| Hardware | CPU | Script Name | Boot Mode |
|----------|-----|-------------|-----------|
| ATOPNUC MA90 | AMD A9-9400 | `my-amd-changes.sh` | UEFI forced |
| ThinkStation P520 | Intel Xeon | `my-intel-xeon-changes.sh` | UEFI + Secure Boot |

---

## Next Steps

1. ✅ Read all documentation templates
2. ⏭️ Create Action Log (start chronicling)
3. ⏭️ Create Hardware Guide for P520
4. ⏭️ Create/Update scripts with correct naming
5. ⏭️ Execute fix with full documentation
6. ⏭️ Create RCA if needed

---

**Tags**: documentation, standards, templates, action-log, rca, runbook, hardware-guide
