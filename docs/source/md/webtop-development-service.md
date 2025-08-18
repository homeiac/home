# Webtop Development Environment Service

## Overview

Webtop provides a cloud-based development environment accessible via web browser, featuring GPU acceleration, Docker-in-Docker support, and persistent storage. Deployed via Kubernetes GitOps for reliable, scalable infrastructure management.

## Service Architecture

### Deployment Overview
- **Platform**: K3s Kubernetes cluster via Flux GitOps
- **Container**: LinuxServer.io Webtop (Ubuntu XFCE)
- **Access**: https://webtop.app.homelab
- **GPU**: RTX 3070 time-slicing for AI/ML development
- **Storage**: 50Gi persistent volume for home directory

### Network Configuration
```yaml
LoadBalancer Service:
  - IP: 192.168.4.120 (MetalLB pool allocation)
  - Ports: 3000 (HTTP), 3001 (HTTPS)
  
Traefik Ingress:
  - Hostname: webtop.app.homelab
  - TLS: Automatic certificate via Traefik
  - Backend: LoadBalancer service HTTP port
```

### Key Features
- **Full Desktop Environment**: Ubuntu XFCE with complete development tools
- **GPU Acceleration**: Direct access to RTX 3070 for AI/ML workloads
- **Docker-in-Docker**: VS Code devcontainers via dedicated sidecar
- **Persistent Storage**: Home directory survives pod restarts and updates
- **Secure Access**: HTTPS with automatic TLS termination

## GitOps Configuration

### File Structure
```
gitops/clusters/homelab/apps/webtop/
├── namespace.yaml      # Dedicated namespace for development tools
├── pvc.yaml           # 50Gi persistent volume claim
├── deployment.yaml    # Main deployment with GPU + DinD sidecar
├── service.yaml       # LoadBalancer service configuration
├── ingress.yaml       # Traefik ingress with TLS
└── kustomization.yaml # Kustomize resource list
```

### Resource Specifications
```yaml
Resources:
  CPU: 2 cores (requests), 4 cores (limits)
  Memory: 4Gi (requests), 8Gi (limits)
  GPU: nvidia.com/gpu (shared via time-slicing)
  Storage: 50Gi local-path PVC mounted to /config

Environment:
  - PUID=1000, PGID=1000 (user permissions)
  - TZ=America/Los_Angeles (Pacific timezone)
  - Ubuntu XFCE desktop environment
```

### Docker-in-Docker Configuration
```yaml
Sidecar Container:
  - Image: docker:dind
  - Privileged: true
  - Volume: shared Docker socket
  - Purpose: VS Code devcontainer support
```

## Access and Usage

### Web Interface Access
1. **Primary Access**: https://webtop.app.homelab
2. **Direct LoadBalancer**: http://192.168.4.120:3000
3. **HTTPS Direct**: https://192.168.4.120:3001 (self-signed cert)

### Development Environment Features
- **Desktop Environment**: Full Ubuntu XFCE desktop via noVNC
- **Development Tools**: Pre-installed git, curl, wget, build tools
- **GPU Access**: nvidia-smi available for AI/ML development
- **Container Support**: Docker CLI and Docker-in-Docker for devcontainers
- **Persistent Home**: /config directory maintains all user data

### GPU Integration
```bash
# Verify GPU access within Webtop desktop
nvidia-smi

# Check GPU sharing with other workloads
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv

# GPU memory allocation shows time-slicing active
```

## Development Workflow

### Getting Started
1. Navigate to https://webtop.app.homelab
2. Complete desktop environment loads automatically
3. Access full Ubuntu XFCE desktop with development tools
4. All changes to home directory persist across sessions

### Docker Development
```bash
# Docker CLI available for container management
docker --version

# VS Code with devcontainer support
# Docker-in-Docker sidecar enables full devcontainer functionality
code .  # Opens VS Code with devcontainer support
```

### AI/ML Development
```bash
# GPU acceleration available for development
nvidia-smi  # Verify RTX 3070 access

# Integration with homelab Ollama service
curl http://ollama.app.homelab:11434/api/generate \
  -d '{"model": "llama3.2", "prompt": "Hello world"}'
```

## Data Persistence

### Persistent Volume Configuration
- **Storage Class**: local-path (K3s default)
- **Size**: 50Gi allocated for home directory
- **Mount Point**: /config (maps to user home directory)
- **Persistence**: Data survives pod restarts, updates, and node migrations

