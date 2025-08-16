#!/bin/bash
# Proxmox Backup Storage Migration Script
# Migrates backup jobs from one storage to another (e.g., local to PBS)
#
# ⚠️  WARNING: THIS SCRIPT IS UNTESTED ⚠️
# This script was created as part of backup infrastructure documentation
# but has not been tested in production. Use at your own risk and always
# test in a non-production environment first with --dry-run option.

set -euo pipefail

# Configuration
SCRIPT_NAME="$(basename "$0")"
LOG_FILE="/var/log/${SCRIPT_NAME%.*}.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    local message="[$(date +'%Y-%m-%d %H:%M:%S')] $1"
    echo -e "${GREEN}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
}

warn() {
    local message="[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1"
    echo -e "${YELLOW}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
}

error() {
    local message="[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1"
    echo -e "${RED}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
    exit 1
}

info() {
    local message="[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1"
    echo -e "${BLUE}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
}

# Usage information
show_usage() {
    cat << EOF
Usage: $SCRIPT_NAME [OPTIONS]

Migrate Proxmox backup jobs from one storage to another.

OPTIONS:
    -f, --from STORAGE      Source storage name (e.g., 'proxmox-backup-server')
    -t, --to STORAGE        Target storage name (e.g., 'homelab-backup')
    -j, --job JOB_ID        Specific backup job ID to migrate (optional)
    -a, --all               Migrate all backup jobs from source storage
    -d, --dry-run          Show what would be done without making changes
    -h, --help             Show this help message

EXAMPLES:
    # Migrate all jobs from old PBS to new PBS storage
    $SCRIPT_NAME --from proxmox-backup-server --to homelab-backup --all

    # Migrate specific backup job
    $SCRIPT_NAME --from local --to homelab-backup --job backup-12345678

    # Dry run to see what would be changed
    $SCRIPT_NAME --from proxmox-backup-server --to homelab-backup --all --dry-run

PREREQUISITES:
    - Run on Proxmox cluster node with pvesh access
    - Target storage must already be configured
    - Backup jobs should be disabled during migration
    - Verify target storage has sufficient space

EOF
}

# Parse command line arguments
parse_args() {
    FROM_STORAGE=""
    TO_STORAGE=""
    JOB_ID=""
    MIGRATE_ALL=false
    DRY_RUN=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--from)
                FROM_STORAGE="$2"
                shift 2
                ;;
            -t|--to)
                TO_STORAGE="$2"
                shift 2
                ;;
            -j|--job)
                JOB_ID="$2"
                shift 2
                ;;
            -a|--all)
                MIGRATE_ALL=true
                shift
                ;;
            -d|--dry-run)
                DRY_RUN=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                ;;
        esac
    done

    # Validation
    if [[ -z "$FROM_STORAGE" ]]; then
        error "Source storage (-f/--from) is required"
    fi

    if [[ -z "$TO_STORAGE" ]]; then
        error "Target storage (-t/--to) is required"
    fi

    if [[ "$MIGRATE_ALL" == false && -z "$JOB_ID" ]]; then
        error "Either --all or --job must be specified"
    fi

    if [[ "$MIGRATE_ALL" == true && -n "$JOB_ID" ]]; then
        error "Cannot use both --all and --job options"
    fi
}

# Verify prerequisites
check_prerequisites() {
    info "Checking prerequisites..."

    # Check if running on Proxmox
    if ! command -v pvesh &> /dev/null; then
        error "pvesh command not found. This script must run on a Proxmox node."
    fi

    # Check if source storage exists
    if ! pvesh get /storage --output-format json | jq -r '.[].storage' | grep -q "^$FROM_STORAGE$"; then
        error "Source storage '$FROM_STORAGE' not found"
    fi

    # Check if target storage exists
    if ! pvesh get /storage --output-format json | jq -r '.[].storage' | grep -q "^$TO_STORAGE$"; then
        error "Target storage '$TO_STORAGE' not found"
    fi

    # Check target storage status
    local target_status
    target_status=$(pvesm status | grep "^$TO_STORAGE " | awk '{print $3}')
    if [[ "$target_status" != "active" ]]; then
        error "Target storage '$TO_STORAGE' is not active (status: $target_status)"
    fi

    info "Prerequisites check passed"
}

