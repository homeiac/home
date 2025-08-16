#!/bin/bash
# Coral TPU Automation Deployment Script
# Syncs the automation system to Proxmox nodes

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
TARGET_HOST="${1:-fun-bedbug.maas}"
TARGET_USER="${2:-root}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# Validate source files exist
validate_source() {
    log "Validating source files..."
    
    local required_files=(
        "src/homelab/coral_models.py"
        "src/homelab/coral_detection.py"
        "src/homelab/coral_config.py"
        "src/homelab/coral_initialization.py"
        "src/homelab/coral_automation.py"
        "scripts/coral_tpu_automation.py"
        "pyproject.toml"
    )
    
    for file in "${required_files[@]}"; do
        if [[ ! -f "$REPO_ROOT/$file" ]]; then
            error "Required file not found: $file"
        fi
    done
    
    log "Source validation complete"
}

# Test SSH connectivity
test_connectivity() {
    log "Testing SSH connectivity to $TARGET_USER@$TARGET_HOST..."
    
    if ! ssh -o ConnectTimeout=5 "$TARGET_USER@$TARGET_HOST" "echo 'Connection successful'" >/dev/null 2>&1; then
        error "Cannot connect to $TARGET_USER@$TARGET_HOST"
    fi
    
    log "SSH connectivity confirmed"
}

# Install Python dependencies
install_dependencies() {
    log "Installing Python dependencies on target system..."
    
    ssh "$TARGET_USER@$TARGET_HOST" bash << 'EOF'
        # Update package list
        apt-get update -qq
        
        # Install Python 3 and pip if not present
        if ! command -v python3 &> /dev/null; then
            apt-get install -y python3 python3-pip
        fi
        
        # Install required Python packages
        pip3 install --upgrade pip setuptools wheel
        pip3 install typing-extensions dataclasses pathlib
        
        echo "Python dependencies installed"
EOF
    
    log "Dependencies installation complete"
}

# Create directory structure
create_directories() {
    log "Creating directory structure on target system..."
    
    ssh "$TARGET_USER@$TARGET_HOST" bash << 'EOF'
        # Create coral automation directories
        mkdir -p /root/coral-automation/{src/homelab,scripts,tests}
        mkdir -p /root/coral-backups
        mkdir -p /var/log
        
        # Set proper permissions
        chmod 755 /root/coral-automation
        chmod 755 /root/coral-automation/scripts
        chmod 755 /root/coral-backups
        
        echo "Directory structure created"
EOF
    
    log "Directory structure setup complete"
}

# Sync source files
sync_files() {
    log "Syncing source files to target system..."
    
    # Copy Python modules
    scp "$REPO_ROOT/src/homelab/coral_models.py" \
        "$TARGET_USER@$TARGET_HOST:/root/coral-automation/src/homelab/"
    
    scp "$REPO_ROOT/src/homelab/coral_detection.py" \
        "$TARGET_USER@$TARGET_HOST:/root/coral-automation/src/homelab/"
    
    scp "$REPO_ROOT/src/homelab/coral_config.py" \
        "$TARGET_USER@$TARGET_HOST:/root/coral-automation/src/homelab/"
    
    scp "$REPO_ROOT/src/homelab/coral_initialization.py" \
        "$TARGET_USER@$TARGET_HOST:/root/coral-automation/src/homelab/"
    
    scp "$REPO_ROOT/src/homelab/coral_automation.py" \
        "$TARGET_USER@$TARGET_HOST:/root/coral-automation/src/homelab/"
    
    # Copy CLI script
    scp "$REPO_ROOT/scripts/coral_tpu_automation.py" \
        "$TARGET_USER@$TARGET_HOST:/root/coral-automation/scripts/"
    
    # Create __init__.py files
    ssh "$TARGET_USER@$TARGET_HOST" bash << 'EOF'
        touch /root/coral-automation/src/__init__.py
        touch /root/coral-automation/src/homelab/__init__.py
        
        # Make CLI script executable
        chmod +x /root/coral-automation/scripts/coral_tpu_automation.py
        
        echo "Source files synced"
EOF
    
    log "File sync complete"
}