### Backup Considerations
- **Kubernetes**: PVC snapshots via K3s backup mechanisms
- **Application**: User responsible for git repositories and cloud backups
- **Configuration**: Desktop settings and installed packages persist

## Integration with Homelab Services

### AI/ML Services
- **Ollama**: Direct access to LLM models via ollama.app.homelab
- **Stable Diffusion**: GPU sharing enables concurrent AI workloads
- **Model Storage**: Local model caching on persistent storage

### Development Infrastructure
- **Git**: Pre-configured for repository access
- **Container Registries**: Access to Docker Hub and private registries
- **Build Tools**: Complete development toolchain available

### Network Access
- **Internal Services**: Full access to homelab network (192.168.4.0/24)
- **External Connectivity**: Internet access for package installation
- **Service Discovery**: DNS resolution for .app.homelab services

## Monitoring and Management

### Health Checks
```bash
# Check deployment status
kubectl get pods -n webtop

# Verify service availability
kubectl get svc -n webtop

# Check ingress configuration
kubectl get ingress -n webtop
```

### Resource Monitoring
```bash
# Monitor GPU usage
kubectl top pods -n webtop --containers

# Check persistent volume usage
kubectl exec -n webtop deployment/webtop -- df -h /config

# View logs
kubectl logs -n webtop deployment/webtop -c webtop
```

### Scaling Considerations
- **Single User**: Current configuration optimized for single developer
- **Multi-User**: Requires multiple deployments with resource quotas
- **GPU Sharing**: Time-slicing enables concurrent GPU workloads

## Troubleshooting

### Common Issues

#### Desktop Not Loading
```bash
# Check container status
kubectl describe pod -n webtop -l app=webtop

# Verify resource allocation
kubectl top pod -n webtop

# Check logs for noVNC issues
kubectl logs -n webtop deployment/webtop -c webtop
```

#### GPU Not Available
```bash
# Verify GPU resource request
kubectl describe pod -n webtop -l app=webtop | grep nvidia.com/gpu

# Check node GPU capacity
kubectl describe node k3s-vm-still-fawn | grep nvidia.com/gpu

# Verify time-slicing configuration
kubectl get configmap -n kube-system nvidia-device-plugin-config -o yaml
```

#### Persistent Storage Issues
```bash
# Check PVC status
kubectl get pvc -n webtop

# Verify mount in container
kubectl exec -n webtop deployment/webtop -- ls -la /config

# Check storage class
kubectl get storageclass local-path
```

#### Network Connectivity
```bash
# Test LoadBalancer service
curl -I http://192.168.4.120:3000

# Check Traefik ingress
kubectl get ingress -n webtop -o yaml

# Verify DNS resolution
nslookup webtop.app.homelab 192.168.4.1
```

### Performance Optimization

#### Resource Tuning
- **CPU**: Adjust based on development workload requirements
- **Memory**: Increase for large builds or multiple browser tabs
- **GPU**: Monitor time-slicing efficiency with concurrent workloads

#### Network Performance
- **Direct Access**: Use LoadBalancer IP for reduced latency
- **Compression**: Browser settings for bandwidth optimization
- **Local Development**: Consider SSH tunneling for intensive workflows

## Security Considerations

### Access Control
- **Network**: Accessible only within homelab network (192.168.4.0/24)
- **Authentication**: No built-in authentication (network-based security)
- **TLS**: Automatic certificate management via Traefik

### Container Security
- **User Context**: Runs as non-root user (PUID=1000)
- **Privileged Access**: Docker-in-Docker sidecar requires privileges
- **Resource Limits**: CPU and memory limits prevent resource exhaustion

### Data Protection
- **Persistent Storage**: Regular backup of PVC recommended
- **Code Repositories**: Use git for version control and remote backups
- **Sensitive Data**: Avoid storing secrets in development environment

## Future Enhancements

### Planned Improvements
- **IDE Integration**: Pre-installed VS Code with extensions
- **Development Tools**: Language-specific toolchains (Python, Node.js, Go)
- **Ollama Integration**: Direct LLM assistance within development environment
- **Multi-User Support**: Resource quotas and user isolation

### Advanced Features
- **Code Server**: Alternative web-based IDE deployment
- **Remote Development**: SSH-based development environment access
- **Build Pipelines**: Integration with CI/CD workflows
- **Container Registry**: Private registry for development images

This service provides a comprehensive cloud development environment that leverages the homelab's GPU resources while maintaining data persistence and secure access patterns.