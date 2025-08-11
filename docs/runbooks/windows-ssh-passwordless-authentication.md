# Windows SSH Passwordless Authentication Setup

## Overview

Configure SSH key-based authentication for Windows OpenSSH Server to enable passwordless SSH connections. This guide covers the specific requirements and common pitfalls when setting up SSH keys on Windows systems.

## Prerequisites

- Windows 10/11 or Windows Server 2019/2022
- OpenSSH Server installed and running
- Administrator privileges (for file permissions and service restart)
- SSH client access from source machine
- Basic understanding of SSH key concepts

## Understanding Windows SSH Key Locations

Windows SSH Server uses different authorized_keys file locations based on user privileges:

### Regular Users
- **File**: `%USERPROFILE%\.ssh\authorized_keys`
- **Example**: `C:\Users\username\.ssh\authorized_keys`

### Administrator Users
- **File**: `C:\ProgramData\ssh\administrators_authorized_keys`
- **Note**: If user is in Administrators group, only this file is checked

### Configuration Reference
Check your SSH config:
```powershell
Get-Content C:\ProgramData\ssh\sshd_config | Select-String -Pattern "AuthorizedKeysFile"
```

Typical output:
```
AuthorizedKeysFile .ssh/authorized_keys
Match Group administrators
       AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys
```

## Step-by-Step Setup

### Step 1: Generate SSH Key Pair (Client Side)

On your client machine (Linux/Mac/WSL):

```bash
# Generate ED25519 key (recommended)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_windows -C "username@windows-host"

# Or generate RSA key (if ED25519 not supported)
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa_windows -C "username@windows-host"

# Display public key for copying
cat ~/.ssh/id_ed25519_windows.pub
```

### Step 2: Create SSH Configuration (Client Side)

Add entry to `~/.ssh/config`:
```bash
Host windows-dev
    HostName 192.168.1.100
    User your-windows-username
    IdentityFile ~/.ssh/id_ed25519_windows
    PreferredAuthentications publickey
```

### Step 3: Backup Current Configuration (Windows Side)

Connect to Windows machine:
```bash
ssh username@windows-host
```

Create backups:
```powershell
# Backup SSH server configuration
Copy-Item C:\ProgramData\ssh\sshd_config "C:\ProgramData\ssh\sshd_config.backup.$(Get-Date -Format 'yyyyMMdd-HHmmss')"

# Backup existing authorized_keys if present
if (Test-Path "$env:USERPROFILE\.ssh\authorized_keys") {
    Copy-Item "$env:USERPROFILE\.ssh\authorized_keys" "$env:USERPROFILE\.ssh\authorized_keys.backup.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
}
```

### Step 4: Determine User Group Membership

Check if your user is in Administrators group:
```powershell
# Method 1: Check group membership
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
Write-Host "User is Administrator: $isAdmin"

# Method 2: Check local group members
net localgroup administrators | findstr /i "your-username"

# Method 3: PowerShell cmdlet
Get-LocalGroupMember -Group "Administrators" | Where-Object {$_.Name -like "*your-username*"}
```

### Step 5: Manual Setup (Recommended Approach)

#### For Regular Users (Non-Administrator)

**On Windows machine, open PowerShell as Administrator**:

```powershell
# Replace with your actual public key
$publicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIYourPublicKeyContentHere username@client-machine"

# Create .ssh directory
$sshDir = "C:\Users\your-username\.ssh"
New-Item -ItemType Directory -Path $sshDir -Force

# Create authorized_keys file with proper encoding
$authorizedKeysPath = "$sshDir\authorized_keys"
$publicKey | Out-File -FilePath $authorizedKeysPath -Encoding ASCII -NoNewline

# Set strict permissions on directory
icacls $sshDir /inheritance:r
icacls $sshDir /grant "your-username:(F)" /grant "SYSTEM:(F)" /grant "Administrators:(F)"

# Set strict permissions on authorized_keys file
icacls $authorizedKeysPath /inheritance:r
icacls $authorizedKeysPath /grant "your-username:(F)" /grant "SYSTEM:(F)" /grant "Administrators:(F)"
```

#### For Administrator Users

**On Windows machine, open PowerShell as Administrator**:

```powershell
# Replace with your actual public key
$publicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIYourPublicKeyContentHere username@client-machine"

# Create administrators_authorized_keys file
$adminKeysPath = "C:\ProgramData\ssh\administrators_authorized_keys"
$publicKey | Out-File -FilePath $adminKeysPath -Encoding ASCII -NoNewline

# Set permissions for administrators file
icacls $adminKeysPath /inheritance:r
icacls $adminKeysPath /grant "Administrators:(F)" /grant "SYSTEM:(F)"

# Also create user file as fallback
$userSshDir = "C:\Users\your-username\.ssh"
$userKeysPath = "$userSshDir\authorized_keys"
New-Item -ItemType Directory -Path $userSshDir -Force
$publicKey | Out-File -FilePath $userKeysPath -Encoding ASCII -NoNewline

# Set permissions on user files
icacls $userSshDir /inheritance:r
icacls $userSshDir /grant "your-username:(F)" /grant "SYSTEM:(F)" /grant "Administrators:(F)"
icacls $userKeysPath /inheritance:r
icacls $userKeysPath /grant "your-username:(F)" /grant "SYSTEM:(F)" /grant "Administrators:(F)"
```

### Step 6: Enable Public Key Authentication

Ensure SSH server configuration allows key authentication:

```powershell
# Check current configuration
Get-Content C:\ProgramData\ssh\sshd_config | Select-String -Pattern "PubkeyAuthentication"

# Enable if commented out or disabled
(Get-Content C:\ProgramData\ssh\sshd_config) -replace "^#?PubkeyAuthentication.*", "PubkeyAuthentication yes" | Set-Content C:\ProgramData\ssh\sshd_config
```

### Step 7: Restart SSH Service

```powershell
Restart-Service sshd
Start-Sleep 3

# Verify service is running
Get-Service sshd | Select-Object Name,Status
```

### Step 8: Test Passwordless Authentication

From client machine:
```bash
# Test with SSH config entry
ssh windows-dev 'Write-Host "Passwordless SSH successful!"; whoami'

# Test with direct connection
ssh -i ~/.ssh/id_ed25519_windows username@windows-host 'Get-Host | Select-Object Name'
```

## Automated Script Approach

### Pre-Setup Script (Before Setting PowerShell as Default)

Create `setup-windows-ssh-keys.ps1`:

```powershell
# setup-windows-ssh-keys.ps1
param(
    [Parameter(Mandatory=$true)]
    [string]$PublicKey,
    
    [Parameter(Mandatory=$true)]
    [string]$Username,
    
    [switch]$IsAdmin = $false,
    [switch]$Backup = $true,
    [switch]$Verify = $true
)

Write-Host "=== Windows SSH Key Setup ===" -ForegroundColor Green
Write-Host "User: $Username" -ForegroundColor Cyan
Write-Host "Admin Mode: $IsAdmin" -ForegroundColor Cyan

try {
    # Backup existing configuration
    if ($Backup) {
        Write-Host "Creating backups..." -ForegroundColor Yellow
        $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        
        Copy-Item "C:\ProgramData\ssh\sshd_config" "C:\ProgramData\ssh\sshd_config.backup.$timestamp"
        
        if (Test-Path "C:\Users\$Username\.ssh\authorized_keys") {
            Copy-Item "C:\Users\$Username\.ssh\authorized_keys" "C:\Users\$Username\.ssh\authorized_keys.backup.$timestamp"
        }
        
        Write-Host "Backups created with timestamp: $timestamp" -ForegroundColor Green
    }

    # Determine key file locations
    $userSshDir = "C:\Users\$Username\.ssh"
    $userKeysPath = "$userSshDir\authorized_keys"
    $adminKeysPath = "C:\ProgramData\ssh\administrators_authorized_keys"

    # Create user SSH directory
    Write-Host "Creating user SSH directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $userSshDir -Force | Out-Null

    # Write public key to user authorized_keys
    Write-Host "Creating user authorized_keys file..." -ForegroundColor Yellow
    $PublicKey | Out-File -FilePath $userKeysPath -Encoding ASCII -NoNewline

    # Set user file permissions
    Write-Host "Setting user file permissions..." -ForegroundColor Yellow
    icacls $userSshDir /inheritance:r | Out-Null
    icacls $userSshDir /grant "$Username:(F)" /grant "SYSTEM:(F)" /grant "Administrators:(F)" | Out-Null
    icacls $userKeysPath /inheritance:r | Out-Null
    icacls $userKeysPath /grant "$Username:(F)" /grant "SYSTEM:(F)" /grant "Administrators:(F)" | Out-Null

    # Handle administrator keys if needed
    if ($IsAdmin) {
        Write-Host "Creating administrator authorized_keys file..." -ForegroundColor Yellow
        $PublicKey | Out-File -FilePath $adminKeysPath -Encoding ASCII -NoNewline
        
        icacls $adminKeysPath /inheritance:r | Out-Null
        icacls $adminKeysPath /grant "Administrators:(F)" /grant "SYSTEM:(F)" | Out-Null
    }

    # Enable public key authentication
    Write-Host "Enabling public key authentication..." -ForegroundColor Yellow
    (Get-Content C:\ProgramData\ssh\sshd_config) -replace "^#?PubkeyAuthentication.*", "PubkeyAuthentication yes" | Set-Content C:\ProgramData\ssh\sshd_config

    # Restart SSH service
    Write-Host "Restarting SSH service..." -ForegroundColor Yellow
    Restart-Service sshd
    Start-Sleep 3

    # Verification
    if ($Verify) {
        Write-Host "Verifying setup..." -ForegroundColor Yellow
        
        # Check files
        $userFileExists = Test-Path $userKeysPath
        $adminFileExists = Test-Path $adminKeysPath
        
        Write-Host "User authorized_keys exists: $userFileExists" -ForegroundColor Cyan
        Write-Host "Admin authorized_keys exists: $adminFileExists" -ForegroundColor Cyan
        
        if ($userFileExists) {
            $content = Get-Content $userKeysPath -Raw
            Write-Host "User file content length: $($content.Length) characters" -ForegroundColor Cyan
        }
        
        # Check SSH service
        $sshService = Get-Service sshd
        Write-Host "SSH Service Status: $($sshService.Status)" -ForegroundColor Cyan
        
        # Check public key authentication setting
        $pubkeyAuth = Get-Content C:\ProgramData\ssh\sshd_config | Select-String "^PubkeyAuthentication"
        Write-Host "PubkeyAuthentication setting: $pubkeyAuth" -ForegroundColor Cyan
    }

    Write-Host "✅ SUCCESS: SSH key setup completed!" -ForegroundColor Green
    Write-Host "Test with: ssh -i ~/.ssh/your-key $Username@$env:COMPUTERNAME" -ForegroundColor Cyan

} catch {
    Write-Host "❌ ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
```

### Usage Examples

```powershell
# For regular user
powershell -ExecutionPolicy Bypass -File setup-windows-ssh-keys.ps1 -PublicKey "ssh-ed25519 AAAA..." -Username "john"

# For administrator user
powershell -ExecutionPolicy Bypass -File setup-windows-ssh-keys.ps1 -PublicKey "ssh-ed25519 AAAA..." -Username "admin" -IsAdmin

# Without backup
powershell -ExecutionPolicy Bypass -File setup-windows-ssh-keys.ps1 -PublicKey "ssh-ed25519 AAAA..." -Username "john" -Backup:$false
```

## Troubleshooting

### Issue: Permission Denied (publickey)

**Symptoms**:
```
user@host: Permission denied (publickey,password,keyboard-interactive).
```

**Debug Steps**:

1. **Enable SSH debug logging**:
   ```powershell
   # Edit SSH config to enable debug logging
   (Get-Content C:\ProgramData\ssh\sshd_config) -replace "^#?LogLevel.*", "LogLevel DEBUG" | Set-Content C:\ProgramData\ssh\sshd_config
   Restart-Service sshd
   ```

2. **Check SSH client verbose output**:
   ```bash
   ssh -v username@windows-host 'echo test'
   # Look for: "Offering public key" and "Authentications that can continue"
   ```

