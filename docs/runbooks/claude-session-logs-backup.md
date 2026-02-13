# Claude Session Logs Backup

## Overview

Backup Claude Code session logs from multiple sources for incident investigation, debugging, and audit purposes.

### Sources
- **Mac local**: `~/.claude/projects/` on developer Mac
- **claudecodeui pods**: Standard and blue deployments in K8s

### Target
- **SMB Share**: `smb://192.168.4.120/secure/claude-sessions/`
- **Mount point** (Mac): `/Volumes/secure/claude-sessions/`
- **Mount point** (K8s pods): `/mnt/claude-sessions/`

### Repos Tracked
- `home` - Homelab infrastructure
- `chorus` - Work project
- `the-road-to-devops` - DevOps learning repo

## Directory Structure

```
/shares/claude-sessions/              # On samba server
├── source-mac-local/
│   ├── repo-home/
│   ├── repo-chorus/
│   └── repo-the-road-to-devops/
├── source-claudecodeui/
│   └── repo-home/
└── source-claudecodeui-blue/
    └── repo-home/
```

## Prerequisites

### SMB Share Access

1. **Mac**: Mount the share
   ```bash
   open 'smb://gshiva@192.168.4.120/secure'
   # Or via Finder: Cmd+K → smb://192.168.4.120/secure
   ```
   Verify: `ls /Volumes/secure`

2. **K8s pods**: SMB CSI driver mounts automatically via PVC
   - PVC: `claude-sessions-smb` in `claudecodeui` namespace
   - Mount: `/mnt/claude-sessions/` inside pods

### Create Directory Structure

On first use, create the target directories:

```bash
# From Mac (with SMB mounted)
mkdir -p /Volumes/secure/claude-sessions/{source-mac-local,source-claudecodeui,source-claudecodeui-blue}/{repo-home,repo-chorus,repo-the-road-to-devops}
```

## Manual Backup Procedure

### From Mac Local

```bash
# Set source and destination
SRC_BASE="$HOME/.claude/projects"
DST_BASE="/Volumes/secure/claude-sessions/source-mac-local"

# Backup home repo
rsync -av --progress \
  "$SRC_BASE/-Users-10381054-code-home/"*.jsonl \
  "$DST_BASE/repo-home/"

# Backup chorus repo
rsync -av --progress \
  "$SRC_BASE/-Users-10381054-code-chorus/"*.jsonl \
  "$DST_BASE/repo-chorus/"

# Backup the-road-to-devops repo
rsync -av --progress \
  "$SRC_BASE/-Users-10381054-code-the-road-to-devops/"*.jsonl \
  "$DST_BASE/repo-the-road-to-devops/"
```

### From claudecodeui Pods (K8s)

The pods have the SMB share mounted at `/mnt/claude-sessions/`. Add a sync to the pod's init or use a CronJob.

**Manual sync from inside a pod:**

```bash
# Exec into the pod
kubectl exec -it -n claudecodeui deploy/claudecodeui-blue -- bash

# Inside pod - sync session logs to SMB
rsync -av ~/.claude/projects/-home-claude-projects-home/*.jsonl \
  /mnt/claude-sessions/source-claudecodeui-blue/repo-home/
```

**From Mac via kubectl:**

```bash
# Get pod name
POD=$(kubectl get pods -n claudecodeui -l app=claudecodeui-blue -o jsonpath='{.items[0].metadata.name}')

# Copy from pod to local temp, then to SMB
kubectl cp claudecodeui/$POD:/home/claude/.claude/projects/-home-claude-projects-home/ /tmp/claude-sessions-blue/
rsync -av /tmp/claude-sessions-blue/*.jsonl /Volumes/secure/claude-sessions/source-claudecodeui-blue/repo-home/
```

## Automated Backup Script

### Usage

```bash
# Run the backup script
~/code/home/scripts/claude/backup-session-logs.sh

# Options
--source mac|k8s|all    # Which source to backup (default: all)
--repo home|chorus|devops|all  # Which repo to backup (default: all)
--dry-run               # Show what would be copied without copying
```

### Examples

```bash
# Backup everything
./scripts/claude/backup-session-logs.sh

# Backup only Mac local sessions
./scripts/claude/backup-session-logs.sh --source mac

# Backup only home repo from all sources
./scripts/claude/backup-session-logs.sh --repo home

# Dry run - see what would be copied
./scripts/claude/backup-session-logs.sh --dry-run
```

## Scheduled Backup Options

### Option 1: Mac launchd (for Mac local sessions)

