#!/bin/bash
# Install rclone to ~/.local/bin (no sudo required)
#
# Usage: ./install-rclone.sh
#
# Downloads and installs rclone for the current user.
# Works in containers and environments without root access.

set -e

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
TMP_DIR="/tmp/rclone-install-$$"

echo "========================================="
echo "Rclone Installation (User Local)"
echo "========================================="
echo ""

# Check if already installed
if command -v rclone &>/dev/null; then
    CURRENT_VERSION=$(rclone version | head -1)
    echo "rclone already installed: $CURRENT_VERSION"
    read -p "Reinstall/upgrade? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing installation."
        exit 0
    fi
fi

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$TMP_DIR"
cd "$TMP_DIR"

echo "Downloading rclone..."
curl -sLO https://downloads.rclone.org/rclone-current-linux-amd64.zip

echo "Extracting..."
unzip -q rclone-current-linux-amd64.zip

echo "Installing to $INSTALL_DIR..."
cp rclone-*-linux-amd64/rclone "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/rclone"

# Cleanup
cd /
rm -rf "$TMP_DIR"

# Verify installation
echo ""
echo "Installed version:"
"$INSTALL_DIR/rclone" version | head -1

# Check PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo ""
    echo "NOTE: $INSTALL_DIR is not in your PATH."
    echo "Add to your shell config:"
    echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
fi

echo ""
echo "========================================="
echo "Installation Complete"
echo "========================================="
echo ""
echo "Next: Run setup-rclone-gdrive.sh to configure Google Drive"
