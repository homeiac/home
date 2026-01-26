#!/bin/bash
# HA Config Sync - Download, edit locally, validate, upload
#
# Usage:
#   ./ha-config-sync.sh pull                    # Download config to local
#   ./ha-config-sync.sh push                    # Upload config to HA
#   ./ha-config-sync.sh check                   # Validate config on HA
#   ./ha-config-sync.sh restart                 # Restart HA core
#   ./ha-config-sync.sh edit                    # Open config in $EDITOR
#
# Workflow:
#   1. ./ha-config-sync.sh pull
#   2. Edit ~/.homelab/ha-config/configuration.yaml
#   3. ./ha-config-sync.sh push
#   4. ./ha-config-sync.sh check
#   5. ./ha-config-sync.sh restart

set -e

PROXMOX_HOST="root@chief-horse.maas"
VMID=116
HA_CONFIG_PATH="/mnt/data/supervisor/homeassistant"
LOCAL_CONFIG_DIR="$HOME/.homelab/ha-config"
BACKUP_DIR="$HOME/.homelab/ha-config-backups"
TIMEOUT=120
YAMLLINT="${YAMLLINT:-/Users/10381054/Library/Python/3.9/bin/yamllint}"

# Ensure local dirs exist
mkdir -p "$LOCAL_CONFIG_DIR" "$BACKUP_DIR"

