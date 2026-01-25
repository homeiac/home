#!/bin/bash
# Backup Frigate face training images via API
# Runs on pumped-piglet - no kubectl needed
# Deploy to: /root/scripts/backup-frigate-faces.sh
# Cron: 0 3 * * * /root/scripts/backup-frigate-faces.sh >> /var/log/frigate-face-backup.log 2>&1

set -e

FRIGATE_URL="https://frigate.app.home.panderosystems.com"
BACKUP_DIR="/local-3TB-backup/frigate-backups"
DATE=$(date +%Y%m%d)
BACKUP_SUBDIR="${BACKUP_DIR}/faces-${DATE}"

echo "$(date): Starting Frigate face backup via API..."

# Create backup directory
mkdir -p "$BACKUP_SUBDIR"

# Get list of faces
FACES_JSON=$(curl -sk "${FRIGATE_URL}/api/faces")

# Parse and download each face
for FACE_NAME in $(echo "$FACES_JSON" | jq -r 'keys[]'); do
    # Skip 'train' folder
    [ "$FACE_NAME" = "train" ] && continue

    echo "Backing up face: $FACE_NAME"
    mkdir -p "${BACKUP_SUBDIR}/${FACE_NAME}"

    # Download each image
    for IMG in $(echo "$FACES_JSON" | jq -r ".\"${FACE_NAME}\"[]"); do
        curl -sk "${FRIGATE_URL}/clips/faces/${FACE_NAME}/${IMG}" \
            -o "${BACKUP_SUBDIR}/${FACE_NAME}/${IMG}"
    done

    COUNT=$(ls -1 "${BACKUP_SUBDIR}/${FACE_NAME}" | wc -l)
    echo "  Downloaded $COUNT images"
done

# Create tarball
cd "$BACKUP_DIR"
tar czf "frigate-faces-${DATE}.tar.gz" "faces-${DATE}"
rm -rf "faces-${DATE}"

echo "$(date): Created backup: frigate-faces-${DATE}.tar.gz ($(ls -lh "frigate-faces-${DATE}.tar.gz" | awk '{print $5}'))"

# Keep only last 7 backups
ls -t frigate-faces-*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm -f

echo "$(date): Backup complete. Current backups:"
ls -lh "$BACKUP_DIR"/frigate-faces-*.tar.gz
