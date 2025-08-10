# Ollama Troubleshooting Runbook

## Overview

This runbook provides step-by-step procedures for diagnosing and resolving common Ollama issues in the homelab Kubernetes environment.

## Common Issues

### 1. High CPU Usage When Model Loaded

**Symptoms:**
- CPU usage >100% when model is idle
- High system load average
- Ollama processes consuming excessive CPU cycles
- Slow system response

**Diagnosis Steps:**

1. **Check CPU usage patterns:**
   ```bash
   # Monitor CPU usage
   ssh root@still-fawn.maas 'top -b -n 3 | grep -A 15 "load average"'
   
   # Check Ollama processes specifically
   ssh root@still-fawn.maas 'ps aux | grep ollama | grep -v grep'
   ```

2. **Verify GPU utilization:**
   ```bash
   # Check GPU memory and processes
   ssh root@still-fawn.maas 'nvidia-smi'
   
   # Verify Ollama is using GPU
   ssh root@still-fawn.maas 'nvidia-smi | grep ollama'
   ```

3. **Check loaded models:**
   ```bash
   # List currently loaded models
   curl -s http://ollama.homelab:11434/api/ps
   
   # Check available models
   curl -s http://ollama.homelab:11434/api/tags
   ```

**Resolution Steps:**

1. **Apply GPU optimization configuration:**
   ```bash
   # Edit Ollama deployment
   kubectl edit deployment ollama-gpu -n ollama
   
   # Add these environment variables:
   env:
     - name: OLLAMA_GPU_OVERHEAD
       value: "1073741824"  # 1GB
     - name: OLLAMA_NUM_PARALLEL
       value: "1"
     - name: OLLAMA_MAX_LOADED_MODELS
       value: "1"
     - name: OLLAMA_FLASH_ATTENTION
       value: "true"
     - name: CUDA_VISIBLE_DEVICES
       value: "0"
   ```

2. **Restart Ollama pod:**
   ```bash
   kubectl delete pod -n ollama -l app=ollama-gpu
   kubectl rollout status deployment/ollama-gpu -n ollama
   ```

3. **Verify resolution:**
   ```bash
   # Check CPU usage is normalized
   ssh root@still-fawn.maas 'top -b -n 1 | head -10'
   
   # Test model loading
   curl -X POST http://ollama.homelab:11434/api/generate \
     -H "Content-Type: application/json" \
     -d '{"model":"gemma3:4b","prompt":"test","stream":false}'
   ```

**Expected Results:**
- CPU usage <20% with loaded model
- GPU memory usage visible in nvidia-smi
- Model responses within 10 seconds

### 2. Model Loading Failures

**Symptoms:**
- "model not found" errors
- Pull operations timing out
- Incomplete model downloads

**Diagnosis Steps:**

1. **Check network connectivity:**
   ```bash
   # Test Ollama registry access
   curl -s https://registry.ollama.ai/v2/
   
   # Check DNS resolution
   nslookup registry.ollama.ai
   ```

2. **Verify disk space:**
   ```bash
   # Check available space on model storage
   kubectl exec -n ollama deployment/ollama-gpu -- df -h /root/.ollama
   
   # Check node storage
   ssh root@still-fawn.maas 'df -h'
   ```

3. **Check model pull status:**
   ```bash
   # Monitor active pulls
   curl -s http://ollama.homelab:11434/api/ps
   
   # Check Ollama logs
   kubectl logs -n ollama deployment/ollama-gpu --tail=50
   ```

**Resolution Steps:**

1. **Retry model pull with monitoring:**
   ```bash
   # Pull with status monitoring
   curl -X POST http://ollama.homelab:11434/api/pull \
     -H "Content-Type: application/json" \
     -d '{"name":"MODEL_NAME"}' | \
     while read line; do
       echo "$(date): $line"
     done
   ```

2. **Clear partial downloads if needed:**
   ```bash
   kubectl exec -n ollama deployment/ollama-gpu -- \
     rm -rf /root/.ollama/models/manifests/registry.ollama.ai/library/MODEL_NAME
   ```

3. **Restart Ollama service:**
   ```bash
   kubectl delete pod -n ollama -l app=ollama-gpu
   ```

### 3. GPU Memory Issues

**Symptoms:**
- "CUDA out of memory" errors
- Models failing to load
- Performance degradation

**Diagnosis Steps:**

1. **Check GPU memory usage:**
   ```bash
   ssh root@still-fawn.maas 'nvidia-smi'
   ```

2. **Identify memory consumers:**
   ```bash
   # Check all GPU processes
   ssh root@still-fawn.maas 'nvidia-smi | grep -A 10 Processes'
   
   # Check running AI workloads
   kubectl get pods -A | grep -E 'ollama|stable-diffusion|sd-'
   ```

3. **Check model sizes:**
   ```bash
   curl -s http://ollama.homelab:11434/api/tags | \
     jq -r '.models[] | "\(.name): \(.size/1024/1024/1024 | floor)GB"'
   ```

**Resolution Steps:**

1. **Scale down conflicting workloads:**
   ```bash
   # Temporarily scale down Stable Diffusion
   kubectl scale deployment stable-diffusion-webui --replicas=0 -n stable-diffusion
   
   # Or other GPU workloads as needed
   kubectl get deployments -A | grep -v "0/0"
   ```

2. **Adjust model parameters:**
   ```bash
   # Use smaller quantization if available
   curl -X POST http://ollama.homelab:11434/api/pull \
     -H "Content-Type: application/json" \
     -d '{"name":"MODEL_NAME:q4_0"}'  # Smaller quantization
   ```

