from proxmoxer import ProxmoxAPI
from homelab.config import Config


class ProxmoxClient:
    """Wrapper around Proxmox API for easy interaction."""

    def __init__(self, host):
        self.host = host

        # Extract API token components
        user_token, self.api_token = Config.API_TOKEN.split('=')
        self.user, self.token_name = user_token.split('!')

        # Initialize ProxmoxAPI with API token
        # self.proxmox = ProxmoxAPI(
        #    host,
        #    user=self.user,
        #    token_name=self.token_name,
        #    token_value=self.api_token,
        #    verify_ssl=False
        # )

        self.proxmox = ProxmoxAPI(
             host,
             user="root@pam",
             password="elder137berry",
             verify_ssl=False
        )

    def get_node_status(self):
        """Retrieve node status information."""
        return self.proxmox.nodes(self.host).status.get()

    def get_storage_content(self, storage):
        """Retrieve storage content."""
        print(f"host: {self.host}")
        return self.proxmox.nodes(self.host).storage(storage).content.get()

    def iso_exists(self, storage):
        """Check if the ISO already exists in Proxmox storage."""
        try:
            storage_content = self.proxmox.nodes(self.host).storage(storage).content.get()
            for item in storage_content:
                if item.get("volid", "").endswith(f"iso/{Config.ISO_NAME}"):
                    print(f"✅ ISO {Config.ISO_NAME} already exists in storage {storage}. Skipping upload.")
                    return True
            return False
        except Exception as e:
            print(f"⚠️ Error checking ISO existence: {e}")
            return False

    def upload_iso(self, storage, iso_path):
        """Upload an ISO to Proxmox storage (only if it does not exist)."""
        if self.iso_exists(storage):
            return  # Skip upload if ISO is already present

        with open(iso_path, "rb") as iso_file:
            self.proxmox.nodes(self.host).storage(storage).upload.post(
                content="iso",
                filename=iso_file
            )
