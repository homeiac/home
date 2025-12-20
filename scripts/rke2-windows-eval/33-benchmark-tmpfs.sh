#!/bin/bash
# Run disk I/O benchmark on tmpfs-backed VM 203
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
WINDOWS_PASSWORD="${WINDOWS_PASSWORD}"
# VM 203 will have same Windows config as 201, including IP
# We need to ensure VM 201 is stopped or use a different approach
WINDOWS_VM_IP="${WINDOWS_VM_IP:-192.168.4.201}"

if [[ -z "$WINDOWS_PASSWORD" ]]; then
    echo "ERROR: WINDOWS_PASSWORD not set in .env"
    exit 1
fi

echo "=== tmpfs VM Disk I/O Benchmark ==="
echo ""

# Check VM 203 is running
if ! ssh root@${PROXMOX_HOST} "qm status 203 | grep -q running"; then
    echo "ERROR: VM 203 is not running"
    echo "Run ./32-create-tmpfs-vm.sh first"
    exit 1
fi

# Check VM 201 is stopped (to avoid IP conflict)
if ssh root@${PROXMOX_HOST} "qm status 201 2>/dev/null | grep -q running"; then
    echo "WARNING: VM 201 is still running with same IP (192.168.4.201)"
    echo "This may cause network conflicts."
    read -p "Stop VM 201? (Y/n): " CONFIRM
    if [[ "$CONFIRM" != "n" && "$CONFIRM" != "N" ]]; then
        echo "Stopping VM 201..."
        ssh root@${PROXMOX_HOST} "qm stop 201"
        sleep 10
    fi
fi

# Wait for Windows to be accessible
echo "Waiting for Windows VM to be accessible..."
for i in {1..60}; do
    if sshpass -p "${WINDOWS_PASSWORD}" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 Administrator@${WINDOWS_VM_IP} "hostname" 2>/dev/null; then
        echo "Windows VM is accessible!"
        break
    fi
    echo "  Attempt $i/60..."
    sleep 5
done

# Run benchmark
echo ""
echo "Running disk I/O benchmark..."
echo ""

sshpass -p "${WINDOWS_PASSWORD}" ssh -o StrictHostKeyChecking=no Administrator@${WINDOWS_VM_IP} 'powershell -Command "
Write-Host \"=== Windows Disk I/O Benchmark (tmpfs-backed) ===\"
Write-Host \"\"

$testDir = \"C:\benchmark\"
New-Item -ItemType Directory -Force -Path $testDir | Out-Null

# Test 1: Sequential write (1GB file)
Write-Host \"--- Test 1: Sequential Write (1GB) ---\"
$sw = [Diagnostics.Stopwatch]::StartNew()
$data = New-Object byte[] (1024*1024)
$fs = [System.IO.File]::Create(\"$testDir\seqwrite.bin\")
for ($i = 0; $i -lt 1024; $i++) {
    $fs.Write($data, 0, $data.Length)
}
$fs.Close()
$sw.Stop()
$seqWriteMBps = [math]::Round(1024 / $sw.Elapsed.TotalSeconds, 2)
Write-Host \"Sequential Write: $seqWriteMBps MB/s\"
Write-Host \"\"

# Test 2: Sequential read
Write-Host \"--- Test 2: Sequential Read (1GB) ---\"
$sw = [Diagnostics.Stopwatch]::StartNew()
$fs = [System.IO.File]::OpenRead(\"$testDir\seqwrite.bin\")
$buffer = New-Object byte[] (1024*1024)
while ($fs.Read($buffer, 0, $buffer.Length) -gt 0) {}
$fs.Close()
$sw.Stop()
$seqReadMBps = [math]::Round(1024 / $sw.Elapsed.TotalSeconds, 2)
Write-Host \"Sequential Read: $seqReadMBps MB/s\"
Write-Host \"\"

# Test 3: Small file creation
Write-Host \"--- Test 3: Small File Creation (1000 x 4KB files) ---\"
$smallDir = \"$testDir\smallfiles\"
New-Item -ItemType Directory -Force -Path $smallDir | Out-Null
$smallData = New-Object byte[] 4096
$sw = [Diagnostics.Stopwatch]::StartNew()
for ($i = 0; $i -lt 1000; $i++) {
    [System.IO.File]::WriteAllBytes(\"$smallDir\file$i.dat\", $smallData)
}
$sw.Stop()
$filesPerSec = [math]::Round(1000 / $sw.Elapsed.TotalSeconds, 2)
Write-Host \"Small File Creation: $filesPerSec files/sec\"
Write-Host \"\"

# Test 4: Random I/O
Write-Host \"--- Test 4: Random 4KB Reads (1000 ops) ---\"
$fs = [System.IO.File]::OpenRead(\"$testDir\seqwrite.bin\")
$rand = New-Object System.Random
$buffer = New-Object byte[] 4096
$sw = [Diagnostics.Stopwatch]::StartNew()
for ($i = 0; $i -lt 1000; $i++) {
    $pos = $rand.Next(0, 1024*1024*1024 - 4096)
    $fs.Seek($pos, [System.IO.SeekOrigin]::Begin) | Out-Null
    $fs.Read($buffer, 0, 4096) | Out-Null
}
$fs.Close()
$sw.Stop()
$iops = [math]::Round(1000 / $sw.Elapsed.TotalSeconds, 2)
Write-Host \"Random 4KB Read IOPS: $iops\"
Write-Host \"\"

# Cleanup
Remove-Item -Recurse -Force $testDir

Write-Host \"=== Benchmark Complete (tmpfs) ===\"
Write-Host \"\"
Write-Host \"Summary:\"
Write-Host \"  Sequential Write: $seqWriteMBps MB/s\"
Write-Host \"  Sequential Read:  $seqReadMBps MB/s\"
Write-Host \"  Small File Ops:   $filesPerSec files/sec\"
Write-Host \"  Random 4KB IOPS:  $iops\"
"'

echo ""
echo "=== Comparison ==="
echo ""
echo "Baseline (ZFS-backed VM 201):"
echo "  Sequential Write: 2466.47 MB/s"
echo "  Sequential Read:  4137.98 MB/s"
echo "  Small File Ops:   899.74 files/sec"
echo "  Random 4KB IOPS:  12119.33"
echo ""
echo "See tmpfs results above for comparison."
