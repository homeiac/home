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
