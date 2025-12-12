#!/bin/bash
#
# 00-install-guest-agent.sh
#
# Install qemu-guest-agent on K3s VM 105 via privileged pod
#

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NODE="k3s-vm-pumped-piglet-gpu"
POD_NAME="install-guest-agent"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Install QEMU Guest Agent on $NODE"
echo "========================================="
echo ""

# Clean up any existing pod
echo "Step 1: Cleaning up any existing pod..."
KUBECONFIG="$KUBECONFIG" kubectl delete pod $POD_NAME --ignore-not-found --wait=false 2>/dev/null || true
sleep 2
echo ""

# Create privileged pod with host access
echo "Step 2: Creating privileged pod..."
KUBECONFIG="$KUBECONFIG" kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $POD_NAME
spec:
  nodeName: $NODE
  hostPID: true
  hostNetwork: true
  containers:
  - name: nsenter
    image: ubuntu:24.04
    command: ["sleep", "3600"]
    securityContext:
      privileged: true
    volumeMounts:
    - name: host
      mountPath: /host
  volumes:
  - name: host
    hostPath:
      path: /
  restartPolicy: Never
EOF
echo ""

# Wait for pod to be ready
echo "Step 3: Waiting for pod to be ready..."
KUBECONFIG="$KUBECONFIG" kubectl wait --for=condition=Ready pod/$POD_NAME --timeout=120s
echo -e "${GREEN}Pod ready${NC}"
echo ""

# Install qemu-guest-agent
echo "Step 4: Installing qemu-guest-agent..."
KUBECONFIG="$KUBECONFIG" kubectl exec $POD_NAME -- nsenter -t 1 -m -u -i -n -- apt-get update -qq
KUBECONFIG="$KUBECONFIG" kubectl exec $POD_NAME -- nsenter -t 1 -m -u -i -n -- apt-get install -y -qq qemu-guest-agent
echo -e "${GREEN}Package installed${NC}"
echo ""

# Enable and start the service
echo "Step 5: Enabling and starting qemu-guest-agent..."
KUBECONFIG="$KUBECONFIG" kubectl exec $POD_NAME -- nsenter -t 1 -m -u -i -n -- systemctl enable qemu-guest-agent
KUBECONFIG="$KUBECONFIG" kubectl exec $POD_NAME -- nsenter -t 1 -m -u -i -n -- systemctl start qemu-guest-agent
echo -e "${GREEN}Service started${NC}"
echo ""

# Verify
echo "Step 6: Verifying..."
KUBECONFIG="$KUBECONFIG" kubectl exec $POD_NAME -- nsenter -t 1 -m -u -i -n -- systemctl status qemu-guest-agent --no-pager | head -10
echo ""

# Clean up pod
echo "Step 7: Cleaning up pod..."
KUBECONFIG="$KUBECONFIG" kubectl delete pod $POD_NAME --wait=false
echo ""

echo "========================================="
echo -e "${GREEN}QEMU Guest Agent installed!${NC}"
echo "========================================="
echo ""
echo "Test with: ssh root@pumped-piglet.maas 'qm agent 105 ping'"
