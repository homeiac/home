# Network Investigation Commands (Safe)

*Safe network investigation commands for homelab infrastructure*

## Safety Guidelines

### **ALWAYS Safe to Run:**
- DNS resolution tests
- Service connectivity tests from within network
- Reading network configuration files
- Checking local network interfaces

### **NEVER Run from External Machines:**
- Network scanning tools (nmap, masscan, etc.)
- Port scanning from client devices
- Network discovery from laptops/external systems

## DNS Investigation (Safe from anywhere)
```bash
# DNS resolution tests (actual homelab pattern)
nslookup <service>.app.homelab
dig <service>.app.homelab
host <service>.app.homelab

# Examples from investigation
nslookup ollama.app.homelab
nslookup stable-diffusion.app.homelab

# Check DNS server configuration
nslookup <service>.app.homelab <dns-server-ip>

# Reverse DNS lookup
nslookup <ip-address>
```

## Service Connectivity Tests
```bash
# Test service accessibility (from within network)
curl -I http://<service>.homelab:<port>
telnet <service>.homelab <port>
nc -zv <service>.homelab <port>

# Test HTTPS services
curl -k https://<service>.homelab
openssl s_client -connect <service>.homelab:443
```

## Network Configuration Investigation
```bash
# Local network interface information
ip addr show
ip route show
cat /etc/resolv.conf

# Network service status
systemctl status networking
systemctl status systemd-networkd
systemctl status NetworkManager
```

## Load Balancer and Ingress Investigation
```bash
# Kubernetes network services
kubectl get services -A --field-selector spec.type=LoadBalancer
kubectl get ingress -A
kubectl describe service <service-name> -n <namespace>

# MetalLB specific (if applicable)
kubectl get ipaddresspools -A
kubectl get l2advertisements -A
```

## From Homelab Network Only

### **Network Discovery (Only from within homelab network)**
```bash
# From homelab hosts/VMs only, never from external clients
ping -c 1 <gateway-ip>
arp -a  # ARP table (shows local network devices)

# Service discovery within cluster
kubectl get endpoints -A
kubectl get services -A -o wide
```

### **Infrastructure Network Status**
```bash
# From Proxmox nodes or internal hosts
ip neigh show  # Neighbor table
ss -tuln       # Listening services
netstat -rn    # Routing table
```

## Investigation Patterns

### **Service Accessibility Check:**
1. **DNS Resolution**: `nslookup service.homelab`
2. **Port Connectivity**: `nc -zv service.homelab port`
3. **HTTP Response**: `curl -I http://service.homelab:port`
4. **Kubernetes Service**: `kubectl get service service-name -A`

### **Load Balancer Investigation:**
1. **External IP Assignment**: `kubectl get services --field-selector spec.type=LoadBalancer`
2. **DNS Mapping**: `nslookup service.homelab` should return LoadBalancer IP
3. **Port Accessibility**: Test specific ports from internal network
4. **Ingress Rules**: `kubectl get ingress -A`

### **Network Troubleshooting:**
1. **Start Internal**: Test from within homelab network first
2. **Check DNS**: Verify DNS resolution works correctly
3. **Verify Services**: Test service endpoints directly
4. **Check Routes**: Examine routing tables on relevant hosts

## Common Network Patterns in Homelabs

### **DNS Architecture:**
- `.homelab` domain with local DNS server
- OPNsense Unbound DNS or similar
- DNS overrides for services: `service.homelab` → LoadBalancer IP

### **Service Access Patterns:**
- **HTTP/HTTPS**: Traefik IngressRoute → `service.homelab` → LoadBalancer
- **TCP Services**: Direct MetalLB LoadBalancer → `service.homelab` → specific IP
- **Internal Only**: ClusterIP services for internal communication

## Investigation Checklist

### **For New Service Setup:**
- [ ] DNS resolution: `nslookup service.homelab`
- [ ] LoadBalancer IP assigned: `kubectl get services`
- [ ] Port accessibility: `nc -zv service.homelab port`
- [ ] Ingress configuration: `kubectl get ingress`

### **For Connectivity Issues:**
- [ ] Service running: `kubectl get pods -A | grep service`
- [ ] Service endpoint: `kubectl get endpoints service-name`
- [ ] DNS resolution: Test from multiple locations
- [ ] Network path: Trace from client to service

All commands should be executed from within the homelab network or authorized management systems only.