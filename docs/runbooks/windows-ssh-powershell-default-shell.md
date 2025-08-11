# Windows SSH PowerShell Default Shell Configuration

## Overview

Configure OpenSSH for Windows to use PowerShell as the default shell instead of cmd.exe. This provides a more powerful shell environment for SSH connections while maintaining compatibility with Windows administration tasks.

## Prerequisites

- Windows 10/11 or Windows Server 2019/2022
- OpenSSH Server installed and running
- Administrator privileges on the Windows machine
- SSH access to the Windows machine (password or existing key-based)

## Verification of Current State

Before making changes, verify the current SSH shell:

### From Client Machine
```bash
ssh user@windows-host 'echo $0'
# If you see: C:\Windows\system32\cmd.exe - current shell is cmd
```

### Check Environment Variable
```bash
ssh user@windows-host 'echo %COMSPEC%'
# Should show: C:\Windows\system32\cmd.exe
```

## Method 1: Registry Configuration (Recommended)

### Step 1: Backup Current Configuration

Connect to Windows machine and create backup:

```bash
ssh user@windows-host
```

In PowerShell session:
```powershell
# Create backup of SSH config
Copy-Item C:\ProgramData\ssh\sshd_config "C:\ProgramData\ssh\sshd_config.backup.$(Get-Date -Format 'yyyyMMdd-HHmmss')"

# Backup registry (optional)
reg export "HKLM\SOFTWARE\OpenSSH" "C:\temp\openssh-backup.reg"
```

### Step 2: Set PowerShell as Default Shell

```powershell
# Set PowerShell as default SSH shell
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force

# Verify the setting
Get-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell
```

### Step 3: Restart SSH Service

```powershell
Restart-Service sshd
```

### Step 4: Verify Configuration

From client machine:
```bash
ssh user@windows-host 'Get-Host | Select-Object Name,Version'
# Should show PowerShell host information

ssh user@windows-host '$PSVersionTable.PSVersion'
# Should show PowerShell version
```

## Method 2: SSH Config File (Alternative)

⚠️ **Note**: This method can interfere with SSH key authentication. Use Method 1 instead.

### Add ForceCommand to sshd_config

```powershell
# Add ForceCommand to SSH config (NOT RECOMMENDED)
$config = Get-Content C:\ProgramData\ssh\sshd_config
$config += "`nForceCommand powershell.exe -NoLogo"
$config | Set-Content C:\ProgramData\ssh\sshd_config

# Restart service
Restart-Service sshd
```

## Verification Steps

### Test PowerShell Functionality
```bash
# Test PowerShell cmdlets
ssh user@windows-host 'Get-Process | Select-Object -First 5'

# Test PowerShell variables
ssh user@windows-host '$env:USERNAME; $env:COMPUTERNAME'

# Test PowerShell objects
ssh user@windows-host 'Get-Service | Where-Object {$_.Status -eq "Running"} | Select-Object Name | Select-Object -First 3'
```

### Verify Prompt Format
```bash
ssh user@windows-host
# Prompt should show: PS C:\Users\username>
# Instead of: C:\Users\username>
```

## Automated Script Approach

Create a PowerShell script for automated deployment:

```powershell
# powershell-default-shell-setup.ps1
param(
    [switch]$Backup = $true,
    [switch]$Verify = $true
)

Write-Host "=== Windows SSH PowerShell Default Shell Setup ===" -ForegroundColor Green