# Get backup jobs using source storage
get_backup_jobs() {
    local jobs
    jobs=$(pvesh get /cluster/backup --output-format json | jq -r ".[] | select(.storage == \"$FROM_STORAGE\") | .id")
    
    if [[ -z "$jobs" ]]; then
        warn "No backup jobs found using storage '$FROM_STORAGE'"
        return 1
    fi

    echo "$jobs"
}

# Migrate a single backup job
migrate_job() {
    local job_id="$1"
    
    info "Processing backup job: $job_id"
    
    # Get current job configuration
    local job_config
    job_config=$(pvesh get "/cluster/backup/$job_id" --output-format json)
    
    if [[ -z "$job_config" ]]; then
        error "Failed to get configuration for job $job_id"
    fi

    # Extract current storage
    local current_storage
    current_storage=$(echo "$job_config" | jq -r '.storage')
    
    if [[ "$current_storage" != "$FROM_STORAGE" ]]; then
        warn "Job $job_id uses storage '$current_storage', not '$FROM_STORAGE'. Skipping."
        return 0
    fi

    info "Current job configuration:"
    echo "$job_config" | jq .

    if [[ "$DRY_RUN" == true ]]; then
        info "[DRY RUN] Would update job $job_id to use storage '$TO_STORAGE'"
        return 0
    fi

    # Update the job to use new storage
    info "Updating job $job_id to use storage '$TO_STORAGE'..."
    
    if pvesh set "/cluster/backup/$job_id" --storage "$TO_STORAGE"; then
        log "Successfully migrated job $job_id from '$FROM_STORAGE' to '$TO_STORAGE'"
    else
        error "Failed to migrate job $job_id"
    fi

    # Verify the change
    local new_storage
    new_storage=$(pvesh get "/cluster/backup/$job_id" --output-format json | jq -r '.storage')
    
    if [[ "$new_storage" == "$TO_STORAGE" ]]; then
        log "Verification passed: Job $job_id now uses storage '$TO_STORAGE'"
    else
        error "Verification failed: Job $job_id still uses storage '$new_storage'"
    fi
}

# Main migration function
perform_migration() {
    log "Starting backup storage migration: $FROM_STORAGE → $TO_STORAGE"
    
    if [[ "$DRY_RUN" == true ]]; then
        warn "DRY RUN MODE - No changes will be made"
    fi

    local jobs_to_migrate=()
    
    if [[ "$MIGRATE_ALL" == true ]]; then
        info "Finding all backup jobs using storage '$FROM_STORAGE'..."
        
        # Get jobs using source storage
        if ! jobs_list=$(get_backup_jobs); then
            warn "No jobs to migrate"
            return 0
        fi
        
        readarray -t jobs_to_migrate <<< "$jobs_list"
        
        info "Found ${#jobs_to_migrate[@]} backup jobs to migrate"
    else
        info "Migrating specific job: $JOB_ID"
        jobs_to_migrate=("$JOB_ID")
    fi

    # Process each job
    for job in "${jobs_to_migrate[@]}"; do
        migrate_job "$job"
    done

    if [[ "$DRY_RUN" == false ]]; then
        log "Migration completed successfully!"
        info "Summary:"
        info "  Source storage: $FROM_STORAGE"
        info "  Target storage: $TO_STORAGE"
        info "  Jobs migrated: ${#jobs_to_migrate[@]}"
    else
        info "Dry run completed. Use --dry-run=false to perform actual migration."
    fi
}

# Cleanup function
cleanup() {
    info "Migration script completed"
}

# Main execution
main() {
    trap cleanup EXIT
    
    log "Backup Storage Migration Script Started"
    
    parse_args "$@"
    check_prerequisites
    perform_migration
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi