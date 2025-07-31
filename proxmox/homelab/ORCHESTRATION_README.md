# Homelab Infrastructure Orchestration

## 🎯 Overview

This orchestrator provides **idempotent infrastructure management** for your homelab, ensuring all critical services survive reboots and maintain consistent configurations.

## 🚀 Quick Start

### One Command to Rule Them All

```bash
# Full orchestration (safe to run multiple times)
poetry run python orchestrate_homelab.py

# See what would be done without changes
poetry run python orchestrate_homelab.py --dry-run
```

## 📋 What It Does

The orchestrator performs these steps **idempotently**:

### 1. 🚀 **K3s VM Provisioning**
- Uses existing `vm_manager.py` logic
- Creates K3s VMs on all Proxmox nodes from `.env` configuration
- Skips VMs that already exist

### 2. 📝 **MAAS Device Registration** 
- **K3s VMs**: Auto-discovers MAC addresses and registers in MAAS
- **Critical Services**: Registers Uptime Kuma containers for persistent IPs
- **Result**: Services get permanent `*.maas` hostnames

### 3. 🔧 **Critical Service Registration**
- Registers Uptime Kuma LXC containers in MAAS
- Ensures monitoring services have persistent DNS names
- Example: `uptime-kuma-pve.maas`, `uptime-kuma-fun-bedbug.maas`

### 4. 📊 **Monitoring Sync**
- Updates all Uptime Kuma instances with current infrastructure
- Uses idempotent `uptime_kuma_client.py` (creates/updates/skips as needed)
- Ensures monitoring covers all Proxmox nodes and K3s VMs

### 5. 📚 **Documentation Generation** *(Future)*
- Auto-generates network diagrams
- Creates service inventory
- Updates infrastructure documentation

## ⚙️ Configuration

### .env File Structure

The orchestrator reads from your existing `.env` file with these additions:

```bash
# Existing node configuration (unchanged)
NODE_1=pve
NODE_1_STORAGE=local-zfs
# ... etc

# NEW: Critical services configuration
CRITICAL_SERVICE_UPTIME_KUMA_PVE_NAME=uptime-kuma-pve
CRITICAL_SERVICE_UPTIME_KUMA_PVE_MAC=BC:24:11:B3:D0:40
CRITICAL_SERVICE_UPTIME_KUMA_PVE_HOST_NODE=pve
CRITICAL_SERVICE_UPTIME_KUMA_PVE_LXC_ID=100

CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_NAME=uptime-kuma-fun-bedbug
CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_MAC=BC:24:11:5F:CD:81
CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_HOST_NODE=fun-bedbug
CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_LXC_ID=112

# NEW: Service credentials
MAAS_USER=gshiva
MAAS_PASSWORD=elder137berry
UPTIME_KUMA_USERNAME=gshiva
UPTIME_KUMA_PASSWORD=elder137berry
```

## 🔄 Idempotent Behavior

### Safe to Run Multiple Times
- **VM Provisioning**: Skips existing VMs
- **MAAS Registration**: Skips existing devices  
- **Monitoring**: Updates only changed configurations
- **No Duplicates**: Never creates duplicate resources

### Example Output
```bash
🎯 Starting Infrastructure Orchestration...
🚀 Step 1: Provisioning K3s VMs...
  ⚠️  VM exists: k3s-vm-pve (vmid=107), skipping.
  ⚠️  VM exists: k3s-vm-still-fawn (vmid=108), skipping.
  ✅ Step 1 complete: 3 K3s VMs processed

📝 Step 2: Registering K3s VMs in MAAS...
  Device k3s-vm-pve already exists in MAAS
  ✅ Successfully registered k3s-vm-chief-horse in MAAS
  ✅ Step 2 complete: 2 VMs registered, 0 failed

🔧 Step 3: Registering critical services in MAAS...
  ✅ Successfully registered uptime-kuma-pve in MAAS
  Device uptime-kuma-fun-bedbug already exists in MAAS
  ✅ Step 3 complete: 1 services registered, 0 failed

📊 Step 4: Updating monitoring configuration...
  - 0 monitors created, 2 updated, 13 up-to-date
  ✅ Step 4 complete: 2 instances updated, 0 failed

🎉 Infrastructure Orchestration Complete! (45.2s)
```

## 🛠️ Architecture Integration

### Leverages Existing Code
- **`vm_manager.py`**: K3s VM provisioning logic (unchanged)
- **`uptime_kuma_client.py`**: Idempotent monitoring management  
- **`config.py`**: .env file parsing (enhanced)
- **SSH/MAAS integration**: From recent Uptime Kuma persistence work

### New Components
- **`infrastructure_orchestrator.py`**: Main orchestration logic
- **`orchestrate_homelab.py`**: CLI wrapper script
- **Enhanced .env**: Additional fields for critical services

## 🎯 Problem Solved

### Before: Manual, Error-Prone
- VMs created manually or with separate scripts
- Services got random DHCP IPs after reboots
- Monitoring configuration manually maintained
- Documentation outdated

### After: Automated, Consistent  
- One script provisions and maintains everything
- All services have persistent DNS names
- Monitoring automatically reflects infrastructure
- Idempotent - safe to run anytime

## 🚀 Future Enhancements

### Tier 2: Smart Documentation
```bash
# Auto-generated from infrastructure state
docs/
├── network-diagram.mermaid          # Who talks to who
├── service-inventory.md             # What's running where  
├── capacity-planning.md             # Resource usage trends
└── disaster-recovery.md             # Recovery procedures
```

### Tier 3: Self-Healing
```bash
# Detect and fix common issues
./orchestrate_homelab.py --check-health
# - DNS resolution issues
# - Container restart policy problems  
# - Monitoring gaps
# - Configuration drift
```

## 🧪 Testing

### Test Reboot Persistence
```bash
# Before running orchestrator
ssh root@fun-bedbug.maas "pct stop 112 && pct start 112"
curl http://192.168.4.224:3001  # Might get different IP

# After running orchestrator  
ssh root@fun-bedbug.maas "pct stop 112 && pct start 112"
curl http://uptime-kuma-fun-bedbug.maas:3001  # Always works
```

### Test Idempotency
```bash
# Run twice, should be identical output
poetry run python orchestrate_homelab.py
poetry run python orchestrate_homelab.py
# Second run should show "already exists" for most resources
```

## 🤝 Community Adoption

### For Other Homelab Enthusiasts

1. **Clone the approach**: Copy `.env` structure and orchestrator pattern
2. **Adapt to your setup**: Change IP ranges, hostnames, services  
3. **Start simple**: Use just VM provisioning first
4. **Add incrementally**: Add MAAS registration, monitoring, etc.
5. **Share improvements**: Contribute back enhancements

### Extensibility Points
- **New VM types**: Add to Config.get_nodes()
- **New critical services**: Add to CRITICAL_SERVICE_* pattern
- **New monitoring**: Extend UptimeKumaClient  
- **New documentation**: Extend step5_generate_documentation()

This orchestrator transforms homelab management from manual, error-prone processes into **reliable, automated, idempotent infrastructure management** while remaining simple enough for solo operation.