#!/bin/bash
# Backup service configs from VMs/LXCs to Crucible storage
#
# Usage: ./backup-services-to-crucible.sh [SERVICE]
#
# Services backed up:
# - HAOS (Home Assistant OS) - configuration.yaml, automations, scripts, secrets
# - Frigate - config.yml, model files
# - Ollama - model list, Modelfiles
#
# Backups stored in /mnt/crucible-storage/services/ on pve
set -e

BACKUP_HOST="pve"
BACKUP_BASE="/mnt/crucible-storage/services"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Service definitions
SERVICE="$1"

log() {
    echo "[$(date '+%H:%M:%S')] $*"
}

# Check Crucible mount
check_mount() {
    if ! ssh "root@$BACKUP_HOST" "mountpoint -q /mnt/crucible-storage" 2>/dev/null; then
        echo "ERROR: Crucible not mounted on $BACKUP_HOST" >&2
        exit 1
    fi
}

# Backup Home Assistant (HAOS on chief-horse VMID 116)
backup_haos() {
    log "Backing up Home Assistant..."

    local dest_dir="$BACKUP_BASE/haos/$TIMESTAMP"
    local ha_config="/mnt/data/supervisor/homeassistant"

    # Use existing script pattern - qm guest exec with correct HAOS path
    ssh "root@chief-horse.maas" "
        mkdir -p '$dest_dir'

        # HAOS config lives at /mnt/data/supervisor/homeassistant/
        echo 'Fetching configuration.yaml...'
        qm guest exec 116 -- cat '$ha_config/configuration.yaml' 2>/dev/null | jq -r '.[\"out-data\"] // empty' > '$dest_dir/configuration.yaml'

        echo 'Fetching automations.yaml...'
        qm guest exec 116 -- cat '$ha_config/automations.yaml' 2>/dev/null | jq -r '.[\"out-data\"] // empty' > '$dest_dir/automations.yaml'

        echo 'Fetching scripts.yaml...'
        qm guest exec 116 -- cat '$ha_config/scripts.yaml' 2>/dev/null | jq -r '.[\"out-data\"] // empty' > '$dest_dir/scripts.yaml'

        echo 'Fetching scenes.yaml...'
        qm guest exec 116 -- cat '$ha_config/scenes.yaml' 2>/dev/null | jq -r '.[\"out-data\"] // empty' > '$dest_dir/scenes.yaml'

        echo 'Fetching secrets.yaml...'
        qm guest exec 116 -- cat '$ha_config/secrets.yaml' 2>/dev/null | jq -r '.[\"out-data\"] // empty' > '$dest_dir/secrets.yaml'

        echo 'Fetching known_devices.yaml...'
        qm guest exec 116 -- cat '$ha_config/known_devices.yaml' 2>/dev/null | jq -r '.[\"out-data\"] // empty' > '$dest_dir/known_devices.yaml'

        echo 'Fetching customize.yaml...'
        qm guest exec 116 -- cat '$ha_config/customize.yaml' 2>/dev/null | jq -r '.[\"out-data\"] // empty' > '$dest_dir/customize.yaml'

        # List integrations/config entries
        echo 'Listing .storage config entries...'
        qm guest exec 116 -- ls -la '$ha_config/.storage/' 2>/dev/null | jq -r '.[\"out-data\"] // empty' > '$dest_dir/storage-list.txt'

        # Core config entries (integrations)
        echo 'Fetching core.config_entries...'
        qm guest exec 116 -- cat '$ha_config/.storage/core.config_entries' 2>/dev/null | jq -r '.[\"out-data\"] // empty' > '$dest_dir/core.config_entries.json'

        # Remove empty files
        find '$dest_dir' -type f -empty -delete

        chmod 600 '$dest_dir'/* 2>/dev/null || true

        echo ''
        echo 'HAOS backup saved to: $dest_dir'
        ls -la '$dest_dir'
    "

    # Copy to pve Crucible storage
    ssh "root@$BACKUP_HOST" "mkdir -p '$dest_dir'"
    ssh "root@chief-horse.maas" "cat '$dest_dir'/*" | ssh "root@$BACKUP_HOST" "cat > /dev/null" 2>/dev/null || true
    # Actually copy the files
    for f in configuration.yaml automations.yaml scripts.yaml scenes.yaml secrets.yaml core.config_entries.json; do
        scp "root@chief-horse.maas:$dest_dir/$f" "root@$BACKUP_HOST:$dest_dir/" 2>/dev/null || true
    done
}

# Backup Frigate (K8s pod or LXC)
backup_frigate() {
    log "Backing up Frigate..."

    local dest_dir="$BACKUP_BASE/frigate/$TIMESTAMP"

    # Check if Frigate runs in K8s (still-fawn) or LXC (fun-bedbug)
    # Try K8s first
    if ssh "root@still-fawn.maas" "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml && kubectl get pod -n frigate -l app.kubernetes.io/name=frigate -o name 2>/dev/null" | grep -q pod; then
        log "Frigate found in K8s on still-fawn"
        ssh "root@still-fawn.maas" "
            export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
            POD=\$(kubectl get pod -n frigate -l app.kubernetes.io/name=frigate -o jsonpath='{.items[0].metadata.name}')

            mkdir -p '$dest_dir'

            echo 'Fetching config.yml...'
            kubectl exec -n frigate \$POD -- cat /config/config.yml > /tmp/frigate-config.yml 2>/dev/null || true

            echo 'Listing models...'
            kubectl exec -n frigate \$POD -- ls -la /config/model_cache/ > /tmp/frigate-models.txt 2>/dev/null || true
        "
        scp "root@still-fawn.maas:/tmp/frigate-config.yml" "/tmp/"
        scp "root@still-fawn.maas:/tmp/frigate-models.txt" "/tmp/"
        scp "/tmp/frigate-config.yml" "root@$BACKUP_HOST:$dest_dir/"
        scp "/tmp/frigate-models.txt" "root@$BACKUP_HOST:$dest_dir/"
    else
        log "Checking LXC on fun-bedbug..."
        ssh "root@fun-bedbug.maas" "
            mkdir -p '$dest_dir'

            # LXC 113 is Frigate
            if pct status 113 | grep -q running; then
                echo 'Fetching config.yml from LXC 113...'
                pct exec 113 -- cat /config/config.yml > '$dest_dir/config.yml' 2>/dev/null || true

                echo 'Listing models...'
                pct exec 113 -- ls -la /config/model_cache/ > '$dest_dir/models.txt' 2>/dev/null || true
            else
                echo 'Frigate LXC not running'
            fi
        "
    fi

    ssh "root@$BACKUP_HOST" "
        if [[ -d '$dest_dir' ]]; then
            chmod 600 '$dest_dir'/* 2>/dev/null || true
            echo ''
            echo 'Frigate backup saved to: $dest_dir'
            ls -la '$dest_dir' 2>/dev/null || echo '(empty)'
        fi
    "
}

# Backup Ollama models info (K8s on pumped-piglet)
backup_ollama() {
    log "Backing up Ollama model info..."

    local dest_dir="$BACKUP_BASE/ollama/$TIMESTAMP"

    ssh "root@$BACKUP_HOST" "mkdir -p '$dest_dir'"

    # Ollama runs on pumped-piglet K8s with GPU
    ssh "root@pumped-piglet.maas" "
        export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

        echo 'Getting Ollama pod...'
        POD=\$(kubectl get pod -n ollama -l app.kubernetes.io/name=ollama -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

        if [[ -n \"\$POD\" ]]; then
            echo 'Listing models...'
            kubectl exec -n ollama \$POD -- ollama list > /tmp/ollama-models.txt 2>/dev/null || true

            echo 'Getting model details...'
            for model in \$(kubectl exec -n ollama \$POD -- ollama list 2>/dev/null | tail -n +2 | awk '{print \$1}'); do
                echo \"=== \$model ===\" >> /tmp/ollama-model-details.txt
                kubectl exec -n ollama \$POD -- ollama show \$model >> /tmp/ollama-model-details.txt 2>/dev/null || true
                echo '' >> /tmp/ollama-model-details.txt
            done
        else
            echo 'Ollama pod not found'
        fi
    " 2>/dev/null || true

    scp "root@pumped-piglet.maas:/tmp/ollama-models.txt" "root@$BACKUP_HOST:$dest_dir/" 2>/dev/null || true
    scp "root@pumped-piglet.maas:/tmp/ollama-model-details.txt" "root@$BACKUP_HOST:$dest_dir/" 2>/dev/null || true

    ssh "root@$BACKUP_HOST" "
        if [[ -d '$dest_dir' ]]; then
            echo ''
            echo 'Ollama backup saved to: $dest_dir'
            ls -la '$dest_dir' 2>/dev/null || echo '(empty)'
        fi
    "
}

# Cleanup old backups (keep last 5 per service)
cleanup_old() {
    local service="$1"
    ssh "root@$BACKUP_HOST" "
        if [[ -d '$BACKUP_BASE/$service' ]]; then
            ls -dt $BACKUP_BASE/$service/*/ 2>/dev/null | tail -n +6 | xargs rm -rf 2>/dev/null || true
        fi
    "
}

# Main
log "Starting service backup to Crucible storage"
check_mount

case "$SERVICE" in
    haos|homeassistant|ha)
        backup_haos
        cleanup_old haos
        ;;
    frigate)
        backup_frigate
        cleanup_old frigate
        ;;
    ollama)
        backup_ollama
        cleanup_old ollama
        ;;
    ""|all)
        backup_haos
        cleanup_old haos
        backup_frigate
        cleanup_old frigate
        backup_ollama
        cleanup_old ollama
        ;;
    *)
        echo "Unknown service: $SERVICE" >&2
        echo "Usage: $0 [haos|frigate|ollama|all]" >&2
        exit 1
        ;;
esac

echo ""
log "Done"
