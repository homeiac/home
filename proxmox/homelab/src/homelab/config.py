from urllib.parse import quote
from dotenv import load_dotenv
import os

import urllib


class Config:
    """Loads and manages configuration from environment variables."""

    load_dotenv()

    API_TOKEN = os.getenv("API_TOKEN")
    ISO_NAME = os.getenv("ISO_NAME", "ubuntu-24.04.2-desktop-amd64.iso")
    ISO_URL = os.getenv(
        "ISO_URL",
        "https://releases.ubuntu.com/24.04.2/ubuntu-24.04.2-desktop-amd64.iso",
    )
    VM_NAME_TEMPLATE = os.getenv("VM_NAME_TEMPLATE", "k3s-vm-{node}")
    CLOUD_USER = os.getenv("CLOUD_USER", "ubuntu")
    CLOUD_PASSWORD = os.getenv("CLOUD_PASSWORD", "ubuntu")
    SSH_PUBKEY_PATH = os.getenv("SSH_PUBKEY_PATH", "/root/.ssh/id_rsa.pub")
    CLOUD_IP_CONFIG = os.getenv("CLOUD_IP_CONFIG", "ip=dhcp")

    # Load public key contents at import-time
    _SSH_PATH = os.path.expanduser(os.getenv("SSH_PUBKEY_PATH", "~/.ssh/id_rsa.pub"))
    with open(_SSH_PATH) as _f:
        raw_ssh = _f.read().strip()

    SSH_PUBKEY = quote(raw_ssh, safe='')

    # Ensure ipconfig0 is correctly formatted
    _raw_ip = os.getenv("CLOUD_IP_CONFIG", "dhcp").strip()
    CLOUD_IP_CONFIG = _raw_ip if _raw_ip.startswith("ip=") else f"ip={_raw_ip}"

    VM_START_TIMEOUT = int(os.getenv("VM_START_TIMEOUT", "180"))

    # Comma-separated Proxmox node IPs, e.g. "192.168.86.194,192.168.1.122,192.168.4.122"
    PVE_IPS = [
        ip.strip()
        for ip in os.getenv("PVE_IPS", "").split(",")
        if ip.strip()
    ]

    @staticmethod
    def get_nodes():
        """Dynamically loads nodes from environment variables."""
        nodes = []
        index = 1
        while os.getenv(f"NODE_{index}"):
            nodes.append(
                {
                    "name": os.getenv(f"NODE_{index}"),
                    "storage": os.getenv(f"STORAGE_{index}"),
                    "img_storage": os.getenv(f"IMG_STORAGE_{index}"),
                    "cpu_ratio": float(os.getenv(f"CPU_RATIO_{index}")),
                    "memory_ratio": float(os.getenv(f"MEMORY_RATIO_{index}")),
                }
            )
            print(f"NODE_{index}: storage={os.getenv(f'STORAGE_{index}')}, cpu_ratio={os.getenv(f'CPU_RATIO_{index}')}, memory_ratio={os.getenv(f'MEMORY_RATIO_{index}')}")
            index += 1
        return nodes

    @staticmethod
    def get_network_ifaces_for(index: int) -> list[str]:
        """
        Reads NETWORK_IFACES_<index+1> from the environment, splits by comma,
        and returns a list of bridge names (e.g. ['vmbr0','vmbr1']).
        """
        key = f"NETWORK_IFACES_{index+1}"
        raw = os.getenv(key, "")
        return [iface.strip() for iface in raw.split(",") if iface.strip()]
