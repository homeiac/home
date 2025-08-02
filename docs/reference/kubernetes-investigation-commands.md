# Kubernetes Investigation Commands

*Safe read-only commands for investigating K8s cluster state*

## Service Discovery
```bash
# Check if service exists across all namespaces
kubectl get deployments,services,pods -A | grep <service-name>

# List all running services by type
kubectl get services -A --field-selector spec.type=LoadBalancer
kubectl get services -A --field-selector spec.type=ClusterIP

# Check for StatefulSets and DaemonSets
kubectl get statefulsets,daemonsets -A | grep <service-name>
```

## Resource Investigation
```bash
# Storage resources
kubectl get pvc,pv -A
kubectl get storageclass
kubectl describe pv | grep -A10 -B5 <volume-name>

# ConfigMaps and Secrets (names only)
kubectl get configmaps,secrets -A | grep <service-name>

# Resource usage
kubectl top nodes
kubectl top pods -A --sort-by=cpu
kubectl top pods -A --sort-by=memory
```

## Node and Hardware
```bash
# Node capabilities and labels
kubectl get nodes -o wide
kubectl describe nodes | grep -A5 -B5 gpu
kubectl get nodes --show-labels

# Resource allocation per node
kubectl describe nodes | grep -A20 "Allocated resources"
```

## Network Investigation
```bash
# Ingress and network policies
kubectl get ingress -A
kubectl get networkpolicies -A

# Service endpoints
kubectl get endpoints -A | grep <service-name>
```

## Logs and Events (Recent)
```bash
# Recent events across cluster
kubectl get events -A --sort-by=.metadata.creationTimestamp

# Pod logs (last 50 lines)
kubectl logs deployment/<deployment-name> -n <namespace> --tail=50

# Previous container logs if crashed
kubectl logs deployment/<deployment-name> -n <namespace> --previous
```

## Investigation Checklist

### For New Service Integration:
- [ ] Check if already deployed: `kubectl get all -A | grep <service>`  
- [ ] Verify storage requirements: `kubectl get storageclass`
- [ ] Check node resources: `kubectl top nodes`
- [ ] Confirm GPU availability: `kubectl describe nodes | grep gpu`

### For Troubleshooting:
- [ ] Pod status: `kubectl get pods -A | grep <service>`
- [ ] Recent events: `kubectl get events -A --sort-by=.metadata.creationTimestamp | tail -20`
- [ ] Resource consumption: `kubectl top pods -A | grep <service>`
- [ ] Service accessibility: `kubectl get services -A | grep <service>`

All commands are read-only and safe to run during investigation.