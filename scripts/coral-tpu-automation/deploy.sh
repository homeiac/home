#!/bin/bash
# Deployment script for Coral TPU automation
# This script safely deploys the automation to the target system

set -e

# Configuration
TARGET_HOST="fun-bedbug.maas"
TARGET_DIR="/root/scripts"
SERVICE_NAME="coral-tpu-init"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Coral TPU Automation Deployment ===${NC}"
echo ""

# Step 1: Test locally first
echo -e "${YELLOW}Step 1: Running local tests...${NC}"
bash test-coral-automation.sh
if [ $? -ne 0 ]; then
    echo -e "${RED}Local tests failed! Aborting deployment.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Local tests passed${NC}\n"

# Step 2: Create remote directory structure
echo -e "${YELLOW}Step 2: Creating remote directories...${NC}"
ssh root@${TARGET_HOST} "mkdir -p ${TARGET_DIR} /root/coral-backups /var/log"
echo -e "${GREEN}✓ Directories created${NC}\n"

# Step 3: Copy scripts to target
echo -e "${YELLOW}Step 3: Copying scripts to ${TARGET_HOST}...${NC}"
scp mock-coral-init.sh coral-tpu-init.sh root@${TARGET_HOST}:${TARGET_DIR}/
ssh root@${TARGET_HOST} "chmod +x ${TARGET_DIR}/*.sh"
echo -e "${GREEN}✓ Scripts deployed${NC}\n"

# Step 4: Run dry-run test on target
echo -e "${YELLOW}Step 4: Running dry-run test on target...${NC}"
ssh root@${TARGET_HOST} "cd ${TARGET_DIR} && DRY_RUN=true bash coral-tpu-init.sh"
echo -e "${GREEN}✓ Dry-run completed${NC}\n"

# Step 5: Ask for confirmation
echo -e "${YELLOW}Step 5: Review and confirm${NC}"
echo "The automation has been deployed in DRY-RUN mode."
echo ""
echo "To enable automatic initialization on boot:"
echo "  1. Copy the systemd service file:"
echo "     scp coral-tpu-init.service root@${TARGET_HOST}:/etc/systemd/system/"
echo ""
echo "  2. Enable the service:"
echo "     ssh root@${TARGET_HOST} 'systemctl daemon-reload'"
echo "     ssh root@${TARGET_HOST} 'systemctl enable ${SERVICE_NAME}.service'"
echo ""
echo "  3. Test the service manually first:"
echo "     ssh root@${TARGET_HOST} 'systemctl start ${SERVICE_NAME}.service'"
echo "     ssh root@${TARGET_HOST} 'systemctl status ${SERVICE_NAME}.service'"
echo ""
echo "To run manually in PRODUCTION mode:"
echo "  ssh root@${TARGET_HOST} 'cd ${TARGET_DIR} && DRY_RUN=false bash coral-tpu-init.sh'"
echo ""
echo -e "${BLUE}Would you like to install the systemd service now? (y/n)${NC}"
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Installing systemd service...${NC}"
    
    # Update service file with correct path
    sed -i "s|/root/scripts/coral-tpu-init.sh|${TARGET_DIR}/coral-tpu-init.sh|g" coral-tpu-init.service
    
    # Copy service file
    scp coral-tpu-init.service root@${TARGET_HOST}:/etc/systemd/system/
    
    # Enable service (but don't start yet)
    ssh root@${TARGET_HOST} "systemctl daemon-reload"
    ssh root@${TARGET_HOST} "systemctl enable ${SERVICE_NAME}.service"
    
    echo -e "${GREEN}✓ Service installed and enabled${NC}"
    echo ""
    echo "The service will run automatically on next boot."
    echo "To test it now, run:"
    echo "  ssh root@${TARGET_HOST} 'systemctl start ${SERVICE_NAME}.service'"
    echo "  ssh root@${TARGET_HOST} 'journalctl -u ${SERVICE_NAME}.service -f'"
else
    echo -e "${YELLOW}Service installation skipped.${NC}"
    echo "You can install it manually later using the instructions above."
fi

echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Next steps:"
echo "1. Test the script manually in dry-run mode (already done)"
echo "2. Test the script manually in production mode"
echo "3. Test the systemd service"
echo "4. Reboot to verify automatic initialization"