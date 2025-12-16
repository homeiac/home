#!/usr/bin/env bats
#
# Tests for quick-triage.sh
# Run with: bats scripts/perf/tests/quick-triage.bats
#

setup() {
    SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
    SCRIPT="$SCRIPT_DIR/quick-triage.sh"
}

# ============================================================================
# SCRIPT EXISTENCE
# ============================================================================

@test "quick-triage.sh exists and is executable" {
    [[ -x "$SCRIPT" ]]
}

@test "--help shows usage information" {
    run "$SCRIPT" --help
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ "60-Second" ]] || [[ "$output" =~ "triage" ]]
}

# ============================================================================
# 10 TRIAGE COMMANDS (Brendan Gregg's 60-second checklist)
# ============================================================================

@test "Includes uptime command" {
    run grep "uptime" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Includes dmesg command" {
    run grep "dmesg" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Includes vmstat command" {
    run grep "vmstat" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Includes mpstat command" {
    run grep "mpstat" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Includes pidstat command" {
    run grep "pidstat" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Includes iostat command" {
    run grep "iostat" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Includes free command" {
    run grep "free" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Includes sar for network" {
    run grep "sar.*DEV" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Includes sar for TCP" {
    run grep "sar.*TCP" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Includes top command" {
    run grep "top" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

# ============================================================================
# OUTPUT FORMAT
# ============================================================================

@test "Has section headers" {
    run grep "print_section" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Shows what to look for" {
    run grep "What to look for" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Highlights errors in output" {
    run grep -i "error\|fail\|oom" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

# ============================================================================
# CONTEXT SUPPORT
# ============================================================================

@test "Supports --context flag" {
    run grep "\-\-context" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Supports ssh context" {
    run grep "ssh" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

# ============================================================================
# NEXT STEPS
# ============================================================================

@test "Suggests deep-dive scripts" {
    run grep "deep-dive" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Suggests use-checklist.sh" {
    run grep "use-checklist" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}
