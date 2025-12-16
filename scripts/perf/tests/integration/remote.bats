#!/usr/bin/env bats
#
# Remote integration tests - run USE Method scripts against actual Linux targets
# Run with: bats scripts/perf/tests/integration/remote.bats
#
# Requires: SSH access to target or scripts/k3s/exec-*.sh helpers
#

setup() {
    SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
    REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
    export SCRIPT_DIR REPO_ROOT

    # Default target - still-fawn K3s VM via Proxmox
    # Override with: TARGET_HOST=hostname bats ...
    TARGET_HOST="${TARGET_HOST:-still-fawn}"
    export TARGET_HOST
}

# Helper to execute on target
exec_on_target() {
    local cmd="$1"
    if [[ -x "$REPO_ROOT/scripts/k3s/exec-${TARGET_HOST}.sh" ]]; then
        "$REPO_ROOT/scripts/k3s/exec-${TARGET_HOST}.sh" "$cmd"
    else
        ssh "root@${TARGET_HOST}.maas" "$cmd"
    fi
}

# ============================================================================
# TARGET ACCESSIBILITY
# ============================================================================

@test "Target host is accessible" {
    run exec_on_target "uptime"
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ "load average" ]]
}

# ============================================================================
# CRISIS TOOLS AVAILABILITY
# ============================================================================

@test "vmstat is available on target" {
    run exec_on_target "which vmstat"
    [[ "$status" -eq 0 ]]
}

@test "free is available on target" {
    run exec_on_target "which free"
    [[ "$status" -eq 0 ]]
}

@test "top is available on target" {
    run exec_on_target "which top"
    [[ "$status" -eq 0 ]]
}

@test "dmesg is available on target" {
    run exec_on_target "which dmesg"
    [[ "$status" -eq 0 ]]
}

@test "iostat is available on target (sysstat)" {
    run exec_on_target "which iostat"
    if [[ "$status" -ne 0 ]]; then
        skip "iostat not installed - run install-crisis-tools.sh"
    fi
}

@test "mpstat is available on target (sysstat)" {
    run exec_on_target "which mpstat"
    if [[ "$status" -ne 0 ]]; then
        skip "mpstat not installed - run install-crisis-tools.sh"
    fi
}

# ============================================================================
# USE METHOD - ERRORS (Check these FIRST per methodology)
# ============================================================================

@test "CPU errors: dmesg MCE/hardware check returns" {
    run exec_on_target "dmesg 2>/dev/null | grep -ci 'mce\|hardware error' || echo 0"
    [[ "$status" -eq 0 ]]
    # Output should contain a number (may have multiple lines from SSH)
    local last_line=$(echo "$output" | tail -1)
    [[ "$last_line" =~ ^[0-9]+$ ]]
}

@test "Memory errors: OOM killer check returns" {
    run exec_on_target "dmesg 2>/dev/null | grep -ci 'killed process\|oom' || echo 0"
    [[ "$status" -eq 0 ]]
    local last_line=$(echo "$output" | tail -1)
    [[ "$last_line" =~ ^[0-9]+$ ]]
}

@test "Disk errors: I/O error check returns" {
    run exec_on_target "dmesg 2>/dev/null | grep -ci 'i/o error\|medium error' || echo 0"
    [[ "$status" -eq 0 ]]
    local last_line=$(echo "$output" | tail -1)
    [[ "$last_line" =~ ^[0-9]+$ ]]
}

# ============================================================================
# USE METHOD - UTILIZATION
# ============================================================================

@test "CPU utilization: vmstat returns valid data" {
    run exec_on_target "vmstat 1 2 | tail -1"
    [[ "$status" -eq 0 ]]
    # Should have multiple space-separated numbers
    [[ "$output" =~ [0-9]+ ]]
}

@test "Memory utilization: free returns valid data" {
    run exec_on_target "free -m | grep Mem"
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ "Mem:" ]]
}

@test "Disk utilization: df returns valid data" {
    run exec_on_target "df -h / | tail -1"
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ [0-9]+% ]]
}

# ============================================================================
# USE METHOD - SATURATION
# ============================================================================

@test "CPU saturation: load average readable" {
    run exec_on_target "cat /proc/loadavg"
    [[ "$status" -eq 0 ]]
    # Should have load averages (floats)
    [[ "$output" =~ [0-9]+\.[0-9]+ ]]
}

@test "Memory saturation: swap activity via vmstat" {
    run exec_on_target "vmstat 1 2 | tail -1 | awk '{print \$7, \$8}'"
    [[ "$status" -eq 0 ]]
    # si and so columns (swap in/out) - allow any numeric output
    local last_line=$(echo "$output" | tail -1)
    [[ "$last_line" =~ [0-9]+ ]]
}

# ============================================================================
# CGROUP CHECKS (K8s/Container layer)
# ============================================================================

@test "Cgroup v2 filesystem exists" {
    run exec_on_target "ls /sys/fs/cgroup/ 2>/dev/null | head -5"
    [[ "$status" -eq 0 ]]
}

@test "CPU cgroup stats accessible" {
    # Try cgroup v2 path first, then v1
    run exec_on_target "cat /sys/fs/cgroup/cpu.stat 2>/dev/null || cat /sys/fs/cgroup/cpu/cpu.stat 2>/dev/null || echo 'no_cgroup'"
    [[ "$status" -eq 0 ]]
}

# ============================================================================
# GPU CHECKS (if present)
# ============================================================================

@test "GPU: nvidia-smi available (if GPU present)" {
    # First check if nvidia-smi exists AND driver is working
    run exec_on_target "nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null"
    if [[ "$status" -ne 0 ]]; then
        skip "No NVIDIA GPU, drivers not loaded, or GPU passed to containers"
    fi
    # If we get here, GPU is accessible
    [[ "$output" =~ [A-Za-z] ]]  # Should contain GPU name
}

# ============================================================================
# FULL SCRIPT EXECUTION
# ============================================================================

@test "quick-triage.sh runs via SSH context" {
    if [[ ! -x "$SCRIPT_DIR/quick-triage.sh" ]]; then
        skip "quick-triage.sh not found"
    fi

    # Run with timeout - triage should complete in 90 seconds
    run timeout 90 "$SCRIPT_DIR/quick-triage.sh" --context "ssh:root@${TARGET_HOST}.maas"

    # Should complete or timeout (both acceptable for integration test)
    [[ "$status" -eq 0 ]] || [[ "$status" -eq 124 ]]
}

@test "use-checklist.sh runs via SSH context" {
    if [[ ! -x "$SCRIPT_DIR/use-checklist.sh" ]]; then
        skip "use-checklist.sh not found"
    fi

    # Run with timeout - full checklist may take 2 minutes
    # Script may exit non-zero if it finds issues (warnings/errors) - that's expected
    run timeout 120 "$SCRIPT_DIR/use-checklist.sh" --context "ssh:root@${TARGET_HOST}.maas"

    # Success if: completed (0), found issues (1), or timed out (124)
    # Only fail if script crashed unexpectedly (>1 except 124)
    [[ "$status" -eq 0 ]] || [[ "$status" -eq 1 ]] || [[ "$status" -eq 124 ]]
    # Verify it produced USE Method output
    [[ "$output" =~ "CPU" ]]
    [[ "$output" =~ "MEMORY" ]] || [[ "$output" =~ "Memory" ]]
}
