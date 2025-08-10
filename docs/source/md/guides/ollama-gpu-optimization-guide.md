# Ollama GPU Optimization Guide

## Overview

This guide provides comprehensive instructions for optimizing Ollama deployments on NVIDIA GPU-equipped Kubernetes nodes. Based on real-world troubleshooting of high CPU usage issues and production optimization experience.

## Prerequisites

- Kubernetes cluster with GPU nodes
- NVIDIA runtime configured (`runtimeClassName: nvidia`)
- GPU nodes labeled with `nvidia.com/gpu.present: "true"`
- MetalLB or similar LoadBalancer solution

## GPU Configuration Parameters

### Essential Environment Variables

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama-gpu
  namespace: ollama
spec:
  template:
    spec:
      runtimeClassName: nvidia
      nodeSelector:
        nvidia.com/gpu.present: "true"
      containers:
        - name: ollama
          image: ollama/ollama:0.7.0
          env:
            # Core Ollama settings
            - name: OLLAMA_HOST
              value: "0.0.0.0"
            - name: OLLAMA_PORT
              value: "11434"
            
            # GPU Optimization Parameters
            - name: OLLAMA_GPU_OVERHEAD
              value: "1073741824"  # 1GB GPU memory overhead
            - name: OLLAMA_NUM_PARALLEL
              value: "1"           # Single parallel processing
            - name: OLLAMA_MAX_LOADED_MODELS
              value: "1"           # Limit loaded models
            - name: OLLAMA_FLASH_ATTENTION
              value: "true"        # Enable GPU optimizations
            - name: CUDA_VISIBLE_DEVICES
              value: "0"           # Explicit GPU targeting
            
            # Performance Tuning
            - name: OLLAMA_KEEP_ALIVE
              value: "5m0s"        # Model persistence
            - name: OLLAMA_LOAD_TIMEOUT
              value: "5m0s"        # Loading timeout
            - name: OLLAMA_MAX_QUEUE
              value: "512"         # Request queue limit
          resources:
            limits:
              nvidia.com/gpu: "1"
```

### Parameter Explanations

| Parameter | Purpose | Recommended Value | Impact |
|-----------|---------|-------------------|--------|
| `OLLAMA_GPU_OVERHEAD` | Reserve GPU memory for operations | `1073741824` (1GB) | Prevents CPU fallback under memory pressure |
| `OLLAMA_NUM_PARALLEL` | Concurrent processing threads | `1` | Reduces CPU usage for single-user scenarios |
| `OLLAMA_MAX_LOADED_MODELS` | Maximum models in GPU memory | `1` | Prevents memory conflicts with other AI workloads |
| `OLLAMA_FLASH_ATTENTION` | Enable GPU-optimized attention | `true` | Improves inference speed on modern GPUs |
| `CUDA_VISIBLE_DEVICES` | GPU device targeting | `0` | Explicit GPU selection, avoids ambiguity |
| `OLLAMA_KEEP_ALIVE` | Model unload delay | `5m0s` | Balance between memory usage and response time |

## GPU Memory Management

### Memory Allocation Strategy

For **RTX 3070 (8GB VRAM)**:
```yaml
# Single AI workload (Ollama only)
OLLAMA_GPU_OVERHEAD: "1073741824"  # 1GB overhead
# Available for models: ~7GB

# Multiple AI workloads (Ollama + Stable Diffusion)
OLLAMA_GPU_OVERHEAD: "2147483648"  # 2GB overhead  
# Stable Diffusion: ~3GB
# Available for Ollama models: ~3GB
```

For **RTX 4090 (24GB VRAM)**:
```yaml
# Production multi-workload
OLLAMA_GPU_OVERHEAD: "2147483648"  # 2GB overhead
# Can support multiple large models simultaneously
```

### Model Size Planning

| Model Family | Size | VRAM Usage | RTX 3070 Fit | RTX 4090 Fit |
|--------------|------|------------|---------------|---------------|
| `llama3.2:1b` | ~1GB | ~1.2GB | ✅ Yes | ✅ Yes |
| `gemma2:2b` | ~1.6GB | ~1.9GB | ✅ Yes | ✅ Yes |
| `gemma3:4b` | ~3.3GB | ~5.0GB | ✅ Yes | ✅ Yes |
| `llama3:8b` | ~4.7GB | ~6.8GB | ⚠️ Tight | ✅ Yes |
| `llama3:70b` | ~40GB | ~42GB | ❌ No | ❌ No* |

*Requires model sharding or CPU inference

## Performance Optimization

### CPU Usage Optimization

**Problem**: High CPU usage when model is idle
**Solution**: Configure parallel processing limits

```yaml
env:
  - name: OLLAMA_NUM_PARALLEL
    value: "1"  # Single parallel for single-user
  # or
  - name: OLLAMA_NUM_PARALLEL  
    value: "4"  # Multiple parallel for high-concurrency
