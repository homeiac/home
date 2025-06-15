#!/usr/bin/env bash
set -euo pipefail

NS_METALLB="metallb-system"
TMP_SVC_NS="default"             # where we create the throw-away Service
TMP_SVC_NAME="metallb-test"
TEST_PORT=80                     # can be any port that exists on a pod
EXPECT_RANGE="192.168.4.5"       # first part of the pool → used for a quick sanity grep

banner() { printf "\n\033[1;34m▶ %s\033[0m\n" "$*"; }

### 0 · pre-flight -----------------------------------------------------------
banner "Checking kubectl connectivity"
kubectl version --client >/dev/null 2>&1

### 1 · pods ­and speakers ----------------------------------------------------
banner "MetalLB pods"
kubectl get pods -n "$NS_METALLB" -o wide

### 2 · CRDs exist ------------------------------------------------------------
banner "IPAddressPools & L2Advertisements"
kubectl get ipaddresspools.metallb.io,l2advertisements.metallb.io || true

### 3 · controller saw the pool ----------------------------------------------
banner "Controller log   (grep for pool load)"
kubectl -n "$NS_METALLB" logs deploy/controller --tail=50 | \
  grep -E "pool|IP allocation" || true

### 4 · create disposable LB Service -----------------------------------------
banner "Creating throw-away LoadBalancer Service"
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: $TMP_SVC_NAME
  namespace: $TMP_SVC_NS
spec:
  selector:
    kubernetes.io/name: kube-dns      # any pod selector that exists
  type: LoadBalancer
  ports:
    - port: $TEST_PORT
      targetPort: 53                  # kube-dns has 53/UDP+TCP
EOF

banner "Waiting for EXTERNAL-IP..."
for i in {1..30}; do
  EXT_IP=$(kubectl get svc "$TMP_SVC_NAME" -n "$TMP_SVC_NS" \
           -o jsonpath='{.status.loadBalancer.ingress[0].ip}' || true)
  if [[ -n "$EXT_IP" ]]; then break; fi
  sleep 1
done

if [[ -z "${EXT_IP:-}" ]]; then
  echo "❌  Service never received an EXTERNAL-IP (check MetalLB controller logs)."
  exit 1
fi

echo "✓  External IP assigned: $EXT_IP"

### 5 · connectivity test -----------------------------------------------------
banner "curl test (expect 404 or NO ERROR)"
curl -m 3 -s "http://$EXT_IP:$TEST_PORT" || true

### 6 · ARP entry (only works on same LAN) ------------------------------------
banner "ARP / neighbor entry on this host"
if command -v ip >/dev/null 2>&1; then               # modern Linux
  ip -4 neigh show "${EXT_IP}" | head -n1 || true
elif command -v arp >/dev/null 2>&1; then            # macOS + *BSD
  arp -n "${EXT_IP}" || true
else
  echo "⚠️  Neither 'ip' nor 'arp' found; skipping neighbour lookup"
fi

### 7 · cleanup ---------------------------------------------------------------
banner "Cleaning up"
kubectl delete svc "$TMP_SVC_NAME" -n "$TMP_SVC_NS"

echo -e "\n\033[1;32mAll checks finished!\033[0m"