3. **Configure memory limits:**
   ```bash
   # Edit deployment to add GPU memory overhead
   kubectl patch deployment ollama-gpu -n ollama -p '
   {
     "spec": {
       "template": {
         "spec": {
           "containers": [{
             "name": "ollama",
             "env": [{
               "name": "OLLAMA_GPU_OVERHEAD", 
               "value": "2147483648"
             }]
           }]
         }
       }
     }
   }'
   ```

### 4. Connection and Network Issues

**Symptoms:**
- Connection timeouts to Ollama service
- "connection refused" errors
- LoadBalancer not responding

**Diagnosis Steps:**

1. **Check service and endpoints:**
   ```bash
   kubectl get svc -n ollama
   kubectl get endpoints -n ollama
   kubectl describe svc ollama-lb -n ollama
   ```

2. **Test internal connectivity:**
   ```bash
   # Test from within cluster
   kubectl run test-pod --image=curlimages/curl -it --rm -- \
     curl http://ollama-lb.ollama.svc.cluster.local:80/api/tags
   ```

3. **Check LoadBalancer status:**
   ```bash
   # Check MetalLB assignment
   kubectl get svc ollama-lb -n ollama -o wide
   
   # Test LoadBalancer IP
   curl -s http://LOADBALANCER_IP:80/api/tags
   ```

**Resolution Steps:**

1. **Restart network components:**
   ```bash
   # Restart Ollama pod
   kubectl delete pod -n ollama -l app=ollama-gpu
   
   # Check MetalLB speaker pods if needed
   kubectl get pods -n metallb-system
   ```

2. **Verify DNS and routing:**
   ```bash
   # Test DNS resolution
   nslookup ollama.homelab
   
   # Check OPNsense DNS overrides if needed
   # Navigate to Services → Unbound DNS → Overrides
   ```

3. **Recreate service if needed:**
   ```bash
   kubectl delete svc ollama-lb -n ollama
   kubectl apply -f /path/to/ollama/service.yaml
   ```

## Performance Optimization

### GPU Configuration Best Practices

```yaml
env:
  - name: OLLAMA_GPU_OVERHEAD
    value: "1073741824"  # 1GB for RTX 3070
  - name: OLLAMA_NUM_PARALLEL
    value: "1"           # Single parallel processing
  - name: OLLAMA_MAX_LOADED_MODELS
    value: "1"           # One model at a time
  - name: OLLAMA_FLASH_ATTENTION
    value: "true"        # Enable GPU optimizations
  - name: CUDA_VISIBLE_DEVICES
    value: "0"           # Explicit GPU targeting
  - name: OLLAMA_KEEP_ALIVE
    value: "5m0s"        # Model unload timeout
```

### Resource Monitoring Commands

```bash
# Real-time GPU monitoring
watch -n 2 'ssh root@still-fawn.maas nvidia-smi'

# CPU usage monitoring
ssh root@still-fawn.maas 'top -b -n 1 | head -15'

# Memory usage
kubectl top pods -n ollama
kubectl top nodes

# Model status
curl -s http://ollama.homelab:11434/api/ps | jq .
```

### Performance Benchmarking

```bash
# Test model loading time
time curl -X POST http://ollama.homelab:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma3:4b","prompt":"benchmark test","stream":false}'

# GPU memory baseline
ssh root@still-fawn.maas 'nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits'

# CPU baseline
ssh root@still-fawn.maas 'top -b -n 1 | grep "Cpu(s)" | awk "{print \$2}" | cut -d% -f1'
```

## Emergency Procedures

### Complete Ollama Reset

```bash
# Scale down deployment
kubectl scale deployment ollama-gpu --replicas=0 -n ollama

# Clear model storage (WARNING: Deletes all models)
kubectl exec -n ollama deployment/ollama-gpu -- rm -rf /root/.ollama/models/*

# Scale back up
kubectl scale deployment ollama-gpu --replicas=1 -n ollama

# Wait for readiness
kubectl rollout status deployment/ollama-gpu -n ollama
```

### Resource Recovery

```bash
# Free GPU memory immediately
kubectl delete pod -n ollama -l app=ollama-gpu
kubectl scale deployment stable-diffusion-webui --replicas=0 -n stable-diffusion

# Clear system cache
ssh root@still-fawn.maas 'sync && echo 3 > /proc/sys/vm/drop_caches'

# Restart containerd if needed (EMERGENCY ONLY)
ssh root@still-fawn.maas 'systemctl restart containerd'
```

## Monitoring and Alerting

### Key Metrics to Monitor

1. **CPU Usage**: Ollama processes should use <20% CPU when idle
2. **GPU Memory**: Track VRAM allocation across AI workloads  
3. **Model Load Time**: Should complete within 30 seconds
4. **Response Time**: Generation should start within 10 seconds
5. **Error Rate**: Monitor failed requests and timeouts

### Recommended Alerts

```yaml
# Prometheus AlertManager rules
- alert: OllamaHighCPUUsage
  expr: rate(container_cpu_usage_seconds_total{pod=~"ollama.*"}[5m]) > 0.5
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "Ollama pod {{ $labels.pod }} high CPU usage"
    
- alert: OllamaGPUMemoryHigh  
  expr: nvidia_ml_py_memory_used_bytes / nvidia_ml_py_memory_total_bytes > 0.9
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "GPU memory usage > 90%"
```

## References

- [Ollama GPU Configuration Guide](../guides/ollama-gpu-optimization-guide.md)
- [High CPU Usage RCA](ollama-high-cpu-usage-rca.md)  
- [Home Assistant LLM Vision Integration](../guides/home-assistant-llm-vision-guide.md)
- [Kubernetes GPU Node Management](../guides/k8s-gpu-node-management.md)