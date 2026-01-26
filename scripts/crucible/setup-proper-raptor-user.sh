#!/bin/bash
# Setup gshiva user on proper-raptor
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

# Load password from .env
if [[ -f "$ENV_FILE" ]]; then
    CRUCIBLE_USER_PASSWORD=$(grep "^CRUCIBLE_USER_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$CRUCIBLE_USER_PASSWORD" ]]; then
    echo "ERROR: CRUCIBLE_USER_PASSWORD not found in $ENV_FILE"
    echo "Add: CRUCIBLE_USER_PASSWORD=yourpassword"
    exit 1
fi

HOST="ubuntu@192.168.4.189"
NEW_USER="gshiva"

echo "=== Setting up user $NEW_USER on proper-raptor ==="

# Check SSH access
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" "echo 'SSH OK'" 2>/dev/null; then
    echo "ERROR: Cannot SSH to $HOST"
    exit 1
fi

# Check if user already exists
if ssh "$HOST" "id $NEW_USER" 2>/dev/null; then
    echo "User $NEW_USER already exists"
else
    echo "Creating user $NEW_USER..."
    ssh "$HOST" "sudo useradd -m -s /bin/bash -G sudo $NEW_USER"
fi

# Set password
echo "Setting password for $NEW_USER..."
ssh "$HOST" "echo '$NEW_USER:$CRUCIBLE_USER_PASSWORD' | sudo chpasswd"

# Copy SSH keys from ubuntu user
echo "Copying SSH authorized_keys..."
ssh "$HOST" "sudo mkdir -p /home/$NEW_USER/.ssh && sudo cp /home/ubuntu/.ssh/authorized_keys /home/$NEW_USER/.ssh/ && sudo chown -R $NEW_USER:$NEW_USER /home/$NEW_USER/.ssh && sudo chmod 700 /home/$NEW_USER/.ssh && sudo chmod 600 /home/$NEW_USER/.ssh/authorized_keys"

# Enable password auth for this user (optional, SSH keys preferred)
echo "Ensuring SSH access..."
ssh "$HOST" "sudo usermod -aG sudo $NEW_USER"

echo ""
echo "=== User setup complete ==="
echo "Test: ssh $NEW_USER@192.168.4.189"