3. **Verify key file permissions**:
   ```powershell
   icacls "C:\Users\username\.ssh\authorized_keys"
   icacls "C:\ProgramData\ssh\administrators_authorized_keys"
   ```

4. **Check key file content**:
   ```powershell
   Get-Content "C:\Users\username\.ssh\authorized_keys" -Raw | Format-Hex
   # Should show ASCII encoding, no BOM, single line
   ```

**Common Solutions**:

1. **Fix file encoding**:
   ```powershell
   $key = Get-Content "path\to\authorized_keys" -Raw
   $key.Trim() | Out-File -FilePath "path\to\authorized_keys" -Encoding ASCII -NoNewline
   ```

2. **Reset permissions**:
   ```powershell
   $path = "C:\Users\username\.ssh\authorized_keys"
   icacls $path /inheritance:r
   icacls $path /grant "username:(F)" /grant "SYSTEM:(F)" /grant "Administrators:(F)"
   ```

3. **Check SSH configuration**:
   ```powershell
   Get-Content C:\ProgramData\ssh\sshd_config | Select-String -Pattern "PubkeyAuthentication|AuthorizedKeysFile"
   ```

### Issue: File Transfer (SCP) Problems

**Symptoms**:
- `scp: Received message too long`
- File transfers fail after setting up keys

**Root Cause**: PowerShell default shell interferes with SCP protocol

**Solutions**:

1. **Use SFTP instead**:
   ```bash
   sftp username@windows-host
   ```

2. **Use PowerShell remoting**:
   ```bash
   ssh username@windows-host 'Copy-Item source destination'
   ```

3. **Temporarily disable PowerShell default**:
   ```powershell
   Remove-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -ErrorAction SilentlyContinue
   Restart-Service sshd
   # Perform file transfers
   # Restore PowerShell default later
   ```

### Issue: Keys Work But PowerShell Commands Fail

**Symptoms**:
- SSH connection succeeds
- PowerShell commands return no output
- Only see prompt: `PS C:\Users\username>`

**Solutions**:

1. **Use explicit output**:
   ```bash
   ssh windows-host 'Write-Output "test"; Write-Host "visible"'
   ```

2. **Redirect streams**:
   ```bash
   ssh windows-host 'command *>&1'
   ```

3. **Use -t for interactive**:
   ```bash
   ssh -t windows-host 'command'
   ```

## Advanced Configuration

### Multiple Key Types

Support both ED25519 and RSA keys:
```powershell
$ed25519Key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample user@host"
$rsaKey = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDExample user@host"

$bothKeys = @($ed25519Key, $rsaKey) -join "`n"
$bothKeys | Out-File -FilePath $authorizedKeysPath -Encoding ASCII -NoNewline
```

### Key Restrictions

Add restrictions to keys:
```powershell
$restrictedKey = 'command="powershell -Command Get-Process",no-port-forwarding ssh-ed25519 AAAAC3... user@host'
$restrictedKey | Out-File -FilePath $authorizedKeysPath -Encoding ASCII -NoNewline
```

### Certificate Authentication

For advanced setups using SSH certificates:
```powershell
# Enable certificate authentication
(Get-Content C:\ProgramData\ssh\sshd_config) -replace "^#?PubkeyAuthentication.*", "PubkeyAuthentication yes" | Set-Content C:\ProgramData\ssh\sshd_config
Add-Content C:\ProgramData\ssh\sshd_config "PubkeyAcceptedKeyTypes +ssh-rsa-cert-v01@openssh.com,ssh-ed25519-cert-v01@openssh.com"
```

## Rollback Procedures

### Remove SSH Keys

```powershell
# Remove user authorized_keys
Remove-Item "C:\Users\username\.ssh\authorized_keys" -ErrorAction SilentlyContinue

# Remove administrator authorized_keys  
Remove-Item "C:\ProgramData\ssh\administrators_authorized_keys" -ErrorAction SilentlyContinue

# Restart SSH service
Restart-Service sshd
```

### Restore from Backup

```powershell
# List available backups
Get-ChildItem C:\ProgramData\ssh\sshd_config.backup.*
Get-ChildItem C:\Users\username\.ssh\authorized_keys.backup.*

