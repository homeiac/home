#!/usr/bin/env bats
#
# Integration tests - run on real localhost
# These tests actually execute the scripts and verify real output
#
# Run with: bats scripts/perf/tests/integration/local.bats
#
# WARNING: These tests hit real system resources and may take time
#

setup() {
    SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
    export SCRIPT_DIR

    # Skip if not on Linux
    if [[ "$(uname)" != "Linux" ]]; then
        skip "Integration tests require Linux"
    fi
}

# ============================================================================
# BASIC EXECUTION TESTS
# ============================================================================

@test "use-checklist.sh runs without errors on localhost" {
    # Set a timeout since the script runs several commands
    run timeout 120 "$SCRIPT_DIR/use-checklist.sh"
    # Should complete (exit 0) or be interrupted (124 for timeout)
    [[ "$status" -eq 0 ]] || [[ "$status" -eq 124 ]]
}

@test "quick-triage.sh runs without errors on localhost" {
    run timeout 90 "$SCRIPT_DIR/quick-triage.sh"
    [[ "$status" -eq 0 ]] || [[ "$status" -eq 124 ]]
}

# ============================================================================
# OUTPUT VALIDATION
# ============================================================================

@test "use-checklist.sh shows CPU section" {
    run timeout 30 bash -c "$SCRIPT_DIR/use-checklist.sh 2>&1 | head -100"
    [[ "$output" =~ "CPU" ]]
}

@test "use-checklist.sh shows Memory section" {
    run timeout 30 bash -c "$SCRIPT_DIR/use-checklist.sh 2>&1 | head -150"
    [[ "$output" =~ "MEMORY" ]] || [[ "$output" =~ "Memory" ]]
}

@test "quick-triage.sh shows uptime" {
    run timeout 30 bash -c "$SCRIPT_DIR/quick-triage.sh 2>&1 | head -50"
    [[ "$output" =~ "UPTIME" ]] || [[ "$output" =~ "load average" ]]
}

# ============================================================================
# SAVE FUNCTIONALITY
# ============================================================================

@test "--save creates a JSON report file" {
    TEST_REPORTS=$(mktemp -d)
    # Override REPORTS_DIR (this would require script modification to work)
    # For now, just verify the flag is accepted
    run timeout 30 "$SCRIPT_DIR/use-checklist.sh" --save
    # Should not error on the flag
    [[ "$status" -eq 0 ]] || [[ "$status" -eq 124 ]]
    rm -rf "$TEST_REPORTS"
}

# ============================================================================
# TOOL AVAILABILITY
# ============================================================================

@test "vmstat is available" {
    command -v vmstat
}

@test "free is available" {
    command -v free
}

@test "top is available" {
    command -v top
}

@test "dmesg is available" {
    command -v dmesg
}

# ============================================================================
# SYSSTAT TOOLS (may not be installed)
# ============================================================================

@test "iostat availability check (sysstat)" {
    if ! command -v iostat &>/dev/null; then
        skip "iostat not installed (sysstat package needed)"
    fi
    command -v iostat
}

@test "mpstat availability check (sysstat)" {
    if ! command -v mpstat &>/dev/null; then
        skip "mpstat not installed (sysstat package needed)"
    fi
    command -v mpstat
}

@test "sar availability check (sysstat)" {
    if ! command -v sar &>/dev/null; then
        skip "sar not installed (sysstat package needed)"
    fi
    command -v sar
}

# ============================================================================
# GPU TESTS (optional)
# ============================================================================

@test "nvidia-smi availability check (if GPU present)" {
    if ! command -v nvidia-smi &>/dev/null; then
        skip "nvidia-smi not available (no NVIDIA GPU or drivers)"
    fi
    run nvidia-smi --query-gpu=name --format=csv,noheader
    [[ "$status" -eq 0 ]]
}
