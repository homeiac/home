# Windows SSH Configuration Runbooks

This directory contains comprehensive runbooks for configuring SSH on Windows systems with advanced features.

## Available Runbooks

### 🐚 [Windows SSH PowerShell Default Shell](./windows-ssh-powershell-default-shell.md)
Configure OpenSSH for Windows to use PowerShell as the default shell instead of cmd.exe.

**Use this runbook when you want to:**
- Get a PowerShell environment by default when SSHing to Windows
- Use PowerShell cmdlets and objects in SSH sessions
- Modernize your Windows SSH experience

**Key Features:**
- Registry-based configuration (recommended method)
- Automated PowerShell script for bulk deployment
- Comprehensive troubleshooting for SCP/file transfer issues
- Complete rollback procedures

### 🔑 [Windows SSH Passwordless Authentication](./windows-ssh-passwordless-authentication.md)
Set up SSH key-based authentication for Windows systems with proper file permissions and encoding.

**Use this runbook when you want to:**
- Enable passwordless SSH connections to Windows
- Properly configure authorized_keys files with correct permissions
- Handle both regular users and administrator accounts
- Avoid common Windows SSH key authentication pitfalls

**Key Features:**
- Detailed explanation of Windows SSH key file locations
- Manual setup procedures (guaranteed to work)
- Automated PowerShell script for enterprise deployment
- Advanced troubleshooting for permission issues

## Combined Setup Guide

For the ultimate Windows SSH experience, use both runbooks together:

### Recommended Setup Order

1. **First**: [Passwordless Authentication](./windows-ssh-passwordless-authentication.md)
   - Set up SSH keys while cmd is still the default shell
   - Avoid file transfer issues during key setup
   - Verify key authentication works

2. **Second**: [PowerShell Default Shell](./windows-ssh-powershell-default-shell.md)
   - Configure PowerShell as default after keys are working
   - Enjoy passwordless PowerShell SSH sessions

### Quick Combined Test
```bash
# This should work without password prompt and show PowerShell info
ssh your-windows-host 'Get-Host | Select-Object Name,Version; whoami'
```

Expected output:
```
Name           Version
----           -------
ConsoleHost    5.1.19041.xxxx

your-domain\your-username
```

## Common Issues and Solutions

### Issue: Can't Transfer Files After Setup
**Problem**: SCP fails with "message too long" error after setting PowerShell as default shell.

**Solution**: Use SFTP or temporarily disable PowerShell default:
```bash
# Use SFTP instead of SCP
sftp your-windows-host
sftp> put localfile.txt

# Or temporarily disable PowerShell default for transfers
ssh your-windows-host 'Remove-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell; Restart-Service sshd'
# Do file transfers
ssh your-windows-host 'Set-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "powershell.exe"; Restart-Service sshd'
```

### Issue: Commands Execute But No Output Visible
**Problem**: SSH commands run but output is not displayed.

**Solution**: Use explicit output commands:
```bash
ssh your-windows-host 'Write-Host "This will be visible"; Write-Output "This too"'
```

### Issue: Permission Denied After Key Setup
**Problem**: SSH keys are rejected even after proper setup.

**Solution**: Check user group membership and use correct authorized_keys file location:
```bash
# For administrator users, keys must be in:
# C:\ProgramData\ssh\administrators_authorized_keys

# For regular users, keys go in:
# C:\Users\username\.ssh\authorized_keys
```

## Enterprise Deployment

### Automated Script Deployment

Both runbooks include PowerShell scripts for automated deployment:

```powershell
# Deploy SSH keys
powershell -ExecutionPolicy Bypass -File setup-windows-ssh-keys.ps1 -PublicKey "ssh-ed25519 AAA..." -Username "admin" -IsAdmin

# Configure PowerShell default shell
powershell -ExecutionPolicy Bypass -File powershell-default-shell-setup.ps1
```

### Group Policy Integration

Consider these Group Policy settings for enterprise environments:

1. **SSH Service Management**:
   - Ensure OpenSSH Server is installed and running
   - Configure automatic startup

2. **Security Settings**:
   - Disable password authentication after key deployment
   - Configure SSH port and firewall rules

3. **PowerShell Execution Policy**:
   - Allow PowerShell script execution for setup scripts
   - Configure appropriate execution policy for SSH sessions

## Security Considerations

### Best Practices
- ✅ Use ED25519 keys (preferred) or RSA 4096-bit minimum
- ✅ Protect private keys with passphrases
- ✅ Regular key rotation
- ✅ Monitor SSH access logs
- ✅ Use different keys for different environments

### Hardening Options
```powershell
# Disable password authentication after key setup
(Get-Content C:\ProgramData\ssh\sshd_config) -replace "^#?PasswordAuthentication.*", "PasswordAuthentication no" | Set-Content C:\ProgramData\ssh\sshd_config

# Restrict authentication methods
Add-Content C:\ProgramData\ssh\sshd_config "AuthenticationMethods publickey"

# Restart SSH service
Restart-Service sshd
```

## Monitoring and Maintenance

### Health Checks
```powershell
# SSH service status
Get-Service sshd | Select-Object Name,Status,StartType

# Check active SSH sessions
Get-Process | Where-Object {$_.Name -eq "sshd" -and $_.Id -ne (Get-WmiObject Win32_Service | Where-Object {$_.Name -eq "sshd"}).ProcessId}

# Review SSH logs
Get-WinEvent -LogName "OpenSSH/Operational" -MaxEvents 20
```

### Regular Maintenance Tasks
- Audit authorized_keys files quarterly
- Review SSH access logs monthly
- Update SSH keys annually
- Test backup and rollback procedures

## Support and Contributing

### Getting Help
If you encounter issues:
1. Check the troubleshooting section in the relevant runbook
2. Run the diagnostic commands provided
3. Create a GitHub issue with the diagnostic output

### Contributing
To improve these runbooks:
- Test procedures on different Windows versions
- Add new troubleshooting scenarios
- Update automated scripts
- Enhance security recommendations

### Feedback
These runbooks are based on real-world experience. Please share:
- Success stories from your deployments
- Issues encountered and solutions found
- Suggestions for improvement

---

## GitHub Issues

These runbooks are tracked and maintained through GitHub issues:

- **PowerShell Default Shell**: [Issue #132](https://github.com/homeiac/home/issues/132)
- **Passwordless Authentication**: [Issue #133](https://github.com/homeiac/home/issues/133)

## Repository Information

**Repository**: [Home Infrastructure](https://github.com/homeiac/home)  
**Last Updated**: November 2024  
**Tested On**: Windows 10/11, Windows Server 2019/2022