#!/bin/bash
#
# Install Linux Crisis Tools
# Based on Brendan Gregg's recommendations:
# https://www.brendangregg.com/blog/2024-03-24/linux-crisis-tools.html
#
# Pre-install these tools BEFORE you need them!
# During a crisis, network may be down, repos unreachable.
#
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

echo -e "${BOLD}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  Linux Crisis Tools Installer                                  ║"
echo "║  Pre-install diagnostic tools before you need them!           ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo -e "${YELLOW}Warning: Not running as root. Will use sudo for package installation.${NC}"
    SUDO="sudo"
else
    SUDO=""
fi

# Detect package manager
detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v yum &>/dev/null; then
        echo "yum"
    elif command -v apk &>/dev/null; then
        echo "apk"
    else
        echo "unknown"
    fi
}

PKG_MANAGER=$(detect_pkg_manager)
echo -e "Detected package manager: ${GREEN}$PKG_MANAGER${NC}"

# ============================================================================
# Package lists by manager
# ============================================================================

# Debian/Ubuntu packages
APT_PACKAGES=(
    # Basic system stats
    procps          # ps, vmstat, uptime, top
    util-linux      # dmesg, lsblk, lscpu
    sysstat         # iostat, mpstat, pidstat, sar

    # Network tools
    iproute2        # ip, ss, nstat, tc
    tcpdump         # packet capture
    ethtool         # NIC configuration
    net-tools       # netstat (legacy but useful)

    # Performance profiling
    linux-tools-common      # perf base
    # linux-tools-$(uname -r)  # kernel-specific perf (install separately)

    # eBPF tools (modern tracing)
    bpfcc-tools     # BCC tools: opensnoop, execsnoop, biosnoop, etc.
    bpftrace        # eBPF scripting

    # Additional useful tools
    htop            # better top
    iotop           # I/O by process
    dstat           # versatile resource stats
    nicstat         # NIC statistics
    numactl         # NUMA stats
    trace-cmd       # ftrace frontend
    strace          # syscall tracing
    lsof            # list open files

    # Hardware info
    pciutils        # lspci
    usbutils        # lsusb
    dmidecode       # BIOS/hardware info
    smartmontools   # SMART disk health

    # Misc
    bc              # calculator (for scripts)
    jq              # JSON parsing
)

# RHEL/CentOS/Fedora packages
DNF_PACKAGES=(
    procps-ng
    util-linux
    sysstat
    iproute
    tcpdump
    ethtool
    net-tools
    perf
    bcc-tools
    bpftrace
    htop
    iotop
    dstat
    numactl
    trace-cmd
    strace
    lsof
    pciutils
    usbutils
    dmidecode
    smartmontools
    bc
    jq
)

# Alpine packages
APK_PACKAGES=(
    procps
    util-linux
    sysstat
    iproute2
    tcpdump
    ethtool
    htop
    iotop
    strace
    lsof
    pciutils
    usbutils
    smartmontools
    bc
    jq
)

# ============================================================================
# Installation functions
# ============================================================================

install_apt() {
    echo -e "\n${BOLD}Updating package list...${NC}"
    $SUDO apt-get update

    echo -e "\n${BOLD}Installing crisis tools...${NC}"
    for pkg in "${APT_PACKAGES[@]}"; do
        echo -n "  Installing $pkg... "
        if $SUDO apt-get install -y "$pkg" &>/dev/null; then
            echo -e "${GREEN}OK${NC}"
        else
            echo -e "${YELLOW}SKIP (may not be available)${NC}"
        fi
    done

    # Try to install kernel-specific perf
    KERNEL_VERSION=$(uname -r)
    echo -n "  Installing linux-tools-$KERNEL_VERSION... "
    if $SUDO apt-get install -y "linux-tools-$KERNEL_VERSION" &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}SKIP (kernel headers may be needed)${NC}"
    fi
}

install_dnf() {
    echo -e "\n${BOLD}Installing crisis tools...${NC}"
    for pkg in "${DNF_PACKAGES[@]}"; do
        echo -n "  Installing $pkg... "
        if $SUDO dnf install -y "$pkg" &>/dev/null; then
            echo -e "${GREEN}OK${NC}"
        else
            echo -e "${YELLOW}SKIP${NC}"
        fi
    done
}

install_yum() {
    echo -e "\n${BOLD}Installing crisis tools...${NC}"
    for pkg in "${DNF_PACKAGES[@]}"; do
        echo -n "  Installing $pkg... "
        if $SUDO yum install -y "$pkg" &>/dev/null; then
            echo -e "${GREEN}OK${NC}"
        else
            echo -e "${YELLOW}SKIP${NC}"
        fi
    done
}

install_apk() {
    echo -e "\n${BOLD}Updating package list...${NC}"
    $SUDO apk update

    echo -e "\n${BOLD}Installing crisis tools...${NC}"
    for pkg in "${APK_PACKAGES[@]}"; do
        echo -n "  Installing $pkg... "
        if $SUDO apk add "$pkg" &>/dev/null; then
            echo -e "${GREEN}OK${NC}"
        else
            echo -e "${YELLOW}SKIP${NC}"
        fi
    done
}

# ============================================================================
# Main
# ============================================================================

case "$PKG_MANAGER" in
    apt)
        install_apt
        ;;
    dnf)
        install_dnf
        ;;
    yum)
        install_yum
        ;;
    apk)
        install_apk
        ;;
    *)
        echo -e "${RED}Unsupported package manager. Manual installation required.${NC}"
        echo ""
        echo "Required tools:"
        echo "  procps, sysstat, iproute2, tcpdump, ethtool, htop, iotop"
        echo "  strace, lsof, pciutils, smartmontools, perf, bcc-tools"
        exit 1
        ;;
esac

# ============================================================================
# Verification
# ============================================================================

echo ""
echo -e "${BOLD}Verifying installed tools...${NC}"

check_tool() {
    local tool=$1
    if command -v "$tool" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $tool"
    else
        echo -e "  ${RED}✗${NC} $tool (not found)"
    fi
}

echo ""
echo "Core tools:"
check_tool vmstat
check_tool iostat
check_tool mpstat
check_tool pidstat
check_tool sar
check_tool free
check_tool top
check_tool htop

echo ""
echo "Network tools:"
check_tool ip
check_tool ss
check_tool netstat
check_tool tcpdump
check_tool ethtool

echo ""
echo "Tracing tools:"
check_tool perf
check_tool strace
check_tool lsof

echo ""
echo "eBPF tools (may require root):"
check_tool bpftrace
if [[ -d /usr/share/bcc/tools ]]; then
    echo -e "  ${GREEN}✓${NC} BCC tools in /usr/share/bcc/tools/"
else
    echo -e "  ${YELLOW}?${NC} BCC tools (check /usr/share/bcc/tools/)"
fi

echo ""
echo "Hardware tools:"
check_tool lspci
check_tool lsusb
check_tool smartctl
check_tool dmidecode

echo ""
echo -e "${BOLD}${GREEN}Crisis tools installation complete!${NC}"
echo ""
echo "These tools are now available for performance diagnosis."
echo "Run 'quick-triage.sh' for a 60-second system overview."
echo "Run 'use-checklist.sh' for full USE Method analysis."