try {
    # Backup current configuration
    if ($Backup) {
        Write-Host "Creating backup..." -ForegroundColor Yellow
        $backupName = "sshd_config.backup.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Copy-Item "C:\ProgramData\ssh\sshd_config" "C:\ProgramData\ssh\$backupName"
        Write-Host "Backup created: $backupName" -ForegroundColor Green
    }

    # Set PowerShell as default shell
    Write-Host "Setting PowerShell as default SSH shell..." -ForegroundColor Yellow
    New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force | Out-Null
    
    # Restart SSH service
    Write-Host "Restarting SSH service..." -ForegroundColor Yellow
    Restart-Service sshd
    Start-Sleep 3
    
    # Verification
    if ($Verify) {
        Write-Host "Verifying configuration..." -ForegroundColor Yellow
        $shellSetting = Get-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -ErrorAction SilentlyContinue
        if ($shellSetting.DefaultShell -like "*powershell*") {
            Write-Host "✅ SUCCESS: PowerShell set as default SSH shell" -ForegroundColor Green
            Write-Host "Registry setting: $($shellSetting.DefaultShell)" -ForegroundColor Cyan
        } else {
            Write-Host "❌ FAILED: PowerShell not set as default" -ForegroundColor Red
        }
        
        # Check SSH service status
        $sshService = Get-Service sshd
        Write-Host "SSH Service Status: $($sshService.Status)" -ForegroundColor Cyan
    }
    
} catch {
    Write-Host "❌ ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host "Test with: ssh user@this-machine 'Get-Host'" -ForegroundColor Cyan
```

Execute the script:
```powershell
# Run with all options
powershell -ExecutionPolicy Bypass -File powershell-default-shell-setup.ps1

# Run without backup
powershell -ExecutionPolicy Bypass -File powershell-default-shell-setup.ps1 -Backup:$false
```

## Troubleshooting

### Issue: SSH Connection Fails After Configuration

**Symptoms**:
- SSH connections hang or fail
- "Connection refused" errors

**Solutions**:
1. Check SSH service status:
   ```powershell
   Get-Service sshd
   Restart-Service sshd
   ```

2. Verify PowerShell path:
   ```powershell
   Test-Path "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
   ```

3. Check Windows Event Logs:
   ```powershell
   Get-WinEvent -LogName "OpenSSH/Operational" -MaxEvents 10
   ```

### Issue: SCP/SFTP Transfers Fail

**Symptoms**:
- `scp: Received message too long`
- File transfers fail with protocol errors

**Root Cause**: PowerShell startup messages interfere with SCP protocol

**Solutions**:
1. **Use SFTP instead of SCP**:
   ```bash
   sftp user@windows-host
   sftp> put localfile.txt
   ```

2. **Use PowerShell remoting for file transfers**:
   ```bash
   ssh user@windows-host 'Invoke-WebRequest -Uri "http://source/file" -OutFile "C:\dest\file"'
   ```

3. **Temporarily disable PowerShell default for large transfers**:
   ```powershell
   # Temporarily remove PowerShell default
   Remove-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell
   Restart-Service sshd
   
   # Perform file transfers
   
   # Restore PowerShell default
   New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force
   Restart-Service sshd
   ```

### Issue: Command Output Not Visible

**Symptoms**:
- Commands execute but no output shown
- Only see PowerShell prompt

**Solutions**:
1. **Use explicit output commands**:
   ```bash
   ssh user@windows-host 'Write-Host "Output"; Write-Output "Data"'
   ```

2. **Redirect all streams**:
   ```bash
   ssh user@windows-host 'command 2>&1'
   ```

3. **Use -t flag for interactive sessions**:
   ```bash
   ssh -t user@windows-host 'command'
   ```

## Rollback Procedures

### Method 1: Remove Registry Setting

```powershell
# Remove PowerShell default shell setting
Remove-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -ErrorAction SilentlyContinue

# Restart SSH service
Restart-Service sshd
```

### Method 2: Restore from Backup

```powershell
# List available backups
Get-ChildItem C:\ProgramData\ssh\sshd_config.backup.*

# Restore specific backup
Copy-Item "C:\ProgramData\ssh\sshd_config.backup.20241108-143022" "C:\ProgramData\ssh\sshd_config" -Force

# Restart SSH service
Restart-Service sshd
```

### Method 3: Reset to CMD Default

```powershell
# Explicitly set CMD as default (optional)
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\cmd.exe" -PropertyType String -Force

# Restart SSH service
Restart-Service sshd
```

## Best Practices

### 1. Always Create Backups
- Backup SSH configuration before changes
- Test changes in non-production environment first

### 2. Use PowerShell 7 (Optional)
For modern PowerShell features:
```powershell
# Set PowerShell 7 as default (if installed)
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Program Files\PowerShell\7\pwsh.exe" -PropertyType String -Force
```

### 3. Security Considerations
- PowerShell provides more capabilities - ensure proper user permissions
- Consider PowerShell execution policy settings
- Monitor SSH access logs more carefully

### 4. Monitoring
Set up monitoring for SSH service status:
```powershell
# Create simple health check script
$service = Get-Service sshd
if ($service.Status -ne 'Running') {
    Write-Warning "SSH service is not running"
    # Add alerting logic here
}
```

## Related Documentation

- [Windows SSH Passwordless Authentication](./windows-ssh-passwordless-authentication.md) - See [Issue #133](https://github.com/homeiac/home/issues/133)
- [Windows SSH Security Hardening](./windows-ssh-security-hardening.md)
- [PowerShell Remoting Configuration](./powershell-remoting-setup.md)

## GitHub Issue

This runbook addresses [Issue #132: Add Windows SSH PowerShell Default Shell Runbook](https://github.com/homeiac/home/issues/132)

## Support

### Common Commands for Support
```powershell
# Check SSH service
Get-Service sshd | Select-Object Name,Status,StartType

# Check SSH configuration
Get-Content C:\ProgramData\ssh\sshd_config | Select-String -Pattern "DefaultShell|ForceCommand"

# Check registry setting
Get-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -ErrorAction SilentlyContinue

# Check SSH logs
Get-WinEvent -LogName "OpenSSH/Operational" -MaxEvents 5
```

### GitHub Issue Template
When reporting issues, include:
- Windows version and build
- PowerShell version (`$PSVersionTable`)
- SSH client version
- Error messages from Event Viewer
- Output from support commands above

---

**Last Updated**: November 2024  
**Version**: 1.0  
**Tested On**: Windows 10/11, Windows Server 2019/2022