```

### GPU Utilization Optimization

**Enable GPU-specific optimizations:**
```yaml
env:
  - name: OLLAMA_FLASH_ATTENTION
    value: "true"  # NVIDIA tensor optimizations
  - name: OLLAMA_NEW_ENGINE
    value: "true"  # Enable new inference engine
```

### Memory Pressure Prevention

**Avoid GPU memory exhaustion:**
```yaml
env:
  - name: OLLAMA_MAX_LOADED_MODELS
    value: "1"  # Single model to prevent OOM
  - name: OLLAMA_GPU_OVERHEAD
    value: "1073741824"  # Reserve memory buffer
```

## Multi-Workload Scenarios

### Ollama + Stable Diffusion

```yaml
# Stable Diffusion WebUI (scaled to 0 when not needed)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: stable-diffusion-webui
spec:
  replicas: 0  # Scale up only when needed
  
# Ollama with reduced overhead
env:
  - name: OLLAMA_GPU_OVERHEAD
    value: "2147483648"  # 2GB for shared GPU
  - name: OLLAMA_MAX_LOADED_MODELS
    value: "1"
```

### Dynamic Scaling Strategy

```bash
# Scale down Stable Diffusion for Ollama workloads
kubectl scale deployment stable-diffusion-webui --replicas=0 -n stable-diffusion

# Load large model in Ollama
curl -X POST http://ollama.homelab:11434/api/pull \
  -d '{"name":"llama3:8b"}'

# Scale back up Stable Diffusion when done
kubectl scale deployment stable-diffusion-webui --replicas=1 -n stable-diffusion
```

## Monitoring and Diagnostics

### GPU Utilization Monitoring

```bash
# Real-time GPU monitoring
watch -n 2 'nvidia-smi'

# GPU memory usage tracking
nvidia-smi --query-gpu=memory.used,memory.total --format=csv

# Process-specific GPU usage
nvidia-smi pmon -i 0 -s um
```

### Performance Benchmarking

```bash
# Model loading benchmark
time curl -X POST http://ollama.homelab:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma3:4b","prompt":"benchmark","stream":false}' \
  | jq -r '.total_duration'

# Concurrent request test
for i in {1..5}; do
  curl -X POST http://ollama.homelab:11434/api/generate \
    -H "Content-Type: application/json" \
    -d '{"model":"gemma3:4b","prompt":"test '$i'","stream":false}' &
done
wait
```

### CPU Usage Verification

```bash
# Check CPU usage is optimized
top -b -n 1 | grep ollama

# Expected: <20% CPU usage when idle
# Problem: >100% CPU usage indicates sub-optimal config
```

## Troubleshooting Common Issues

### High CPU Usage (>100%)

**Symptoms:**
- Ollama processes consuming excessive CPU
- High system load average
- Poor response times

**Resolution:**
```yaml
env:
  - name: OLLAMA_NUM_PARALLEL
    value: "1"
  - name: OLLAMA_GPU_OVERHEAD
    value: "1073741824"
  - name: OLLAMA_FLASH_ATTENTION
    value: "true"
```

### GPU Memory Errors

**Symptoms:**
- "CUDA out of memory" errors
- Models failing to load
- nvidia-smi shows 100% memory usage

**Resolution:**
```bash
# Scale down competing workloads
kubectl scale deployment stable-diffusion-webui --replicas=0 -n stable-diffusion

