#!/bin/bash
# Setup rclone with Google Drive for offsite backup
#
# This script:
# 1. Checks for rclone (run install-rclone.sh first if needed)
# 2. Guides through Google Drive OAuth setup (supports headless)
# 3. Creates backup sync configuration
# 4. Tests connection
#
# For headless/container environments:
#   1. Run this script and choose "headless" mode
#   2. On a machine with a browser, run: rclone authorize "drive"
#   3. Paste the token when prompted

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RCLONE_CONFIG_DIR="$HOME/.config/rclone"
RCLONE_CONFIG="$RCLONE_CONFIG_DIR/rclone.conf"
REMOTE_NAME="gdrive-backup"
RCLONE="${RCLONE:-rclone}"

# Check for rclone in common locations
if ! command -v "$RCLONE" &>/dev/null; then
    if [ -x "$HOME/.local/bin/rclone" ]; then
        RCLONE="$HOME/.local/bin/rclone"
    else
        echo "ERROR: rclone not found."
        echo "Run install-rclone.sh first."
        exit 1
    fi
fi

echo "========================================="
echo "Rclone Google Drive Setup"
echo "========================================="
echo ""
echo "rclone: $RCLONE"
echo "rclone version: $($RCLONE version | head -1)"
echo ""

# Create rclone config directory
mkdir -p "$RCLONE_CONFIG_DIR"

# Check if remote already exists
if $RCLONE listremotes --config "$RCLONE_CONFIG" 2>/dev/null | grep -q "^${REMOTE_NAME}:$"; then
    echo "Remote '$REMOTE_NAME' already exists."
    echo ""

    # Test if it works
    if $RCLONE about "$REMOTE_NAME:" --config "$RCLONE_CONFIG" &>/dev/null; then
        echo "Connection verified - remote is working."
        $RCLONE about "$REMOTE_NAME:" --config "$RCLONE_CONFIG"
        echo ""
        read -p "Reconfigure anyway? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Keeping existing configuration."
            exit 0
        fi
    else
        echo "Remote exists but connection failed. Reconfiguring..."
    fi
    $RCLONE config delete "$REMOTE_NAME" --config "$RCLONE_CONFIG"
fi

echo ""
echo "========================================="
echo "OAuth Setup Mode"
echo "========================================="
echo ""
echo "Choose setup mode:"
echo "  1) Auto   - Opens browser on this machine (requires GUI)"
echo "  2) Headless - For containers/SSH (paste token from another machine)"
echo ""
read -p "Select [1/2]: " -n 1 -r MODE
echo ""

if [[ "$MODE" == "1" ]]; then
    # Auto mode - let rclone handle it
    echo ""
    echo "Starting OAuth flow..."
    echo "A browser window should open. If not, check the URL below."
    echo ""

    $RCLONE config create "$REMOTE_NAME" drive \
        scope=drive \
        --config "$RCLONE_CONFIG"
else
    # Headless mode - need to get token from another machine
    echo ""
    echo "========================================="
    echo "Headless OAuth Instructions"
    echo "========================================="
    echo ""
    echo "On a machine with a web browser, run:"
    echo ""
    echo "  rclone authorize \"drive\""
    echo ""
    echo "This will:"
    echo "  1. Open a browser for Google login"
    echo "  2. Ask you to grant access"
    echo "  3. Display a token (JSON blob)"
    echo ""
    echo "Copy the ENTIRE token including the curly braces."
    echo ""
    read -p "Press Enter when you have the token ready..."
    echo ""
    echo "Paste the token below (it should start with {\"access_token\"):"
    echo "(After pasting, press Enter twice)"
    echo ""

    # Read multi-line token
    TOKEN=""
    while IFS= read -r line; do
        [[ -z "$line" ]] && break
        TOKEN="${TOKEN}${line}"
    done

    if [[ -z "$TOKEN" ]]; then
        echo "ERROR: No token provided"
        exit 1
    fi

    # Create the config manually
    echo "Creating rclone configuration..."

    cat >> "$RCLONE_CONFIG" << EOF
[$REMOTE_NAME]
type = drive
scope = drive
token = $TOKEN
EOF

    echo "Configuration saved."
fi

# Test connection
echo ""
echo "Testing connection..."
if $RCLONE about "$REMOTE_NAME:" --config "$RCLONE_CONFIG" 2>/dev/null; then
    echo ""
    echo "Google Drive connected successfully!"
    echo ""
    $RCLONE about "$REMOTE_NAME:" --config "$RCLONE_CONFIG"
else
    echo ""
    echo "ERROR: Could not connect to Google Drive."
    echo "Check your token and try again."
    exit 1
fi

# Create backup folder on Google Drive
BACKUP_FOLDER="homelab-backup"
echo ""
echo "Creating backup folder: $BACKUP_FOLDER"
$RCLONE mkdir "$REMOTE_NAME:$BACKUP_FOLDER" --config "$RCLONE_CONFIG" 2>/dev/null || true
$RCLONE mkdir "$REMOTE_NAME:$BACKUP_FOLDER/postgres" --config "$RCLONE_CONFIG" 2>/dev/null || true

# List contents
echo ""
echo "Backup folder contents:"
$RCLONE ls "$REMOTE_NAME:$BACKUP_FOLDER" --config "$RCLONE_CONFIG" 2>/dev/null || echo "(empty)"

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
echo "  $RCLONE ls $REMOTE_NAME:$BACKUP_FOLDER --config $RCLONE_CONFIG"
echo "  $RCLONE copy /path/to/file $REMOTE_NAME:$BACKUP_FOLDER/"
echo ""
echo "Next step: Run sync-postgres-to-gdrive.sh to sync PostgreSQL backups"