# Restore SSH configuration
Copy-Item "C:\ProgramData\ssh\sshd_config.backup.20241108-143022" "C:\ProgramData\ssh\sshd_config" -Force

# Restore authorized_keys
Copy-Item "C:\Users\username\.ssh\authorized_keys.backup.20241108-143022" "C:\Users\username\.ssh\authorized_keys" -Force

# Restart SSH service
Restart-Service sshd
```

### Disable Public Key Authentication

```powershell
# Disable public key authentication
(Get-Content C:\ProgramData\ssh\sshd_config) -replace "^PubkeyAuthentication.*", "PubkeyAuthentication no" | Set-Content C:\ProgramData\ssh\sshd_config

# Restart SSH service
Restart-Service sshd
```

## Security Best Practices

### 1. Key Management
- Use strong key types (ED25519 preferred, RSA 4096-bit minimum)
- Regularly rotate SSH keys
- Use different keys for different purposes
- Protect private keys with passphrases

### 2. File Permissions
- Always use strict NTFS permissions on key files
- Remove inheritance to prevent permission escalation
- Audit key file access regularly

### 3. SSH Configuration
- Disable password authentication after key setup:
  ```powershell
  (Get-Content C:\ProgramData\ssh\sshd_config) -replace "^#?PasswordAuthentication.*", "PasswordAuthentication no" | Set-Content C:\ProgramData\ssh\sshd_config
  ```
- Enable key-only authentication:
  ```powershell
  Add-Content C:\ProgramData\ssh\sshd_config "AuthenticationMethods publickey"
  ```

### 4. Monitoring
- Monitor SSH authentication logs
- Set up alerts for failed authentication attempts
- Regular audit of authorized_keys files

## Integration with PowerShell Default Shell

When combining with PowerShell default shell configuration:

### Recommended Setup Order
1. ✅ Set up SSH keys first (this guide)
2. ✅ Configure PowerShell as default shell
3. ✅ Test both functionalities together

### Testing Both Features
```bash
# Test passwordless authentication with PowerShell
ssh windows-dev 'Get-Host | Select-Object Name,Version; $PSVersionTable.PSVersion'

# Should show:
# - No password prompt (passwordless working)
# - PowerShell host information (PowerShell default working)
# - PowerShell version (PowerShell default working)
```

## Related Documentation

- [Windows SSH PowerShell Default Shell](./windows-ssh-powershell-default-shell.md) - See [Issue #132](https://github.com/homeiac/home/issues/132)
- [Windows SSH Security Hardening](./windows-ssh-security-hardening.md)
- [SSH Client Configuration](./ssh-client-configuration.md)

## GitHub Issue

This runbook addresses [Issue #133: Add Windows SSH Passwordless Authentication Runbook](https://github.com/homeiac/home/issues/133)

## Support Information

### Diagnostic Commands
```powershell
# SSH service status
Get-Service sshd | Select-Object Name,Status,StartType

# Check SSH configuration
Get-Content C:\ProgramData\ssh\sshd_config | Select-String -Pattern "Pubkey|Authorized"

# Check key files
Get-ChildItem "C:\Users\$env:USERNAME\.ssh\" -ErrorAction SilentlyContinue
Get-ChildItem "C:\ProgramData\ssh\*authorized*" -ErrorAction SilentlyContinue

# Check file permissions
icacls "C:\Users\$env:USERNAME\.ssh\authorized_keys"
icacls "C:\ProgramData\ssh\administrators_authorized_keys"

# Check SSH logs
Get-WinEvent -LogName "OpenSSH/Operational" -MaxEvents 10
```

### Client-side Diagnostics
```bash
# Test key authentication
ssh -o PreferredAuthentications=publickey -v username@windows-host 'echo test'

# Check SSH config
ssh -T windows-dev

# Verify key fingerprint
ssh-keygen -lf ~/.ssh/id_ed25519_windows.pub
```

---

**Last Updated**: November 2024  
**Version**: 1.0  
**Tested On**: Windows 10/11, Windows Server 2019/2022  
**Compatible SSH Clients**: OpenSSH 7.0+, PuTTY, WinSCP