# Windows Docker High-Memory Container Guide

## Overview

This guide documents the setup and optimization of Windows Docker containers for high-memory workloads on Windows 10 Pro, utilizing Hyper-V isolation to maximize the 64GB RAM allocation.

## Architecture

### Resource Allocation Strategy
- **WSL2 Ubuntu**: 16GB RAM (Linux development environment)
- **Windows Containers**: 48GB RAM available (high-memory workloads)
- **Windows OS**: 8GB reserved for system operations

### Isolation Mode
Windows 10 automatically uses **Hyper-V isolation** for containers, which provides:
- Compatibility with any Windows container version
- Enhanced security and isolation
- No kernel version matching requirements
- Higher resource overhead but better compatibility

## Prerequisites

### System Requirements
- Windows 10 Pro or Enterprise
- Hyper-V enabled
- Docker Desktop installed and running
- Minimum 32GB RAM (64GB recommended)

### Verification Commands
```powershell
# Check Docker isolation mode
docker info | Select-String "Isolation"
# Expected output: Default Isolation: hyperv

# Verify available memory
Get-WmiObject -Class Win32_ComputerSystem | Select-Object TotalPhysicalMemory

# Check Hyper-V status
Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
```

## Compatible Base Images

### Recommended Base Images for Windows 10
- `mcr.microsoft.com/windows/servercore:ltsc2019` - Full Windows Server Core
- `mcr.microsoft.com/windows/nanoserver:1809` - Lightweight option
- `mcr.microsoft.com/powershell:lts-windowsservercore-ltsc2019` - PowerShell Core

### Image Compatibility Notes
- **Hyper-V isolation** allows any Windows container version on Windows 10
- **Process isolation** requires exact kernel version matching (not recommended)
- Always test new base images in your specific environment

## Container Creation Examples

### High-Memory Database Container
```dockerfile
FROM mcr.microsoft.com/windows/servercore:ltsc2019
SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop';"]

# Install SQL Server or database of choice
RUN Write-Host 'Installing database server...'

# Configure for high memory usage
ENV SQLSERVER_MEMORY_LIMIT=16GB

EXPOSE 1433
CMD ["powershell", "-Command", "Start-DatabaseServer"]
```

### Memory-Intensive Analytics Container
```dockerfile
FROM mcr.microsoft.com/powershell:lts-windowsservercore-ltsc2019

# Copy analytics application
COPY analytics-app.ps1 C:/app/analytics-app.ps1

# Set memory configuration
ENV MAX_HEAP_SIZE=20g
ENV ANALYTICS_MEMORY_POOL=16g

EXPOSE 8080
CMD ["pwsh", "-File", "C:/app/analytics-app.ps1"]
```

### Development Environment Container
```dockerfile
FROM mcr.microsoft.com/windows/servercore:ltsc2019
SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop';"]

# Install development tools
RUN Set-ExecutionPolicy Bypass -Scope Process -Force; \
    iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1')); \
    choco install -y git nodejs python3 visualstudio2019buildtools

WORKDIR C:/workspace
CMD ["powershell"]
```

## Deployment Commands

### High-Memory Container Deployment
```powershell
# Database server (16GB memory limit)
docker run -d --name database-server `
  --restart unless-stopped `
  -m 16g `
  -p 1433:1433 `
  your-database-image:latest

# Analytics engine (20GB memory limit)  
docker run -d --name analytics-engine `
  --restart unless-stopped `
  -m 20g `
  -p 8080:8080 `
  your-analytics-image:latest

# Development environment (12GB memory limit)
docker run -d --name dev-environment `
  --restart unless-stopped `
  -m 12g `
  -p 3000:3000 `
  -v C:\dev-projects:C:\workspace `
  your-dev-image:latest
```

### Resource Monitoring
```powershell
# Monitor container resource usage
docker stats

# Check specific container memory usage
docker stats container-name --no-stream

# View container logs
docker logs container-name --tail 50 -f
```

## Memory Management Best Practices

### Container Memory Limits
- Always set explicit memory limits with `-m` flag
- Leave 4-8GB buffer for Windows OS operations
- Monitor actual memory usage vs. allocated limits
- Consider memory overhead of Hyper-V isolation

### Memory Optimization Techniques
```powershell
# In PowerShell applications, explicitly manage memory:
[System.GC]::Collect()
[System.GC]::WaitForPendingFinalizers()
[System.GC]::Collect()

# Set application-specific memory limits
$env:MAX_MEMORY_USAGE = "16GB"
```

### Scaling Strategy
1. **Start with smaller containers** to test resource requirements
2. **Monitor memory usage patterns** over time  
3. **Adjust limits** based on actual usage
4. **Implement memory cleanup** in long-running applications

## WSL2 Integration

### Complementary Linux Environment
While Windows containers handle high-memory workloads, WSL2 provides:
- Linux development tools and environments
- Container orchestration and monitoring tools
- Lightweight services that don't require Windows

### Resource Coordination
```powershell
# Check WSL2 memory configuration
wsl --distribution Ubuntu-24.04 --exec free -h

# WSL2 configuration in ~/.wslconfig
[wsl2]
memory=16GB
processors=4
```

## Troubleshooting

### Common Issues

#### Container Startup Failures
```powershell
# Check Docker service status
Get-Service docker

# Verify Hyper-V is running
Get-VM | Where-Object State -eq Running
```

#### Memory Allocation Problems
```powershell
# Check available memory
Get-Counter "\Memory\Available MBytes"

# Monitor Docker daemon memory usage
Get-Process "Docker Desktop" | Select-Object ProcessName, WorkingSet64
```

#### Image Compatibility Issues
- Ensure base image supports your Windows version
- Try different base image versions (ltsc2019, 1809, etc.)
- Use Hyper-V isolation to overcome kernel version mismatches

### Performance Optimization
- Use SSD storage for container images and volumes
- Configure appropriate CPU limits alongside memory limits
- Monitor network I/O for containerized services
- Implement health checks for container reliability

## Integration with Homelab Infrastructure

### Network Configuration
- Windows containers can access homelab network directly
- Configure port mappings for service access
- Use Docker networks for container-to-container communication

### Monitoring Integration
- Deploy monitoring agents in containers
- Export metrics to existing Prometheus/Grafana stack
- Set up log forwarding to centralized logging system

### Backup and Recovery
- Implement container data volume backups
- Document container rebuild procedures
- Test disaster recovery processes regularly

## Conclusion

Windows Docker containers with Hyper-V isolation provide a reliable method to utilize high-memory workloads on Windows 10. The combination of proper resource allocation, compatible base images, and effective monitoring creates a robust development and production environment for Windows-specific applications.

Key advantages:
- **High memory utilization** (up to 48GB for containers)
- **Reliable isolation** with Hyper-V
- **Flexible deployment** options
- **Integration** with existing homelab infrastructure

This approach maximizes the value of powerful Windows hardware while maintaining development flexibility and operational reliability.