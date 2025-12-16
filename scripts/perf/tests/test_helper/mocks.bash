#!/bin/bash
#
# Mock functions for testing USE Method scripts
# These replace system commands with predictable outputs
#

# ============================================================================
# VMSTAT MOCKS
# ============================================================================

# Normal system - 5% CPU idle
mock_vmstat_normal() {
    cat << 'EOF'
procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
 1  0      0 500000 100000 200000    0    0     0     0  100  200 10  5 85  0  0
EOF
}

# High CPU utilization - 5% idle (95% busy)
mock_vmstat_high_cpu() {
    cat << 'EOF'
procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
 1  0      0 500000 100000 200000    0    0     0     0  100  200 85 10  5  0  0
EOF
}

# CPU saturation - run queue (r) > CPU count
mock_vmstat_saturated() {
    cat << 'EOF'
procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
15  0      0 500000 100000 200000    0    0     0     0  100  200 85 10  5  0  0
EOF
}

# Swapping - si/so > 0
mock_vmstat_swapping() {
    cat << 'EOF'
procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
 1  0  50000  50000 100000 200000  500  300     0     0  100  200 50 10 40  0  0
EOF
}

# ============================================================================
# FREE MOCKS
# ============================================================================

mock_free_normal() {
    cat << 'EOF'
              total        used        free      shared  buff/cache   available
Mem:          16000        8000        4000         500        4000        7500
Swap:          2000           0        2000
EOF
}

mock_free_low_memory() {
    cat << 'EOF'
              total        used        free      shared  buff/cache   available
Mem:          16000       15500         100         500         400         200
Swap:          2000        1800         200
EOF
}

# ============================================================================
# DMESG MOCKS
# ============================================================================

mock_dmesg_clean() {
    cat << 'EOF'
[    0.000000] Linux version 5.15.0 (gcc version 11.2.0)
[    0.100000] Kernel command line: BOOT_IMAGE=/boot/vmlinuz
[    1.000000] ACPI: Core revision 20210730
[   10.000000] systemd[1]: Started Network Manager.
EOF
}

mock_dmesg_oom() {
    cat << 'EOF'
[    0.000000] Linux version 5.15.0 (gcc version 11.2.0)
[12345.678901] java invoked oom-killer: gfp_mask=0x1100cca
[12345.678902] Out of memory: Killed process 1234 (java) total-vm:8000000kB
[12345.678903] oom_reaper: reaped process 1234 (java), now anon-rss:0kB
EOF
}

mock_dmesg_mce() {
    cat << 'EOF'
[    0.000000] Linux version 5.15.0 (gcc version 11.2.0)
[54321.123456] mce: [Hardware Error]: Machine check events logged
[54321.123457] mce: [Hardware Error]: CPU 0: Machine Check Exception
EOF
}

mock_dmesg_io_error() {
    cat << 'EOF'
[    0.000000] Linux version 5.15.0 (gcc version 11.2.0)
[99999.999999] blk_update_request: I/O error, dev sda, sector 12345
[99999.999999] Buffer I/O error on dev sda1, logical block 1000
EOF
}

mock_dmesg_gpu_xid() {
    cat << 'EOF'
[    0.000000] Linux version 5.15.0 (gcc version 11.2.0)
[88888.888888] NVRM: Xid (PCI:0000:01:00): 79, GPU has fallen off the bus
EOF
}

# ============================================================================
# IOSTAT MOCKS
# ============================================================================

mock_iostat_normal() {
    cat << 'EOF'
Linux 5.15.0 (hostname)     12/15/2025     _x86_64_    (8 CPU)

Device             r/s     w/s     rkB/s     wkB/s   await  avgqu-sz  %util
sda              10.00   20.00    100.00    200.00    5.00      0.50  15.00
nvme0n1          50.00  100.00   1000.00   2000.00    1.00      0.10   5.00
EOF
}

mock_iostat_high_util() {
    cat << 'EOF'
Linux 5.15.0 (hostname)     12/15/2025     _x86_64_    (8 CPU)

Device             r/s     w/s     rkB/s     wkB/s   await  avgqu-sz  %util
sda             500.00  500.00   5000.00   5000.00   50.00      5.00  95.00
nvme0n1          50.00  100.00   1000.00   2000.00    1.00      0.10   5.00
EOF
}

