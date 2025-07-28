# Home Assistant OS SSH Access Setup Guide

## Overview
This guide documents how to enable SSH access to Home Assistant OS host system, including the critical workaround for setting up SSH keys when copy/paste functionality is limited.

## Prerequisites
- Home Assistant OS running (tested on HAOS 16.0)
- File Editor add-on installed
- Terminal & SSH add-on installed
- Physical or console access to Home Assistant device
- SSH public key available

## Background
Home Assistant OS uses dropbear SSH server which requires `/root/.ssh/authorized_keys` to be present before it will start. The challenge is getting your SSH public key into this file when traditional copy/paste methods don't work reliably.

## Step-by-Step Implementation

### Step 1: Prepare Your SSH Public Key
On your client machine, ensure you have an SSH key pair:
```bash
# Generate key if needed
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# Get your public key
cat ~/.ssh/id_rsa.pub
```

**Copy the entire public key output to your clipboard.**

### Step 2: Use File Editor Add-on Workaround
This is the critical step that overcomes copy/paste limitations:

1. **Open File Editor add-on** in Home Assistant web interface
2. **Navigate to `/root/.ssh/` directory** (create if it doesn't exist)
3. **Create new file** named `authorized_keys`
4. **Type a random character** in the file (e.g., "x")
5. **Select that character** by highlighting it
6. **Press `Cmd+V` (Mac) or `Ctrl+V` (Windows/Linux)** to paste your public key
   - ⚠️ **Critical**: You MUST select text first before pasting
   - ⚠️ **Copy/paste is disabled by default** - this workaround bypasses the restriction
7. **Delete the random character** you typed initially
8. **Save the file**

**File should contain only your SSH public key, like:**
```
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC... your_email@example.com
```

### Step 3: Set Correct Permissions via Console
1. **Access Home Assistant console** (keyboard/monitor or advanced terminal)
2. **Type `login`** to get root shell
3. **Set proper permissions:**
```bash
chmod 700 /root/.ssh
chmod 600 /root/.ssh/authorized_keys
chown root:root /root/.ssh/authorized_keys
```

### Step 4: Start Dropbear SSH Service
```bash
# Start dropbear SSH service
/usr/sbin/dropbear -r /etc/dropbear/dropbear_rsa_host_key -p 22222
```

**Note**: Dropbear will NOT start if `/root/.ssh/authorized_keys` is missing or has wrong permissions.

### Step 5: Verify SSH Access
From your client machine:
```bash
# Test SSH connection
ssh root@192.168.4.240 -p 22222

# Should connect without password prompt
```

## Alternative Methods (If File Editor Unavailable)

### Method 2: Advanced SSH & Web Terminal
1. **Install "Advanced SSH & Web Terminal" add-on**
2. **Set Protection Mode: OFF**
3. **Access terminal and type `login`**
4. **Create authorized_keys manually:**
```bash
mkdir -p /root/.ssh
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC... your_email@example.com" > /root/.ssh/authorized_keys
chmod 700 /root/.ssh
chmod 600 /root/.ssh/authorized_keys
```

### Method 3: USB Drive Method
1. **Create file on USB drive** with your public key
2. **Insert USB into Home Assistant device**
3. **Access console and mount USB:**
```bash
login
mkdir /mnt/usb
mount /dev/sda1 /mnt/usb
mkdir -p /root/.ssh
cp /mnt/usb/authorized_keys /root/.ssh/
chmod 700 /root/.ssh
chmod 600 /root/.ssh/authorized_keys
umount /mnt/usb
```

## Troubleshooting

### SSH Connection Refused
**Problem**: `ssh: connect to host 192.168.4.240 port 22222: Connection refused`

**Solutions**:
1. **Check if dropbear is running:**
```bash
ps aux | grep dropbear
```

2. **Check authorized_keys exists:**
```bash
ls -la /root/.ssh/authorized_keys
```

3. **Restart dropbear:**
```bash
pkill dropbear
/usr/sbin/dropbear -r /etc/dropbear/dropbear_rsa_host_key -p 22222
```

### Permission Denied
**Problem**: SSH connects but authentication fails

**Solutions**:
1. **Check file permissions:**
```bash
ls -la /root/.ssh/
# Should show: drwx------ 2 root root ... .ssh/
# Should show: -rw------- 1 root root ... authorized_keys
```

2. **Check file content:**
```bash
cat /root/.ssh/authorized_keys
# Should contain your public key, no extra characters
```

### Copy/Paste Not Working
**Problem**: Cannot paste SSH key into File Editor

**Solutions**:
1. **Use the select-then-paste workaround** (primary method)
2. **Try different browsers** (Chrome, Firefox, Safari)
3. **Use Advanced SSH & Web Terminal** instead
4. **Use USB drive method** as fallback

## Making SSH Persistent

### Auto-start Dropbear on Boot
Create a systemd service:
```bash
cat > /etc/systemd/system/dropbear-ssh.service << 'EOF'
[Unit]
Description=Dropbear SSH server
After=network.target

[Service]
Type=forking
ExecStart=/usr/sbin/dropbear -r /etc/dropbear/dropbear_rsa_host_key -p 22222
ExecReload=/bin/kill -HUP $MAINPID
KillMode=process
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl enable dropbear-ssh.service
systemctl start dropbear-ssh.service
```

## Security Considerations
- **Change default port** from 22222 to something else
- **Use strong SSH keys** (RSA 4096-bit or Ed25519)
- **Limit access** by IP if possible
- **Monitor SSH logs** regularly
- **Keep authorized_keys** file updated

## References
- [Home Assistant Community: SSH Access Guide](https://community.home-assistant.io/t/howto-how-to-access-the-home-assistant-os-host-itself-over-ssh/263352)
- [Dropbear SSH Documentation](https://matt.ucc.asn.au/dropbear/dropbear.html)

## Key Insights
- **File Editor copy/paste workaround** is critical for environments where traditional methods fail
- **Dropbear requires authorized_keys** to exist before starting
- **Permissions must be exact** (700 for .ssh, 600 for authorized_keys)
- **Multiple fallback methods** ensure access can be established