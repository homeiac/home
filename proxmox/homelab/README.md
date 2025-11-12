# Proxmox K3s VM Automation with Python

This project automates the creation and management of K3s virtual machines (VMs)
in a Proxmox Virtual Environment (PVE) using Python. It follows a **src
layout**, leveraging `proxmoxer` for API interactions, `python-dotenv` for
configuration management, and `requests` for ISO downloads.

## **Project Structure**

```bash
homelab/  # Project Root
│── src/              # Contains all Python code
│   ├── homelab/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── proxmox_api.py
│   │   ├── resource_manager.py
│   │   ├── iso_manager.py
│   │   ├── vm_manager.py
│   │   ├── main.py
│   │   ├── .env  <-- Environment variables file
│── tests/
│── .gitignore
│── README.md
│── pyproject.toml  <-- Poetry project configuration
│── poetry.lock
```

## **Setup Instructions**

### **1. Install Poetry**

Follow the [official installation
guide](https://python-poetry.org/docs/#installation) to install Poetry.

### **2. Clone the Repository**

```bash
git clone https://github.com/your-repo/homelab.git
cd homelab
```

### **3. Install Dependencies**

```bash
poetry install
```

### **4. Configure Environment Variables**

Create the `.env` file inside `src/homelab/` and populate it with:

```ini
# Proxmox API Token (Replace with actual values)
API_TOKEN=root@pam!your_token_id=your_token_secret

# VM Defaults
ISO_NAME=ubuntu-24.04.2-desktop-amd64.iso
ISO_URL=https://releases.ubuntu.com/24.04.2/ubuntu-24.04.2-desktop-amd64.iso
```

> **Note:** The `.env` file is ignored in `.gitignore` to prevent accidental
> commits.

### **5. Run the Application**

#### **Run the script from the project root (where `pyproject.toml` is located):**

```bash
cd homelab
poetry run python -m homelab.main | tee proxmox_setup.log
```

## **Important Notes**

- The application **must be run from the project root**, **not** from `src/` or
  `src/homelab/`.
- The `.env` file **must be inside** `src/homelab/` because the
  script loads environment variables from that location.
- Logging output is stored in `proxmox_setup.log`.

## **Python Module Overview**

- **`config.py`** - Loads configuration from `.env`.
- **`proxmox_api.py`** - Handles Proxmox API interactions.
- **`resource_manager.py`** - Calculates VM CPU and memory allocations.
- **`iso_manager.py`** - Manages ISO downloads and uploads.
- **`vm_manager.py`** - Creates VMs dynamically.
- **`main.py`** - Orchestrates the entire setup process.

Each module is tested in `tests/`, ensuring robustness and maintainability.

### **Running Unit Tests**

To verify the functionality, run:

```bash
poetry add --dev pytest
pytest tests/
```

This ensures a fully automated, modular, and testable Proxmox K3s VM deployment
workflow.

## Fully Idempotent Provisioning (New!)

The provisioning system now handles the complete lifecycle automatically:

### One Command Setup

```bash
cd proxmox/homelab
poetry install
cp .env.example .env
# Edit .env with your settings

# Run idempotent provisioning
poetry run python -m homelab.main
```

### What It Does

**Phase 1: ISO Management**
- Downloads Ubuntu cloud image if missing
- Uploads to all Proxmox nodes if needed

**Phase 2: VM Provisioning**
- Checks health of existing VMs
- Deletes and recreates unhealthy/stuck VMs
- Creates missing VMs automatically
- Validates network configuration
- Handles Proxmox API SSL issues with CLI fallback

**Phase 3: K3s Cluster Join**
- Retrieves join token from existing cluster
- Checks cluster membership
- Joins new VMs to cluster
- Skips VMs already in cluster

### Configuration

Required environment variables in `.env`:

```bash
# Proxmox API
API_TOKEN=root@pam!token=your-token-here

# Node Configuration
NODE_1=pve
NODE_2=chief-horse
NODE_3=still-fawn
# ... etc

# K3s Cluster (optional - skip if not set)
K3S_EXISTING_NODE_IP=192.168.4.212
```

### Idempotent Behavior

Safe to run multiple times:
- ✅ Skips existing healthy VMs
- ✅ Recreates unhealthy VMs (stopped/paused)
- ✅ Skips VMs already in k3s cluster
- ✅ Only uploads ISOs if missing
- ✅ Handles offline nodes gracefully

### Recovery from Stuck VMs

If a VM is stuck (stopped, paused, boot failure):

```bash
# Just run the provisioning - it will detect and fix automatically
poetry run python -m homelab.main
```

The system will:
1. Detect the unhealthy VM
2. Delete it
3. Recreate with proper configuration
4. Join to k3s cluster

No manual intervention required!

### Implementation Details

**New Modules:**
- `health_checker.py` - VM health detection
- `k3s_manager.py` - K3s cluster operations
- Enhanced `vm_manager.py` - VM deletion and health integration
- Enhanced `proxmox_api.py` - CLI fallback for SSL issues

**GitHub Issue:** #159 - Make VM provisioning fully idempotent

**Tests:** 100% coverage on all new functionality