# Create systemd service
create_service() {
    log "Creating systemd service for coral automation..."
    
    ssh "$TARGET_USER@$TARGET_HOST" bash << 'EOF'
cat > /etc/systemd/system/coral-tpu-init.service << 'SVCEOF'
[Unit]
Description=Coral TPU Initialization Service
After=network.target
Wants=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /root/coral-automation/scripts/coral_tpu_automation.py
Environment=PYTHONPATH=/root/coral-automation/src
WorkingDirectory=/root/coral-automation
StandardOutput=journal
StandardError=journal
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SVCEOF

        # Reload systemd and enable service
        systemctl daemon-reload
        systemctl enable coral-tpu-init.service
        
        echo "Systemd service created and enabled"
EOF
    
    log "Systemd service setup complete"
}

# Create convenience wrapper script
create_wrapper() {
    log "Creating convenience wrapper script..."
    
    ssh "$TARGET_USER@$TARGET_HOST" bash << 'EOF'
cat > /usr/local/bin/coral-tpu << 'WRAPEOF'
#!/bin/bash
# Coral TPU Automation Wrapper Script

export PYTHONPATH="/root/coral-automation/src:$PYTHONPATH"
cd /root/coral-automation

exec /usr/bin/python3 /root/coral-automation/scripts/coral_tpu_automation.py "$@"
WRAPEOF

        chmod +x /usr/local/bin/coral-tpu
        
        echo "Wrapper script created"
EOF
    
    log "Wrapper script setup complete"
}

# Test installation
test_installation() {
    log "Testing installation..."
    
    ssh "$TARGET_USER@$TARGET_HOST" bash << 'EOF'
        export PYTHONPATH="/root/coral-automation/src"
        cd /root/coral-automation
        
        # Test CLI help
        python3 scripts/coral_tpu_automation.py --help >/dev/null 2>&1
        if [[ $? -eq 0 ]]; then
            echo "✅ CLI script working"
        else
            echo "❌ CLI script failed"
            exit 1
        fi
        
        # Test wrapper script
        /usr/local/bin/coral-tpu --help >/dev/null 2>&1
        if [[ $? -eq 0 ]]; then
            echo "✅ Wrapper script working"
        else
            echo "❌ Wrapper script failed"
            exit 1
        fi
        
        # Test systemd service syntax
        systemctl status coral-tpu-init.service >/dev/null 2>&1
        if [[ $? -eq 3 ]]; then  # 3 = service not running but loaded
            echo "✅ Systemd service loaded"
        else
            echo "❌ Systemd service failed to load"
            exit 1
        fi
        
        echo "Installation test complete"
EOF
    
    log "Installation test passed"
}

# Show usage information
show_usage() {
    log "Coral TPU Automation Installation Complete!"
    
    cat << 'USAGE'

🔧 Usage Instructions:

1. Check current system status:
   coral-tpu --status-only

2. Preview what automation would do:
   coral-tpu --dry-run

3. Run automation manually:
   coral-tpu

4. Enable automatic startup:
   systemctl start coral-tpu-init.service

5. Check service status:
   systemctl status coral-tpu-init.service

6. View logs:
   journalctl -u coral-tpu-init.service -f

📁 File Locations:
   - Source code: /root/coral-automation/
   - CLI script: /usr/local/bin/coral-tpu
   - Systemd service: coral-tpu-init.service
   - Config backups: /root/coral-backups/
   - Logs: /var/log/coral-tpu-automation.log

🛡️  Safety Features:
   - Never initializes if Coral already in Google mode
   - Automatic LXC config backup before changes
   - Prevents breaking Frigate TPU access
   - Comprehensive logging and error handling

USAGE
}

# Main deployment function
main() {
    log "Starting Coral TPU Automation deployment to $TARGET_HOST"
    
    validate_source
    test_connectivity
    install_dependencies
    create_directories
    sync_files
    create_service
    create_wrapper
    test_installation
    show_usage
    
    log "Deployment completed successfully! 🎉"
}

# Run with error handling
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi