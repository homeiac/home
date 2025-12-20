# PowerShell script to prepare Windows Server 2022 for RKE2
# Run this ON the Windows VM after installation

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

Write-Host "=== Preparing Windows Server for RKE2 ===" -ForegroundColor Cyan
Write-Host ""

# 1. Install Windows Containers feature
Write-Host "[1/6] Installing Windows Containers feature..." -ForegroundColor Yellow
Install-WindowsFeature -Name Containers -IncludeAllSubFeature
Write-Host "  Containers feature installed" -ForegroundColor Green

# 2. Disable Windows Defender real-time protection (for build performance)
Write-Host ""
Write-Host "[2/6] Disabling Windows Defender real-time protection..." -ForegroundColor Yellow
Write-Host "  (Improves build I/O performance significantly)" -ForegroundColor Gray
Set-MpPreference -DisableRealtimeMonitoring $true
Add-MpPreference -ExclusionPath "C:\var"
Add-MpPreference -ExclusionPath "C:\etc"
Add-MpPreference -ExclusionPath "C:\run"
Write-Host "  Defender real-time monitoring disabled" -ForegroundColor Green

# 3. Configure Windows Firewall
Write-Host ""
Write-Host "[3/6] Configuring Windows Firewall for RKE2..." -ForegroundColor Yellow
# RKE2 ports
New-NetFirewallRule -DisplayName "RKE2 API Server" -Direction Inbound -LocalPort 6443 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "RKE2 Supervisor" -Direction Inbound -LocalPort 9345 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "Kubelet" -Direction Inbound -LocalPort 10250 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "Flannel VXLAN" -Direction Inbound -LocalPort 8472 -Protocol UDP -Action Allow -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "NodePort Services" -Direction Inbound -LocalPort 30000-32767 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue
Write-Host "  Firewall rules added" -ForegroundColor Green

# 4. Create required directories
Write-Host ""
Write-Host "[4/6] Creating RKE2 directories..." -ForegroundColor Yellow
$dirs = @("C:\var\lib\rancher\rke2", "C:\etc\rancher\rke2", "C:\var\log\pods")
foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  Created: $dir" -ForegroundColor Gray
    }
}
Write-Host "  Directories created" -ForegroundColor Green

# 5. Install containerd
Write-Host ""
Write-Host "[5/6] Installing containerd..." -ForegroundColor Yellow

# Download containerd
$containerdVersion = "1.7.24"
$containerdUrl = "https://github.com/containerd/containerd/releases/download/v$containerdVersion/containerd-$containerdVersion-windows-amd64.tar.gz"
$downloadPath = "$env:TEMP\containerd.tar.gz"

Write-Host "  Downloading containerd $containerdVersion..." -ForegroundColor Gray
Invoke-WebRequest -Uri $containerdUrl -OutFile $downloadPath

# Extract (requires tar, available in Windows Server 2022)
Write-Host "  Extracting..." -ForegroundColor Gray
$containerdPath = "C:\Program Files\containerd"
if (!(Test-Path $containerdPath)) {
    New-Item -ItemType Directory -Path $containerdPath -Force | Out-Null
}
tar -xzf $downloadPath -C $containerdPath

# Add to PATH
$envPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($envPath -notlike "*containerd*") {
    [Environment]::SetEnvironmentVariable("Path", "$envPath;$containerdPath\bin", "Machine")
}

# Configure containerd
$containerdConfig = @"
version = 2
root = "C:\\ProgramData\\containerd\\root"
state = "C:\\ProgramData\\containerd\\state"

[grpc]
  address = "\\\\.\\pipe\\containerd-containerd"

[plugins."io.containerd.grpc.v1.cri"]
  sandbox_image = "mcr.microsoft.com/oss/kubernetes/pause:3.9"
"@
$containerdConfig | Out-File -FilePath "$containerdPath\config.toml" -Encoding ASCII

# Register as service
Write-Host "  Registering containerd service..." -ForegroundColor Gray
& "$containerdPath\bin\containerd.exe" --register-service
Start-Service containerd
Write-Host "  containerd installed and running" -ForegroundColor Green

# 6. Display next steps
Write-Host ""
Write-Host "[6/6] Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "=== Next Steps ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. A reboot is recommended:" -ForegroundColor Yellow
Write-Host "   Restart-Computer"
Write-Host ""
Write-Host "2. After reboot, get the RKE2 join command from Rancher UI:" -ForegroundColor Yellow
Write-Host "   - Open https://rancher.homelab"
Write-Host "   - Go to your cluster -> Registration -> Windows"
Write-Host "   - Copy the PowerShell command"
Write-Host ""
Write-Host "3. Run the join command on this Windows node" -ForegroundColor Yellow
Write-Host ""
Write-Host "4. Verify in Rancher UI that the Windows node shows as Ready" -ForegroundColor Yellow
Write-Host ""

# Prompt for reboot
$reboot = Read-Host "Reboot now? (y/n)"
if ($reboot -eq "y") {
    Restart-Computer
}
