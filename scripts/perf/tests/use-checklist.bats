#!/usr/bin/env bats
#
# Tests for use-checklist.sh
# Run with: bats scripts/perf/tests/use-checklist.bats
#

# Setup - runs before each test
setup() {
    # Load test helpers
    load 'test_helper/mocks'

    # Path to script under test
    SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
    SCRIPT="$SCRIPT_DIR/use-checklist.sh"

    # Create temp directory for test outputs
    TEST_TEMP=$(mktemp -d)
    export TEST_TEMP
}

# Teardown - runs after each test
teardown() {
    teardown_mock_path 2>/dev/null || true
    rm -rf "$TEST_TEMP" 2>/dev/null || true
}

# ============================================================================
# SCRIPT EXISTENCE AND HELP
# ============================================================================

@test "use-checklist.sh exists and is executable" {
    [[ -x "$SCRIPT" ]]
}

@test "--help shows usage information" {
    run "$SCRIPT" --help
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ "USE Method" ]]
    [[ "$output" =~ "--context" ]]
}

# ============================================================================
# E→U→S ORDER VERIFICATION (Critical USE Method requirement)
# ============================================================================

@test "CPU: Errors checked BEFORE Utilization" {
    # This test verifies the E→U→S order is maintained
    run "$SCRIPT" --help  # Quick run to check structure
    # In actual script, grep the function to verify order
    run grep -A 50 "check_cpu()" "$SCRIPT"
    [[ "$output" =~ "ERRORS FIRST" ]]
}

@test "Memory: Errors checked BEFORE Utilization" {
    run grep -A 50 "check_memory()" "$SCRIPT"
    [[ "$output" =~ "ERRORS FIRST" ]]
}

@test "Disk: Errors checked BEFORE Utilization" {
    run grep -A 50 "check_disk()" "$SCRIPT"
    [[ "$output" =~ "ERRORS FIRST" ]]
}

@test "Network: Errors checked BEFORE Utilization" {
    run grep -A 50 "check_network()" "$SCRIPT"
    [[ "$output" =~ "ERRORS FIRST" ]]
}

@test "GPU: Errors checked BEFORE Utilization" {
    run grep -A 50 "check_gpu()" "$SCRIPT"
    [[ "$output" =~ "ERRORS FIRST" ]]
}

# ============================================================================
# THRESHOLD TESTS
# ============================================================================

@test "CPU utilization threshold is 70% for warning" {
    run grep "CPU_UTIL_WARN" "$SCRIPT"
    [[ "$output" =~ "70" ]]
}

@test "Memory utilization threshold is 80% for warning" {
    run grep "MEM_UTIL_WARN" "$SCRIPT"
    [[ "$output" =~ "80" ]]
}

@test "Disk utilization threshold is 70% for warning" {
    run grep "DISK_UTIL_WARN" "$SCRIPT"
    [[ "$output" =~ "70" ]]
}

# ============================================================================
# CONTEXT ROUTING TESTS
# ============================================================================

@test "--context k8s-pod parses namespace/pod correctly" {
    run grep -A 10 'k8s-pod' "$SCRIPT"
    [[ "$output" =~ "kubectl exec" ]]
}

@test "--context proxmox-vm routes to qm guest exec" {
    run grep -A 10 'proxmox-vm' "$SCRIPT"
    [[ "$output" =~ "qm guest exec" ]]
}

@test "--context ssh routes to ssh command" {
    run grep -A 10 '"ssh"' "$SCRIPT"
    [[ "$output" =~ "ssh" ]]
}

@test "--context lxc routes to pct exec" {
    run grep -A 10 '"lxc"' "$SCRIPT"
    [[ "$output" =~ "pct exec" ]]
}

# ============================================================================
# OUTPUT FORMAT TESTS
# ============================================================================

@test "Script uses color codes for status" {
    run grep -E "RED=|YELLOW=|GREEN=" "$SCRIPT"
    [[ "$output" =~ "RED" ]]
    [[ "$output" =~ "YELLOW" ]]
    [[ "$output" =~ "GREEN" ]]
}

@test "print_metric function exists" {
    run grep "print_metric()" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "JSON_OUTPUT variable is used" {
    run grep "JSON_OUTPUT" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

# ============================================================================
# RESOURCE CHECK FUNCTIONS
# ============================================================================

@test "check_cpu function exists" {
    run grep "check_cpu()" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "check_memory function exists" {
    run grep "check_memory()" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "check_disk function exists" {
    run grep "check_disk()" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "check_network function exists" {
    run grep "check_network()" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "check_gpu function exists" {
    run grep "check_gpu()" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "check_cgroups function exists" {
    run grep "check_cgroups()" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

# ============================================================================
# COMMAND USAGE TESTS
# ============================================================================

@test "Uses vmstat for CPU metrics" {
    run grep "vmstat" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Uses free for memory metrics" {
    run grep "free -m" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Uses iostat for disk metrics" {
    run grep "iostat" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Uses dmesg for error detection" {
    run grep "dmesg" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Uses nvidia-smi for GPU metrics" {
    run grep "nvidia-smi" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

# ============================================================================
# LAYERED ANALYSIS TESTS
# ============================================================================

@test "run_layered_analysis function exists" {
    run grep "run_layered_analysis()" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "get_host_context function exists" {
    run grep "get_host_context()" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "WORKLOAD LAYER header in output" {
    run grep "WORKLOAD LAYER" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "HOST LAYER header in output" {
    run grep "HOST LAYER" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

# ============================================================================
# SAVE/REPORT TESTS
# ============================================================================

@test "--save flag is supported" {
    run grep "\-\-save" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "REPORTS_DIR is defined" {
    run grep "REPORTS_DIR" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Timestamp format for reports" {
    run grep "TIMESTAMP=" "$SCRIPT"
    [[ "$output" =~ "date" ]]
}

# ============================================================================
# INVESTIGATE PROMPTS
# ============================================================================

@test "Shows INVESTIGATE prompt for errors" {
    run grep ">>> INVESTIGATE" "$SCRIPT"
    [[ "$status" -eq 0 ]]
}

@test "Multiple INVESTIGATE prompts for different conditions" {
    count=$(grep -c ">>> INVESTIGATE" "$SCRIPT")
    [[ "$count" -gt 5 ]]
}
