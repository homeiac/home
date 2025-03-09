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
        self.proxmox = ProxmoxAPI(
            host,
            user=self.user,
            token_name=self.token_name,
            token_value=self.api_token,
            verify_ssl=False
        )

    def get_node_status(self):
        """Retrieve node status information."""
        return self.proxmox.nodes(self.host).status.get()

    def get_storage_content(self, storage):
        """Retrieve storage content."""
        return self.proxmox.nodes(self.host).storage(storage).content.get()

    def upload_iso(self, storage, iso_path):
        """Upload an ISO to Proxmox storage."""
        with open(iso_path, "rb") as iso_file:
            self.proxmox.nodes(self.host).storage(storage).upload.post(
                content="iso",
                filename=Config.ISO_NAME,
                file=iso_file
            )