# Use smaller models or quantizations
curl -X POST http://ollama.homelab:11434/api/pull \
  -d '{"name":"gemma2:2b"}'  # Smaller alternative

# Increase GPU overhead
kubectl set env deployment/ollama-gpu OLLAMA_GPU_OVERHEAD=2147483648 -n ollama
```

### Slow Model Loading

**Symptoms:**
- Model pulls taking >10 minutes
- Timeouts during model download

**Resolution:**
```yaml
env:
  - name: OLLAMA_LOAD_TIMEOUT
    value: "10m0s"  # Increase timeout
  - name: OLLAMA_MAX_QUEUE
    value: "1024"   # Increase queue size
```

## Production Deployment Example

### Complete Optimized Deployment

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ollama
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama-gpu
  namespace: ollama
  labels:
    app: ollama-gpu
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ollama-gpu
  template:
    metadata:
      labels:
        app: ollama-gpu
    spec:
      runtimeClassName: nvidia
      nodeSelector:
        nvidia.com/gpu.present: "true"
      containers:
        - name: ollama
          image: ollama/ollama:0.7.0
          imagePullPolicy: IfNotPresent
          args:
            - serve
          env:
            # Basic Configuration
            - name: OLLAMA_HOST
              value: "0.0.0.0"
            - name: OLLAMA_PORT
              value: "11434"
            
            # GPU Optimization (CRITICAL)
            - name: OLLAMA_GPU_OVERHEAD
              value: "1073741824"  # 1GB GPU memory overhead
            - name: OLLAMA_NUM_PARALLEL
              value: "1"           # Single parallel processing
            - name: OLLAMA_MAX_LOADED_MODELS
              value: "1"           # One model limit
            - name: OLLAMA_FLASH_ATTENTION
              value: "true"        # GPU optimizations
            - name: CUDA_VISIBLE_DEVICES
              value: "0"           # Explicit GPU targeting
            
            # Performance Tuning
            - name: OLLAMA_KEEP_ALIVE
              value: "5m0s"
            - name: OLLAMA_LOAD_TIMEOUT
              value: "5m0s"
            - name: OLLAMA_MAX_QUEUE
              value: "512"
          ports:
            - containerPort: 11434
          resources:
            limits:
              nvidia.com/gpu: "1"
          livenessProbe:
            httpGet:
              path: /
              port: 11434
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /
              port: 11434
            initialDelaySeconds: 5
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: ollama-lb
  namespace: ollama
spec:
  type: LoadBalancer
  selector:
    app: ollama-gpu
  ports:
    - name: http
      port: 80
      targetPort: 11434
      protocol: TCP
```

### Validation Commands

```bash
# Deploy the configuration
kubectl apply -f ollama-optimized-deployment.yaml

# Wait for readiness
kubectl rollout status deployment/ollama-gpu -n ollama

# Test GPU optimization
curl -X POST http://ollama.homelab:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma3:4b","prompt":"GPU optimization test","stream":false}'

# Verify CPU usage is optimized
ssh root@still-fawn.maas 'top -b -n 1 | head -15'

# Check GPU utilization
ssh root@still-fawn.maas 'nvidia-smi'
```

## Best Practices Summary

1. **Always set GPU overhead** - Prevents CPU fallback
2. **Limit parallel processing** - Reduces idle CPU usage  
3. **Enable GPU optimizations** - Use flash attention for modern GPUs
4. **Explicit GPU targeting** - Set CUDA_VISIBLE_DEVICES
5. **Monitor resource usage** - Track GPU memory and CPU usage
6. **Plan for multi-workload** - Consider other AI services on same GPU
7. **Use appropriate model sizes** - Match models to available VRAM
8. **Implement health checks** - Ensure service reliability
9. **Document configurations** - Include rationale for parameter choices
10. **Test performance regularly** - Benchmark after configuration changes

## References

- [Ollama High CPU Usage RCA](../troubleshooting/ollama-high-cpu-usage-rca.md)
- [Ollama Troubleshooting Runbook](../troubleshooting/ollama-troubleshooting-runbook.md)
- [NVIDIA GPU Monitoring Guide](nvidia-gpu-monitoring-guide.md)
- [Kubernetes GPU Node Management](k8s-gpu-node-management.md)