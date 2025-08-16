#!/bin/bash
# Production Coral TPU Initialization Script
# This script handles Coral TPU initialization and Frigate LXC configuration

# Source the mock script functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/mock-coral-init.sh"

# Override for production if needed
DRY_RUN=${DRY_RUN:-true}  # DEFAULT TO DRY RUN FOR SAFETY

# Additional production-specific functions
verify_prerequisites() {
    log INFO "Verifying prerequisites..."
    
    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        log ERROR "This script must be run as root"
        return 1
    fi
    
    # Check if Proxmox tools are available
    if ! command -v pct &> /dev/null; then
        log ERROR "pct command not found. Are you running on Proxmox?"
        return 1
    fi
    
    # Check if Python is available
    if ! command -v ${PYTHON_CMD} &> /dev/null; then
        log ERROR "${PYTHON_CMD} not found"
        return 1
    fi
    
    # Check if coral init files exist
    if [ ! -d "${CORAL_INIT_DIR}/coral" ]; then
        log WARN "Coral directory not found at ${CORAL_INIT_DIR}/coral"
        log INFO "You may need to clone the repository first:"
        log INFO "  cd ${CORAL_INIT_DIR}"
        log INFO "  git clone https://github.com/google-coral/pycoral.git coral/pycoral"
        log INFO "  git clone https://github.com/google-coral/test_data.git test_data"
        return 1
    fi
    
    log INFO "All prerequisites verified"
    return 0
}

# Production main wrapper
production_main() {
    # Safety check
    if [ "$DRY_RUN" = false ]; then
        log WARN "Running in PRODUCTION mode - changes will be made!"
        log INFO "Waiting 5 seconds... Press Ctrl+C to abort"
        sleep 5
    else
        log INFO "Running in DRY-RUN mode - no changes will be made"
    fi
    
    # Verify prerequisites
    if ! verify_prerequisites; then
        log ERROR "Prerequisites check failed"
        exit 1
    fi
    
    # Call the main function from mock script
    main "$@"
}

# Run production main
production_main "$@"