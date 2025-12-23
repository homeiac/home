#!/bin/bash
# Configure Proxmox OIDC realm for Entra ID
# Run this ON the Proxmox host or via SSH
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration - set these or pass as arguments
PROXMOX_HOST="${PROXMOX_HOST:-}"
TENANT_ID="${TENANT_ID:-}"
CLIENT_ID="${CLIENT_ID:-}"
CLIENT_SECRET="${CLIENT_SECRET:-}"
REALM_NAME="${REALM_NAME:-entra}"

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Configure Proxmox OIDC realm for Microsoft Entra ID.

Options:
  --host HOST         Proxmox host (or run locally on Proxmox)
  --tenant-id ID      Azure Tenant ID
  --client-id ID      Azure Application (Client) ID
  --client-secret S   Azure Client Secret VALUE
  --realm NAME        Proxmox realm name (default: entra)
  --verify-only       Just verify existing config, don't modify
  -h, --help          Show this help

Example:
  $0 --host proxmox.office.local \\
     --tenant-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \\
     --client-id yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \\
     --client-secret "your-secret-value"

EOF
    exit 0
}

VERIFY_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --host) PROXMOX_HOST="$2"; shift 2 ;;
        --tenant-id) TENANT_ID="$2"; shift 2 ;;
        --client-id) CLIENT_ID="$2"; shift 2 ;;
        --client-secret) CLIENT_SECRET="$2"; shift 2 ;;
        --realm) REALM_NAME="$2"; shift 2 ;;
        --verify-only) VERIFY_ONLY=true; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

# Check if we're running on Proxmox or remotely
run_cmd() {
    if [[ -n "$PROXMOX_HOST" ]]; then
        ssh "root@${PROXMOX_HOST}" "$@"
    else
        eval "$@"
    fi
}

# Verify Proxmox access
echo "=== Checking Proxmox Access ==="
if ! run_cmd "pvesh get /version" &>/dev/null; then
    echo "ERROR: Cannot access Proxmox API"
    echo "Run on Proxmox host or specify --host"
    exit 1
fi

PROXMOX_VERSION=$(run_cmd "pvesh get /version --output-format json" | jq -r '.version')
echo "Proxmox VE version: ${PROXMOX_VERSION}"

if $VERIFY_ONLY; then
    echo ""
    echo "=== Existing Realms ==="
    run_cmd "pvesh get /access/domains --output-format json" | jq -r '.[] | "\(.realm): \(.type) - \(.comment // "no comment")"'

    echo ""
    echo "=== Checking for Entra realm ==="
    if run_cmd "pvesh get /access/domains/${REALM_NAME}" &>/dev/null; then
        echo "Realm '${REALM_NAME}' exists:"
        run_cmd "pvesh get /access/domains/${REALM_NAME} --output-format json" | jq '.'
    else
        echo "Realm '${REALM_NAME}' not found"
    fi
    exit 0
fi

# Validate required parameters
if [[ -z "$TENANT_ID" || -z "$CLIENT_ID" || -z "$CLIENT_SECRET" ]]; then
    echo "ERROR: Missing required parameters"
    echo ""
    echo "Required: --tenant-id, --client-id, --client-secret"
    echo ""
    usage
fi

ISSUER_URL="https://login.microsoftonline.com/${TENANT_ID}/v2.0"

echo ""
echo "=== Configuration ==="
echo "Realm:      ${REALM_NAME}"
echo "Issuer URL: ${ISSUER_URL}"
echo "Client ID:  ${CLIENT_ID}"
echo "Secret:     ****${CLIENT_SECRET: -4}"
echo ""

# Check if realm already exists
if run_cmd "pvesh get /access/domains/${REALM_NAME}" &>/dev/null; then
    echo "Realm '${REALM_NAME}' already exists. Updating..."
    ACTION="set"
else
    echo "Creating realm '${REALM_NAME}'..."
    ACTION="create"
fi

# Create/update the realm
# Note: pvesh escapes are tricky, using pveum instead
if [[ "$ACTION" == "create" ]]; then
    run_cmd "pveum realm add ${REALM_NAME} --type openid \
        --issuer-url '${ISSUER_URL}' \
        --client-id '${CLIENT_ID}' \
        --client-key '${CLIENT_SECRET}' \
        --username-claim 'email' \
        --autocreate 1 \
        --comment 'Microsoft Entra ID'"
else
    run_cmd "pveum realm modify ${REALM_NAME} \
        --issuer-url '${ISSUER_URL}' \
        --client-id '${CLIENT_ID}' \
        --client-key '${CLIENT_SECRET}' \
        --username-claim 'email' \
        --autocreate 1 \
        --comment 'Microsoft Entra ID'"
fi

echo ""
echo "=== Realm Configured ==="
run_cmd "pvesh get /access/domains/${REALM_NAME} --output-format json" | jq '.'

echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Open Proxmox UI: https://<proxmox-ip>:8006"
echo "2. On login page, select realm: ${REALM_NAME}"
echo "3. Click 'Login' to redirect to Microsoft"
echo "4. After first login, assign permissions:"
echo "   pveum user modify <email>@${REALM_NAME} -group admin"
echo ""
echo "Note: First login creates user with NO permissions."
echo "You must manually assign groups/roles."
