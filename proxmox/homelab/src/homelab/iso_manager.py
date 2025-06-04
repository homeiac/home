import os
import requests
from homelab.proxmox_api import ProxmoxClient
from homelab.config import Config


class IsoManager:
    """Handles ISO download and upload to Proxmox."""

    @staticmethod
    def download_iso():
        """Download ISO if not already present."""
        if not os.path.isfile(Config.ISO_NAME):
            print(f"Downloading {Config.ISO_NAME} from {Config.ISO_URL}...")
            response = requests.get(Config.ISO_URL, stream=True)
            with open(Config.ISO_NAME, "wb") as iso_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        iso_file.write(chunk)
            print(f"Downloaded {Config.ISO_NAME}.")
        else:
            print(f"ISO {Config.ISO_NAME} already exists locally. Skipping download.")

    @staticmethod
    def upload_iso_to_nodes():
        """Upload ISO to each node's storage."""
        nodes = Config.get_nodes()
        for node in nodes:
            client = ProxmoxClient(node["name"])
            if not any(
                item.get("volid", "").endswith(f"iso/{Config.ISO_NAME}")
                for item in client.get_storage_content(node["storage"])
            ):
                client.upload_iso(node["storage"], Config.ISO_NAME)
                print(f"Uploaded {Config.ISO_NAME} to {node['name']} storage {node['storage']}.")
            else:
                print(f"ISO {Config.ISO_NAME} already exists in {node['name']} storage {node['storage']}. Skipping upload.")