mock_iostat_saturated() {
    cat << 'EOF'
Linux 5.15.0 (hostname)     12/15/2025     _x86_64_    (8 CPU)

Device             r/s     w/s     rkB/s     wkB/s   await  avgqu-sz  %util
sda             500.00  500.00   5000.00   5000.00  150.00     15.00  98.00
EOF
}

# ============================================================================
# NETWORK MOCKS
# ============================================================================

mock_ip_link_normal() {
    cat << 'EOF'
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    RX:  bytes packets errors dropped  missed   mcast
         1000    100      0       0       0       0
    TX:  bytes packets errors dropped carrier collsns
         1000    100      0       0       0       0
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP mode DEFAULT group default qlen 1000
    link/ether 00:00:00:00:00:01 brd ff:ff:ff:ff:ff:ff
    RX:  bytes packets errors dropped  missed   mcast
    1000000000  1000000      0       0       0       0
    TX:  bytes packets errors dropped carrier collsns
    2000000000  2000000      0       0       0       0
EOF
}

mock_ip_link_errors() {
    cat << 'EOF'
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP mode DEFAULT group default qlen 1000
    link/ether 00:00:00:00:00:01 brd ff:ff:ff:ff:ff:ff
    RX:  bytes packets errors dropped  missed   mcast
    1000000000  1000000    500     100       0       0
    TX:  bytes packets errors dropped carrier collsns
    2000000000  2000000    200      50       0       0
EOF
}

mock_ip_link_drops() {
    cat << 'EOF'
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP mode DEFAULT group default qlen 1000
    link/ether 00:00:00:00:00:01 brd ff:ff:ff:ff:ff:ff
    RX:  bytes packets errors dropped  missed   mcast
    1000000000  1000000      0    5000       0       0
    TX:  bytes packets errors dropped carrier collsns
    2000000000  2000000      0    3000       0       0
EOF
}

# ============================================================================
# NVIDIA-SMI MOCKS
# ============================================================================

mock_nvidia_smi_normal() {
    echo "45"  # GPU utilization %
}

mock_nvidia_smi_high_util() {
    echo "95"  # GPU utilization %
}

mock_nvidia_smi_memory() {
    echo "4000, 8000"  # used MB, total MB
}

mock_nvidia_smi_memory_full() {
    echo "7800, 8000"  # 97.5% used
}

mock_nvidia_smi_temp_normal() {
    echo "55"  # degrees C
}

mock_nvidia_smi_temp_hot() {
    echo "92"  # degrees C - throttling
}

# ============================================================================
# CGROUP MOCKS
# ============================================================================

mock_cgroup_cpu_unlimited() {
    echo "-1"
}

mock_cgroup_cpu_limited() {
    echo "200000"  # 2 CPU cores (quota/period)
}

mock_cgroup_cpu_throttled() {
    cat << 'EOF'
nr_periods 10000
nr_throttled 500
throttled_time 50000000000
EOF
}

mock_cgroup_cpu_not_throttled() {
    cat << 'EOF'
nr_periods 10000
nr_throttled 0
throttled_time 0
EOF
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# Override a command with a mock function
# Usage: mock_command vmstat mock_vmstat_high_cpu
mock_command() {
    local cmd="$1"
    local mock_fn="$2"

    # Create a function that shadows the command
    eval "$cmd() { $mock_fn; }"
    export -f "$cmd"
}

# Restore original command
restore_command() {
    local cmd="$1"
    unset -f "$cmd"
}

# Create temporary directory for mock command binaries
setup_mock_path() {
    MOCK_BIN_DIR=$(mktemp -d)
    export PATH="$MOCK_BIN_DIR:$PATH"
    export MOCK_BIN_DIR
}

# Create a mock binary
create_mock_binary() {
    local name="$1"
    local output="$2"

    cat > "$MOCK_BIN_DIR/$name" << EOF
#!/bin/bash
cat << 'MOCKEOF'
$output
MOCKEOF
EOF
    chmod +x "$MOCK_BIN_DIR/$name"
}

# Cleanup mock binaries
teardown_mock_path() {
    if [[ -n "$MOCK_BIN_DIR" && -d "$MOCK_BIN_DIR" ]]; then
        rm -rf "$MOCK_BIN_DIR"
    fi
}
