#!/bin/bash
# Setup SSH keys for passwordless access to Proxmox hosts
#
# Usage: ./setup-ssh-keys.sh <password>
#
# This uses Python's pty module to handle password prompts since
# sshpass is not available in the claudecodeui container.

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <password>"
    echo "       Password for root user on Proxmox hosts"
    exit 1
fi

PASSWORD="$1"
SSH_KEY_PRIVATE="$HOME/.ssh/id_ed25519"
SSH_KEY_PUBLIC="$HOME/.ssh/id_ed25519.pub"
HOSTS="pumped-piglet.maas fun-bedbug.maas chief-horse.maas still-fawn.maas"

# Ensure .ssh directory exists
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

# Check if SSH key exists, generate if not
if [ ! -f "$SSH_KEY_PRIVATE" ]; then
    echo "Generating SSH key..."
    ssh-keygen -t ed25519 -f "$SSH_KEY_PRIVATE" -N "" -C "claude@claudecodeui"
fi

# Add host keys to known_hosts
echo "Adding host keys to known_hosts..."
for host in $HOSTS; do
    ssh-keyscan -H "$host" >> "$HOME/.ssh/known_hosts" 2>/dev/null || true
done

# Read the public key
PUBKEY=$(cat "$SSH_KEY_PUBLIC")

echo ""
echo "Copying SSH key to hosts..."

for host in $HOSTS; do
    echo -n "  $host: "

    # Use Python with pty to handle password prompt
    python3 << PYEOF
import pty
import os
import select
import time

host = "$host"
password = "$PASSWORD"
pubkey = "$PUBKEY"

# Command to append key to authorized_keys
cmd = f"ssh -o StrictHostKeyChecking=accept-new root@{host} \"echo '{pubkey}' >> ~/.ssh/authorized_keys\""

pid, fd = pty.fork()

if pid == 0:
    # Child process - exec ssh
    os.execvp('/bin/bash', ['/bin/bash', '-c', cmd])
else:
    # Parent process - handle password prompt
    output = b''
    password_sent = False
    success = False

    try:
        for _ in range(100):  # Max 10 seconds
            r, w, e = select.select([fd], [], [], 0.1)
            if fd in r:
                try:
                    data = os.read(fd, 1024)
                    if not data:
                        break
                    output += data
                    if b'password:' in output.lower() and not password_sent:
                        time.sleep(0.2)
                        os.write(fd, (password + '\n').encode())
                        password_sent = True
                except OSError:
                    break

        _, status = os.waitpid(pid, 0)
        success = (os.WEXITSTATUS(status) == 0)
    except Exception as e:
        pass

    print("OK" if success else "FAILED")
PYEOF

done

echo ""
echo "Testing SSH connections..."
ALL_OK=true
for host in $HOSTS; do
    if ssh -o BatchMode=yes -o ConnectTimeout=5 root@"$host" "echo ok" >/dev/null 2>&1; then
        echo "  $host: OK"
    else
        echo "  $host: FAILED"
        ALL_OK=false
    fi
done

echo ""
if [ "$ALL_OK" = true ]; then
    echo "All hosts configured successfully!"
else
    echo "Some hosts failed. You may need to run this script again."
fi
