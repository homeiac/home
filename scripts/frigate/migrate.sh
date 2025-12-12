#!/bin/bash
set -euo pipefail

# migrate.sh
# Interactive migration guide for moving from still-fawn to K8s Frigate
# This script guides you through the entire migration process step-by-step

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================="
echo "Frigate K8s Migration Interactive Guide"
echo -e "=========================================${NC}"
echo ""

show_menu() {
    echo ""
    echo "What would you like to do?"
    echo ""
    echo "  1) Verify K8s Frigate is ready"
    echo "  2) Shutdown still-fawn Frigate (after verification)"
    echo "  3) Rollback to still-fawn Frigate"
    echo "  4) View migration checklist"
    echo "  5) View full documentation"
    echo "  q) Quit"
    echo ""
}

while true; do
    show_menu
    read -p "Enter your choice: " choice

    case $choice in
        1)
            echo ""
            echo -e "${BLUE}Running K8s Frigate verification...${NC}"
            echo ""
            if bash "$SCRIPT_DIR/verify-frigate-k8s.sh"; then
                echo ""
                echo -e "${GREEN}✓ Verification passed!${NC}"
                echo ""
                echo "Next steps:"
                echo "  - Manually test Frigate web UI: http://192.168.4.83:5000"
                echo "  - Verify all cameras are streaming"
                echo "  - Check Coral TPU is working"
                echo "  - Once satisfied, run option 2 to shutdown still-fawn"
            else
                echo ""
                echo -e "${RED}✗ Verification failed!${NC}"
                echo "Fix the issues above before proceeding with migration."
            fi
            ;;
        2)
            echo ""
            echo -e "${YELLOW}This will shutdown still-fawn Frigate LXC!${NC}"
            echo ""
            read -p "Have you verified K8s Frigate is working? (yes/no): " verified
            if [ "$verified" = "yes" ]; then
                bash "$SCRIPT_DIR/shutdown-still-fawn-frigate.sh"
            else
                echo "Please run option 1 to verify K8s Frigate first."
            fi
            ;;
        3)
            echo ""
            echo -e "${YELLOW}This will rollback to still-fawn Frigate${NC}"
            echo ""
            bash "$SCRIPT_DIR/rollback-to-still-fawn.sh"
            ;;
        4)
            echo ""
            if command -v bat &> /dev/null; then
                bat "$SCRIPT_DIR/MIGRATION-CHECKLIST.md"
            elif command -v less &> /dev/null; then
                less "$SCRIPT_DIR/MIGRATION-CHECKLIST.md"
            else
                cat "$SCRIPT_DIR/MIGRATION-CHECKLIST.md"
            fi
            ;;
        5)
            echo ""
            if command -v bat &> /dev/null; then
                bat "$SCRIPT_DIR/README.md"
            elif command -v less &> /dev/null; then
                less "$SCRIPT_DIR/README.md"
            else
                cat "$SCRIPT_DIR/README.md"
            fi
            ;;
        q|Q)
            echo "Exiting."
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice. Please try again.${NC}"
            ;;
    esac
done
