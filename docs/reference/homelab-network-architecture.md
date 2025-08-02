# Homelab Network Architecture Reference

*Based on investigation of actual Traefik + MetalLB + OPNsense Unbound DNS configuration*

## DNS Architecture Pattern

### **Domain Structure**: `.app.homelab`
- **Primary Domain**: `homelab`
- **Application Subdomain**: `app.homelab` 
- **Service Pattern**: `<service>.app.homelab`

### **Examples from Investigation**:
- `ollama.app.homelab` → `192.168.4.80` (via Traefik)
- `stable-diffusion.app.homelab` → `192.168.4.80` (via Traefik)

## Network Traffic Flow

### **HTTP/HTTPS Services via Traefik**:
```
Client → DNS: service.app.homelab → 192.168.4.80 (Traefik LoadBalancer)
       → Traefik Ingress Rules → Internal Service → Pod
```

### **Direct TCP Services via MetalLB**:
```
Client → DNS: service.app.homelab → Specific LoadBalancer IP → Pod
```

## Infrastructure Components

### **Traefik (HTTP Router)**
- **LoadBalancer IP**: `192.168.4.80`
- **Ports**: 80 (HTTP), 443 (HTTPS)
- **Function**: HTTP ingress routing based on hostname
- **Configuration**: Kubernetes Ingress resources with `ingressClassName: traefik`

### **MetalLB (LoadBalancer Provider)**
- **IP Pool**: `192.168.4.80-120` (estimated from observed IPs)
- **Assigned IPs**:
  - `192.168.4.80` - Traefik (HTTP router)
  - `192.168.4.81` - Ollama (direct service)
  - `192.168.4.82` - Stable Diffusion (direct service) 
  - `192.168.4.120` - Samba (TCP services)

### **OPNsense Unbound DNS**
- **Function**: Local DNS resolver with host overrides
- **Configuration**: Host overrides map `*.app.homelab` to appropriate IPs
- **Pattern**: Single DNS entry per service pointing to either Traefik or direct LoadBalancer

## Service Deployment Patterns

### **Pattern 1: HTTP Services via Traefik Ingress**
*Used for: Web applications, APIs, dashboards*

**DNS Configuration**:
```
service.app.homelab → 192.168.4.80 (Traefik)
```

**Kubernetes Configuration**:
```yaml
# Service (ClusterIP or LoadBalancer)
apiVersion: v1
kind: Service
metadata:
  name: service-name
spec:
  type: ClusterIP  # Internal only, accessed via Traefik
  
# Ingress Route
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    kubernetes.io/ingress.class: traefik
spec:
  ingressClassName: traefik
  rules:
  - host: service.app.homelab
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: service-name
            port:
              number: 80
```

### **Pattern 2: Direct TCP Services via MetalLB**
*Used for: Non-HTTP protocols, direct service access*

**DNS Configuration**:
```
service.app.homelab → <assigned-metallb-ip>
```

**Kubernetes Configuration**:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: service-name
spec:
  type: LoadBalancer  # Gets MetalLB IP assignment
  ports:
  - port: <service-port>
    targetPort: <container-port>
```

## DNS Management Process

### **For New HTTP Services**:
1. **Deploy Kubernetes Ingress**: Host set to `service.app.homelab`
2. **DNS Override**: `service.app.homelab` → `192.168.4.80` (Traefik IP)
3. **Access**: `http://service.app.homelab` routes through Traefik

### **For New TCP Services**:
1. **Deploy LoadBalancer Service**: Gets MetalLB IP assignment
2. **Check Assigned IP**: `kubectl get service service-name`
3. **DNS Override**: `service.app.homelab` → `<assigned-metallb-ip>`
4. **Access**: `service.app.homelab:port` connects directly

## Investigation Commands

### **Check Service Access Pattern**:
```bash
# Check if HTTP service (via Traefik)
kubectl get ingress -A | grep service-name

# Check if direct TCP service (via MetalLB)
kubectl get services -A --field-selector spec.type=LoadBalancer | grep service-name

# Test DNS resolution
nslookup service.app.homelab

# Test HTTP access
curl -I http://service.app.homelab

# Test TCP access (if applicable)
nc -zv service.app.homelab port
```

## Common Configurations

### **Ollama Example** (Mixed Pattern):
- **Direct LoadBalancer**: `192.168.4.81` for API access
- **Traefik Ingress**: `ollama.app.homelab` → `192.168.4.80` for web interface
- **Both resolve to same service, different access methods**

### **Web Applications Pattern**:
- Single Traefik ingress: `app.app.homelab` → `192.168.4.80`
- OPNsense DNS: `app.app.homelab` → `192.168.4.80`
- Clean URL access without port numbers

This architecture provides clean hostname-based access while supporting both HTTP (via Traefik) and TCP (via direct MetalLB) services.