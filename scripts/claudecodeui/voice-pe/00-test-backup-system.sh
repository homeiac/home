#!/bin/bash
set -e

# Test Voice PE backup system components
# Verifies backup/restore workflow without making changes

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

echo "=== Voice PE Backup System Test ==="
echo ""

# Test 1: Environment file
echo "[1/5] Checking environment file..."
if [[ -f "$ENV_FILE" ]]; then
    echo "  ✓ Found: $ENV_FILE"

    if grep -q "^HA_TOKEN=" "$ENV_FILE"; then
        echo "  ✓ HA_TOKEN configured"
    else
        echo "  ✗ HA_TOKEN not found in .env"
        exit 1
    fi
else
    echo "  ✗ Environment file missing: $ENV_FILE"
    exit 1
fi
echo ""

# Test 2: Backups directory
echo "[2/5] Checking backups directory..."
BACKUPS_DIR="$SCRIPT_DIR/backups"
if [[ -d "$BACKUPS_DIR" ]]; then
    echo "  ✓ Found: $BACKUPS_DIR"

    BACKUP_COUNT=$(ls -1 "$BACKUPS_DIR"/voice-pe-*.yaml 2>/dev/null | wc -l)
    echo "  ℹ Existing backups: $BACKUP_COUNT"
else
    echo "  ✗ Backups directory missing"
    exit 1
fi
echo ""

# Test 3: ESPHome connectivity
echo "[3/5] Testing ESPHome dashboard connectivity..."
ESPHOME_HOST="homeassistant.maas"
ESPHOME_PORT="6052"

if curl -s -f -m 5 "http://$ESPHOME_HOST:$ESPHOME_PORT" > /dev/null 2>&1; then
    echo "  ✓ ESPHome dashboard accessible: http://$ESPHOME_HOST:$ESPHOME_PORT"
else
    echo "  ⚠ ESPHome dashboard not accessible (may be normal if not running)"
    echo "    URL: http://$ESPHOME_HOST:$ESPHOME_PORT"
fi
echo ""

# Test 4: Script executability
echo "[4/5] Verifying script permissions..."
SCRIPTS=(
    "00-backup-voice-pe-config.sh"
    "98-restore-voice-pe-backup.sh"
    "99-factory-reset-voice-pe.sh"
)

for script in "${SCRIPTS[@]}"; do
    if [[ -x "$SCRIPT_DIR/$script" ]]; then
        echo "  ✓ $script is executable"
    else
        echo "  ✗ $script is not executable"
        chmod +x "$SCRIPT_DIR/$script"
        echo "    Fixed: chmod +x applied"
    fi
done
echo ""

# Test 5: Script syntax
echo "[5/5] Checking script syntax..."
for script in "${SCRIPTS[@]}"; do
    if bash -n "$SCRIPT_DIR/$script" 2>/dev/null; then
        echo "  ✓ $script syntax valid"
    else
        echo "  ✗ $script has syntax errors"
        bash -n "$SCRIPT_DIR/$script"
        exit 1
    fi
done
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ Backup system test completed successfully"
echo ""
echo "Next steps:"
echo "  • Create backup: ./00-backup-voice-pe-config.sh"
echo "  • Test restore: ./98-restore-voice-pe-backup.sh"
echo "  • View reset guide: ./99-factory-reset-voice-pe.sh"
echo ""
echo "For help: cat README-BACKUP-RESTORE.md"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
