#!/bin/bash
# Build patched crucible-nbd-server with --address support on proper-raptor
#
# This patches the NBD server to support a custom listen address, required
# for per-VM volumes where each VM needs its own NBD port.
#
# After building, the binary is copied to /home/ubuntu/crucible-nbd-server
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRUCIBLE_IP="192.168.4.189"
CRUCIBLE_HOST="ubuntu@${CRUCIBLE_IP}"

echo "=== Building Patched crucible-nbd-server ==="
echo ""

# Check SSH access
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$CRUCIBLE_HOST" "echo 'SSH OK'" 2>/dev/null; then
    echo "ERROR: Cannot SSH to $CRUCIBLE_HOST"
    exit 1
fi

# Check if Crucible source exists
if ! ssh "$CRUCIBLE_HOST" "test -d /home/ubuntu/crucible"; then
    echo "ERROR: Crucible source not found at /home/ubuntu/crucible"
    echo "Clone it first: git clone https://github.com/oxidecomputer/crucible"
    exit 1
fi

# Apply the patch
echo "Applying --address patch to nbd_server/src/main.rs..."

ssh "$CRUCIBLE_HOST" "cat > /tmp/patch-nbd-server.sh" << 'REMOTE_SCRIPT'
#!/bin/bash
set -e

cd /home/ubuntu/crucible

# Check if already patched
if grep -q '"127.0.0.1:10809"' nbd_server/src/main.rs && \
   grep -q 'opt.address' nbd_server/src/main.rs; then
    echo "Already patched (opt.address found)"
else
    echo "Applying patch..."

    # Backup original
    cp nbd_server/src/main.rs nbd_server/src/main.rs.bak

    # Add --address argument to Opt struct (after target)
    # Find the target line and add address after it
    sed -i '/target: Vec<SocketAddr>,/a\
\
    /// Address to bind the NBD server (default: 127.0.0.1:10809)\
    #[clap(short = '\''a'\'', long, default_value = "127.0.0.1:10809")]\
    address: String,' nbd_server/src/main.rs

    # Replace hardcoded bind address with opt.address
    # The original line is: let listener = TcpListener::bind("127.0.0.1:10809").await?;
    sed -i 's/TcpListener::bind("127.0.0.1:10809")/TcpListener::bind(\&opt.address)/' nbd_server/src/main.rs

    echo "Patch applied"
fi

# Verify changes
echo ""
echo "Verifying patch..."
if grep -q 'address: String' nbd_server/src/main.rs && \
   grep -q 'bind(&opt.address)' nbd_server/src/main.rs; then
    echo "Patch verified OK"
else
    echo "ERROR: Patch verification failed"
    echo "Restoring backup..."
    mv nbd_server/src/main.rs.bak nbd_server/src/main.rs
    exit 1
fi
REMOTE_SCRIPT

ssh "$CRUCIBLE_HOST" "chmod +x /tmp/patch-nbd-server.sh && /tmp/patch-nbd-server.sh"

# Build
echo ""
echo "Building crucible-nbd-server (this may take a while)..."
ssh "$CRUCIBLE_HOST" "cd /home/ubuntu/crucible && cargo build --release -p nbd_server 2>&1" | tail -20

# Copy to home directory
echo ""
echo "Copying binary to /home/ubuntu/crucible-nbd-server..."
ssh "$CRUCIBLE_HOST" "cp /home/ubuntu/crucible/target/release/crucible-nbd-server /home/ubuntu/"

# Verify
echo ""
echo "Verifying build..."
VERSION=$(ssh "$CRUCIBLE_HOST" "/home/ubuntu/crucible-nbd-server --help 2>&1 | head -5" || true)
echo "$VERSION"

if echo "$VERSION" | grep -q "address"; then
    echo ""
    echo "=== Build Successful ==="
    echo "Binary at: /home/ubuntu/crucible-nbd-server"
    echo ""
    echo "New flag: --address <IP:PORT>  (default: 127.0.0.1:10809)"
    echo ""
    echo "Next step: Run deploy-ha-storage.sh to deploy to Proxmox hosts"
else
    echo ""
    echo "WARNING: --address flag not found in help output"
    echo "Build may have failed or patch not applied correctly"
fi
