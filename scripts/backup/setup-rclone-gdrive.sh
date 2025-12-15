#!/bin/bash
# Setup rclone with Google Drive for offsite backup
#
# This script:
# 1. Installs rclone if not present
# 2. Guides through Google Drive OAuth setup
# 3. Creates backup sync configuration
# 4. Tests connection
#
# Run on: K3s node that will sync backups (or any machine with kubectl access)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RCLONE_CONFIG_DIR="$HOME/.config/rclone"
RCLONE_CONFIG="$RCLONE_CONFIG_DIR/rclone.conf"
REMOTE_NAME="gdrive-backup"

echo "========================================="
echo "Rclone Google Drive Setup"
echo "========================================="
echo ""

# Install rclone if not present
if ! command -v rclone &>/dev/null; then
    echo "Installing rclone..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq rclone
    elif command -v curl &>/dev/null; then
        curl https://rclone.org/install.sh | sudo bash
    else
        echo "ERROR: Cannot install rclone. Please install manually."
        echo "  https://rclone.org/install/"
        exit 1
    fi
fi

echo "rclone version: $(rclone version | head -1)"
echo ""

# Check if remote already exists
if rclone listremotes 2>/dev/null | grep -q "^${REMOTE_NAME}:$"; then
    echo "Remote '$REMOTE_NAME' already exists."
    echo ""
    read -p "Reconfigure? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing configuration."
        rclone about "$REMOTE_NAME:" 2>/dev/null || echo "WARNING: Could not verify remote"
        exit 0
    fi
    rclone config delete "$REMOTE_NAME"
fi

echo "Setting up Google Drive remote..."
echo ""
echo "INSTRUCTIONS:"
echo "1. You will be prompted to authorize rclone with Google"
echo "2. A browser window will open (or you'll get a URL to visit)"
echo "3. Sign in with your Google account"
echo "4. Grant rclone access to Google Drive"
echo ""
echo "If running on a headless server, use the 'remote' option when asked"
echo "and complete OAuth on your local machine."
echo ""

read -p "Press Enter to continue..."

# Create rclone config directory
mkdir -p "$RCLONE_CONFIG_DIR"

# Use rclone config to set up Google Drive
# This will interactively guide through OAuth
rclone config create "$REMOTE_NAME" drive \
    scope=drive \
    --config "$RCLONE_CONFIG"

# Test connection
echo ""
echo "Testing connection..."
if rclone about "$REMOTE_NAME:" 2>/dev/null; then
    echo "✓ Google Drive connected successfully!"
else
    echo "WARNING: Could not verify connection. You may need to complete OAuth."
    echo ""
    echo "To complete OAuth on another machine:"
    echo "  rclone authorize drive"
    echo ""
    echo "Then paste the token when prompted."
fi

# Create backup folder on Google Drive
BACKUP_FOLDER="homelab-backup"
echo ""
echo "Creating backup folder: $BACKUP_FOLDER"
rclone mkdir "$REMOTE_NAME:$BACKUP_FOLDER" 2>/dev/null || true

# Show drive info
echo ""
echo "Google Drive Info:"
rclone about "$REMOTE_NAME:" 2>/dev/null || echo "(could not retrieve info)"

echo ""
echo "========================================="
echo "Setup Complete"
echo "========================================="
echo ""
echo "Remote name: $REMOTE_NAME"
echo "Config file: $RCLONE_CONFIG"
echo "Backup folder: $REMOTE_NAME:$BACKUP_FOLDER"
echo ""
echo "Test commands:"
echo "  rclone ls $REMOTE_NAME:$BACKUP_FOLDER"
echo "  rclone copy /path/to/file $REMOTE_NAME:$BACKUP_FOLDER/"
echo ""
echo "Next step: Run sync-postgres-to-gdrive.sh to sync PostgreSQL backups"
