# Next Session: Fix Windows SSH File Transfer Issue

## Problem Statement

**Critical Issue**: SCP file transfers fail when PowerShell is set as the default SSH shell.

### Current Symptoms
```bash
scp localfile.txt windows-dev:
# Result: "scp: Received message too long 1347625027"
# Root Cause: PowerShell startup output interferes with SCP binary protocol
```

### Impact
- Cannot transfer files to/from Windows machine using standard SCP
- Limits automation capabilities and file management
- Forces manual file operations or workarounds

## Immediate Workaround Available

**SMB Share Solution** (for local dev machine):
- Windows machine IP: `192.168.4.225`
- Username: `gshiv`
- Password: `gopal1sat` 
- Can likely mount SMB share for direct file access

## Tasks for Next Session

### 1. **Implement SMB Share Workaround** (Priority: High)

```bash
# Test SMB connectivity
smbclient -L //192.168.4.225 -U gshiv

# Mount Windows share (macOS/Linux)
mkdir -p /tmp/windows-share
mount -t smbfs //gshiv:gopal1sat@192.168.4.225/C$ /tmp/windows-share

# Alternative: Use smbclient for file transfers
smbclient //192.168.4.225/C$ -U gshiv -c "put localfile.txt remotefile.txt"
```

### 2. **Research Alternative File Transfer Methods** (Priority: High)

#### A. SFTP Alternative
```bash
# Test if SFTP works (uses SSH but different protocol)
sftp windows-dev
# Commands: put, get, ls, cd, etc.
```

#### B. PowerShell Remoting File Transfer
```bash
# Use Invoke-WebRequest for downloads
ssh windows-dev 'Invoke-WebRequest -Uri "http://source/file" -OutFile "C:\dest\file"'

# Use PowerShell copy commands
ssh windows-dev 'Copy-Item source destination'
```

#### C. Base64 Encoding Workaround
```bash
# Encode file to base64, transfer as text, decode on Windows
base64 localfile.txt > encoded.txt
ssh windows-dev 'certutil -decode encoded.txt decoded.txt'
```

### 3. **Investigate PowerShell SSH Configuration** (Priority: Medium)

#### A. Test PowerShell Silent Mode
```bash
# Try PowerShell with no profile/logo
ssh windows-dev 'powershell -NoProfile -NoLogo -Command "Get-Host"'
```

#### B. Alternative Shell Configuration
```powershell
# Test setting PowerShell with specific parameters
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoLogo -NoProfile"
```

#### C. Subsystem Configuration
```bash
# Research SSH subsystem for file transfers
# Check if we can configure separate subsystem for SCP
```

### 4. **Test Temporary Shell Switching** (Priority: Medium)

```bash
# Function to temporarily disable PowerShell for file transfers
function scp_to_windows() {
    ssh windows-dev 'Remove-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell; Restart-Service sshd'
    sleep 5
    scp "$@"
    ssh windows-dev 'Set-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "powershell.exe"; Restart-Service sshd'
}
```

### 5. **Create Comprehensive File Transfer Solution** (Priority: High)

Create a new runbook: `docs/runbooks/windows-ssh-file-transfers.md` covering:

- All working file transfer methods
- Performance comparison
- Use case recommendations (SMB for bulk, SFTP for automation, etc.)
- Integration with existing PowerShell default shell setup
- Automated wrapper functions/scripts

### 6. **Update Existing Runbooks** (Priority: Medium)

Update both existing runbooks with:
- File transfer limitation warnings
- References to the file transfer solutions guide  
- Recommended setup order if file transfers are critical

## Expected Solutions Priority

### Tier 1 (Immediate Use)
1. **SMB Share** - Direct file system access, best for bulk transfers
2. **SFTP** - Standard protocol, should work with PowerShell default
3. **PowerShell Remoting** - Native Windows solution

### Tier 2 (Automation Friendly)
1. **Wrapper Scripts** - Automate shell switching for SCP
2. **Base64 Transfer** - Reliable for small files
3. **Web-based Transfer** - HTTP uploads/downloads

### Tier 3 (Advanced Solutions)  
1. **SSH Subsystem Configuration** - Custom SCP handling
2. **PowerShell SSH Module** - Native PowerShell SSH client
3. **Alternative SSH Server** - Different Windows SSH implementation

## Testing Checklist

For each solution, test:
- [ ] Small text files (< 1KB)
- [ ] Binary files (images, executables)  
- [ ] Large files (> 10MB)
- [ ] Bidirectional transfers (upload/download)
- [ ] Automation compatibility (scriptable)
- [ ] Performance compared to native SCP

## Success Criteria

1. **Reliable file transfer** method that works with PowerShell default shell
2. **Documentation** covering all viable approaches
3. **Automated tools** for common file transfer scenarios
4. **Updated runbooks** with file transfer guidance
5. **Performance acceptable** for typical development workflows

## Implementation Notes

- Test all solutions on the actual Windows dev machine (192.168.4.225)
- Prioritize solutions that don't require changing the PowerShell default shell
- Consider security implications of each transfer method
- Document performance characteristics and limitations
- Create helper functions/aliases for common operations

---

This should provide a comprehensive approach to solving the file transfer limitation while maintaining the benefits of PowerShell as the default SSH shell.