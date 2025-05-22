from dotenv import load_dotenv
import os


class Config:
    """Loads and manages configuration from environment variables."""

    load_dotenv()

    API_TOKEN = os.getenv("API_TOKEN")
    ISO_NAME = os.getenv("ISO_NAME", "ubuntu-24.04.2-desktop-amd64.iso")
    ISO_URL = os.getenv(
        "ISO_URL",
        "https://releases.ubuntu.com/24.04.2/ubuntu-24.04.2-desktop-amd64.iso",
    )

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
                    "cpu_ratio": float(os.getenv(f"CPU_RATIO_{index}")),
                    "memory_ratio": float(os.getenv(f"MEMORY_RATIO_{index}")),
                }
            )
            index += 1
        return nodes