Create `~/Library/LaunchAgents/com.homelab.claude-backup.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.homelab.claude-backup</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/10381054/code/home/scripts/claude/backup-session-logs.sh</string>
        <string>--source</string>
        <string>mac</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</dict>
</plist>
```

Load with: `launchctl load ~/Library/LaunchAgents/com.homelab.claude-backup.plist`

### Option 2: K8s CronJob (for pod sessions)

The pods have the SMB share mounted, so a CronJob can sync periodically:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: claude-session-backup
  namespace: claudecodeui
spec:
  schedule: "0 3 * * *"  # 3 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: ghcr.io/homeiac/claudecodeui:main
            command:
            - /bin/sh
            - -c
            - |
              rsync -av /home/claude/.claude/projects/-home-claude-projects-home/*.jsonl \
                /mnt/claude-sessions/source-claudecodeui/repo-home/
            volumeMounts:
            - name: claude-home
              mountPath: /home/claude
            - name: claude-sessions-smb
              mountPath: /mnt/claude-sessions
          restartPolicy: OnFailure
          volumes:
          - name: claude-home
            persistentVolumeClaim:
              claimName: claude-data-blue
          - name: claude-sessions-smb
            persistentVolumeClaim:
              claimName: claude-sessions-smb
```

## Verification

### Check Backup Completed

```bash
# List backed up files
ls -la /Volumes/secure/claude-sessions/source-mac-local/repo-home/

# Count files per source
find /Volumes/secure/claude-sessions -name "*.jsonl" | wc -l

# Check latest backup timestamp
ls -lt /Volumes/secure/claude-sessions/source-mac-local/repo-home/ | head -5
```

### Compare Source vs Backup

```bash
# Count source files
find ~/.claude/projects/-Users-10381054-code-home -name "*.jsonl" | wc -l

# Count backup files
find /Volumes/secure/claude-sessions/source-mac-local/repo-home -name "*.jsonl" | wc -l
```

## Restore from Backup

### Restore to Mac Local

```bash
# Restore all session files for home repo
rsync -av /Volumes/secure/claude-sessions/source-mac-local/repo-home/*.jsonl \
  ~/.claude/projects/-Users-10381054-code-home/
```

### Restore to K8s Pod

```bash
# Copy from SMB to local temp
cp /Volumes/secure/claude-sessions/source-claudecodeui-blue/repo-home/*.jsonl /tmp/

# Get pod name
POD=$(kubectl get pods -n claudecodeui -l app=claudecodeui-blue -o jsonpath='{.items[0].metadata.name}')

# Copy to pod
kubectl cp /tmp/*.jsonl claudecodeui/$POD:/home/claude/.claude/projects/-home-claude-projects-home/
```

## Infrastructure Setup

The SMB mount in K8s is configured via:

1. **SMB CSI Driver**: `gitops/clusters/homelab/infrastructure/smb-csi-driver/`
2. **Credentials Secret**: `gitops/clusters/homelab/infrastructure/smb-csi-driver/secrets/samba-credentials.sops.yaml`
3. **PV/PVC**: `gitops/clusters/homelab/apps/claudecodeui/smb-claude-sessions-pv.yaml`
4. **Deployment mounts**: Added to both `deployment.yaml` and `blue/deployment-blue.yaml`

### First-Time Setup

1. **Encrypt the samba credentials secret:**
   ```bash
   cd ~/code/home
   sops -e -i gitops/clusters/homelab/infrastructure/smb-csi-driver/secrets/samba-credentials.sops.yaml
   ```

2. **Create the share directory on samba server:**
   ```bash
   # SSH to samba LXC or use kubectl exec
   mkdir -p /shares/claude-sessions
   chown 1001:1001 /shares/claude-sessions
   ```

3. **Push and reconcile:**
   ```bash
   git add gitops/
   git commit -m "feat: add SMB mount for claude session backups"
   git push
   flux reconcile kustomization flux-system --with-source
   ```

## Troubleshooting

### SMB Mount Not Working

```bash
# Check CSI driver pods
kubectl get pods -n kube-system | grep smb

# Check PV/PVC status
kubectl get pv claude-sessions-smb-pv
kubectl get pvc -n claudecodeui claude-sessions-smb

# Check events for errors
kubectl describe pvc -n claudecodeui claude-sessions-smb
```

### Permission Denied on SMB Share

- Check samba credentials secret is correct
- Verify the share directory exists on the samba server
- Check uid/gid in mount options matches the pod user (1001)

### Mac SMB Mount Disconnected

```bash
# Remount
open 'smb://gshiva@192.168.4.120/secure'

# Or via command line
mount -t smbfs //gshiva@192.168.4.120/secure /Volumes/secure
```