backup_config() {
    echo "=== Creating backup ==="
    BACKUP_NAME="ha-config-$(date +%Y%m%d-%H%M%S)"
    BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
    mkdir -p "$BACKUP_PATH"

    for f in "$LOCAL_CONFIG_DIR"/*.yaml; do
        if [[ -f "$f" ]]; then
            cp "$f" "$BACKUP_PATH/"
        fi
    done

    echo "Backup saved to: $BACKUP_PATH"

    # Keep only last 10 backups
    ls -dt "$BACKUP_DIR"/ha-config-* 2>/dev/null | tail -n +11 | xargs rm -rf 2>/dev/null || true
}

restore_config() {
    echo "=== Available backups ==="
    ls -dt "$BACKUP_DIR"/ha-config-* 2>/dev/null | head -10 | nl

    echo ""
    read -p "Enter backup number to restore (or 'q' to quit): " choice

    if [[ "$choice" == "q" ]]; then
        echo "Cancelled."
        return 1
    fi

    BACKUP_PATH=$(ls -dt "$BACKUP_DIR"/ha-config-* 2>/dev/null | sed -n "${choice}p")

    if [[ -z "$BACKUP_PATH" || ! -d "$BACKUP_PATH" ]]; then
        echo "Invalid backup selection"
        return 1
    fi

    echo "Restoring from: $BACKUP_PATH"
    cp "$BACKUP_PATH"/*.yaml "$LOCAL_CONFIG_DIR/"
    echo "Restored. Run 'push' to upload to HA."
}

pull_config() {
    echo "=== Pulling HA config ==="

    # Backup current local config first
    if ls "$LOCAL_CONFIG_DIR"/*.yaml &>/dev/null; then
        backup_config
    fi

    # Key config files to sync
    CONFIG_FILES="configuration.yaml automations.yaml scripts.yaml scenes.yaml"

    for filename in $CONFIG_FILES; do
        filepath="$HA_CONFIG_PATH/$filename"
        echo "  Downloading $filename..."
        RESULT=$(ssh $PROXMOX_HOST "qm guest exec $VMID --timeout $TIMEOUT -- cat $filepath" 2>/dev/null)
        CONTENT=$(echo "$RESULT" | jq -r '.["out-data"] // empty')
        if [[ -n "$CONTENT" ]]; then
            echo "$CONTENT" > "$LOCAL_CONFIG_DIR/$filename"
        else
            echo "    (file not found or empty)"
        fi
    done

    echo ""
    echo "Config saved to: $LOCAL_CONFIG_DIR/"
    ls -la "$LOCAL_CONFIG_DIR/"
}

push_config() {
    echo "=== Pushing HA config ==="

    for file in "$LOCAL_CONFIG_DIR"/*.yaml; do
        if [[ -f "$file" ]]; then
            filename=$(basename "$file")
            dest="$HA_CONFIG_PATH/$filename"
            echo "  Uploading $filename..."

            # Base64 encode to avoid escaping issues
            CONTENT=$(base64 < "$file")

            ssh $PROXMOX_HOST "qm guest exec $VMID --timeout $TIMEOUT -- bash -c 'echo \"$CONTENT\" | base64 -d > \"$dest\"'" 2>/dev/null
        fi
    done

    echo "Done."
}

check_local() {
    echo "=== Checking local config ==="
    ERRORS=0

    # Check line endings
    for f in "$LOCAL_CONFIG_DIR"/*.yaml; do
        if [[ -f "$f" ]]; then
            if file "$f" | grep -q CRLF; then
                echo "ERROR: CRLF line endings in $(basename $f)"
                echo "  Fix with: sed -i '' 's/\r$//' $f"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    done

    # Check YAML syntax
    if [[ -x "$YAMLLINT" ]]; then
        for f in "$LOCAL_CONFIG_DIR"/*.yaml; do
            if [[ -f "$f" ]]; then
                echo "  Validating $(basename $f)..."
                if ! "$YAMLLINT" -d relaxed "$f" 2>&1; then
                    ERRORS=$((ERRORS + 1))
                fi
            fi
        done
    else
        echo "  (yamllint not installed, using Python YAML check)"
        # Fallback: Python YAML check with HA custom tags
        for f in "$LOCAL_CONFIG_DIR"/*.yaml; do
            if [[ -f "$f" ]]; then
                echo "  Validating $(basename $f)..."
                # HA uses !include, !include_dir_merge_named, !secret - add constructors
                if ! python3 -c "
import yaml

# Handle HA custom tags
def ha_constructor(loader, tag_suffix, node):
    return f'{tag_suffix}: {node.value}'

yaml.add_multi_constructor('!', ha_constructor, Loader=yaml.SafeLoader)
yaml.safe_load(open('$f'))
print('    OK')
" 2>&1; then
                    echo "ERROR: Invalid YAML in $(basename $f)"
                    ERRORS=$((ERRORS + 1))
                fi
            fi
        done
    fi

    if [[ $ERRORS -eq 0 ]]; then
        echo "Local config OK"
        return 0
    else
        echo "Found $ERRORS error(s)"
        return 1
    fi
}

check_remote() {
    echo "=== Checking HA config on server ==="
    RESULT=$(ssh $PROXMOX_HOST "qm guest exec $VMID --timeout $TIMEOUT -- ha core check" 2>/dev/null)
    echo "$RESULT" | jq -r '.["out-data"] // .["err-data"] // .'
}

restart_ha() {
    echo "=== Restarting HA ==="
    ssh $PROXMOX_HOST "qm guest exec $VMID --timeout 30 -- ha core restart" 2>/dev/null || true
    echo "Restart initiated. HA will be back in ~30 seconds."
}

edit_config() {
    ${EDITOR:-vim} "$LOCAL_CONFIG_DIR/configuration.yaml"
}

case "${1:-help}" in
    pull)
        pull_config
        ;;
    push)
        backup_config && check_local && push_config
        ;;
    check)
        check_local
        ;;
    check-remote)
        check_remote
        ;;
    restart)
        restart_ha
        ;;
    edit)
        edit_config
        ;;
    validate)
        backup_config && check_local && push_config && check_remote
        ;;
    backup)
        backup_config
        ;;
    restore)
        restore_config
        ;;
    backups)
        echo "=== Available backups ==="
        ls -dt "$BACKUP_DIR"/ha-config-* 2>/dev/null | head -10 | nl || echo "No backups found"
        ;;
    *)
        echo "Usage: $0 {pull|push|check|check-remote|restart|edit|validate|backup|restore|backups}"
        echo ""
        echo "Commands:"
        echo "  pull         Download config from HA (auto-backup first)"
        echo "  edit         Open config in \$EDITOR"
        echo "  check        Validate local config (YAML, line endings)"
        echo "  push         Backup + validate + upload to HA"
        echo "  check-remote Validate config on HA server"
        echo "  restart      Restart HA core"
        echo "  validate     Full: backup, check, push, check remote"
        echo "  backup       Create backup of local config"
        echo "  backups      List available backups"
        echo "  restore      Restore from a backup"
        echo ""
        echo "Workflow:"
        echo "  1. $0 pull"
        echo "  2. $0 edit"
        echo "  3. $0 validate"
        echo "  4. $0 restart"
        echo ""
        echo "Backups: $BACKUP_DIR"
        ;;
esac
