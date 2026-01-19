#!/usr/bin/env bats
#
# Behavioral tests for Claude Code USE Method methodology
# These tests validate that CLAUDE.md contains the correct structure
# to trigger systematic performance diagnosis.
#
# Run with: bats scripts/perf/tests/behavioral/methodology.bats
#

setup() {
    SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
    REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
    export SCRIPT_DIR REPO_ROOT
}

# ============================================================================
# CLAUDE.MD STRUCTURE TESTS
# ============================================================================

@test "CLAUDE.md exists" {
    [[ -f "$REPO_ROOT/CLAUDE.md" ]]
}

@test "CLAUDE.md contains Performance Diagnosis section" {
    run grep -c "Performance Diagnosis" "$REPO_ROOT/CLAUDE.md"
    [[ "$status" -eq 0 ]]
    [[ "$output" -ge 1 ]]
}

@test "Performance Diagnosis section mentions USE Method" {
    run grep -A 30 "Performance Diagnosis" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "USE Method" ]]
}

@test "Performance Diagnosis section mentions OpenMemory" {
    run grep -A 30 "Performance Diagnosis" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "OpenMemory" ]] || [[ "$output" =~ "openmemory" ]]
}

# ============================================================================
# TRIGGER KEYWORD TESTS
# ============================================================================

@test "Trigger keywords include 'slow'" {
    run grep -i "trigger" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "slow" ]]
}

@test "Trigger keywords include 'latency'" {
    run grep -i "trigger" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "latency" ]]
}

@test "Trigger keywords include 'performance'" {
    run grep -i "trigger" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "performance" ]]
}

@test "Trigger keywords include 'timeout'" {
    run grep -i "trigger" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "timeout" ]]
}

@test "Trigger keywords include 'unresponsive'" {
    run grep -i "trigger" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "unresponsive" ]]
}

# ============================================================================
# STEP ORDER TESTS
# ============================================================================

@test "OpenMemory check is Step 1 (first)" {
    # Extract the steps section and verify OpenMemory is first
    run grep -A 10 "RECOMMENDED STEPS" "$REPO_ROOT/CLAUDE.md"
    # First numbered step should mention OpenMemory (check for "1." followed by OpenMemory)
    [[ "$output" =~ "1.".*"OpenMemory" ]] || [[ "$output" =~ "Check OpenMemory FIRST" ]]
}

@test "USE Method is Step 2 (after OpenMemory check)" {
    run grep -A 15 "RECOMMENDED STEPS" "$REPO_ROOT/CLAUDE.md"
    # Should have USE Method or diagnose.sh in step 2
    [[ "$output" =~ "2.".*"USE Method" ]] || [[ "$output" =~ "2.".*"diagnose" ]]
}

# ============================================================================
# SCRIPT REFERENCE TESTS
# ============================================================================

@test "diagnose.sh is referenced" {
    run grep "diagnose.sh" "$REPO_ROOT/CLAUDE.md"
    [[ "$status" -eq 0 ]]
}

@test "Target contexts are documented" {
    run grep -A 5 "diagnose.sh" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "proxmox-vm" ]]
    [[ "$output" =~ "k8s-pod" ]] || [[ "$output" =~ "ssh:" ]]
}

@test "HAOS VM context (116) is documented" {
    run grep -i "116" "$REPO_ROOT/CLAUDE.md"
    [[ "$status" -eq 0 ]]
}

# ============================================================================
# ANTI-PATTERN TESTS
# ============================================================================

@test "Anti-patterns section exists" {
    run grep -i "anti-pattern" "$REPO_ROOT/CLAUDE.md"
    [[ "$status" -eq 0 ]]
}

@test "Anti-pattern: jumping to conclusions" {
    run grep -A 10 "ANTI-PATTERN" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "without data" ]] || [[ "$output" =~ "probably" ]]
}

@test "Anti-pattern: skipping USE Method" {
    run grep -A 10 "ANTI-PATTERN" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "Skipping" ]] || [[ "$output" =~ "skipping" ]]
}

@test "Anti-pattern: not checking OpenMemory" {
    run grep -A 10 "ANTI-PATTERN" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "OpenMemory" ]] || [[ "$output" =~ "memory" ]]
}

# ============================================================================
# METHODOLOGY REQUIREMENTS
# ============================================================================

@test "E->U->S order mentioned" {
    run grep -i "error.*utilization.*saturation\|E.*U.*S" "$REPO_ROOT/CLAUDE.md"
    [[ "$status" -eq 0 ]]
}

@test "All resources mentioned (CPU, Memory, Disk, Network)" {
    run grep -A 30 "Performance Diagnosis" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "CPU" ]]
    [[ "$output" =~ "Memory" ]]
    [[ "$output" =~ "Disk" ]]
    [[ "$output" =~ "Network" ]]
}

@test "Layered analysis mentioned" {
    run grep -A 30 "Performance Diagnosis" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "layer" ]] || [[ "$output" =~ "host" ]]
}

@test "Resolution storage mentioned (openmemory_lgm_store)" {
    run grep -A 40 "Performance Diagnosis" "$REPO_ROOT/CLAUDE.md"
    [[ "$output" =~ "openmemory_lgm_store" ]] || [[ "$output" =~ "Store resolution" ]]
}

# ============================================================================
# RUNBOOK REFERENCE TESTS
# ============================================================================

@test "Runbook reference exists" {
    run grep "performance-diagnosis-runbook" "$REPO_ROOT/CLAUDE.md"
    [[ "$status" -eq 0 ]]
}

@test "Runbook file exists" {
    [[ -f "$REPO_ROOT/docs/methodology/performance-diagnosis-runbook.md" ]]
}

# ============================================================================
# BEHAVIORAL TEST SCENARIOS EXIST
# ============================================================================

@test "Voice PE test scenario exists" {
    [[ -f "$SCRIPT_DIR/voice-pe-already-solved.md" ]]
}

@test "Frigate CPU test scenario exists" {
    [[ -f "$SCRIPT_DIR/frigate-high-cpu.md" ]]
}

@test "HAOS memory test scenario exists" {
    [[ -f "$SCRIPT_DIR/haos-memory-pressure.md" ]]
}
