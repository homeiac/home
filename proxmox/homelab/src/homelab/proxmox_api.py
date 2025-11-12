from typing import Any, Dict, List, Optional
import json
import logging
import os

from proxmoxer import ProxmoxAPI
from proxmoxer.core import ResourceException
import paramiko

from homelab.config import Config

logger = logging.getLogger(__name__)


class ProxmoxClient:
    """Wrapper around Proxmox API with CLI fallback for SSL failures."""

    def __init__(self, host: str, verify_ssl: bool = False, use_cli_fallback: bool = True) -> None:
        # Append .maas suffix if not present
        if not host.endswith(".maas"):
            host = host + ".maas"
        self.host = host
        self.cli_mode = False
        self.use_cli_fallback = use_cli_fallback

        # Extract API token components
        if Config.API_TOKEN is None:
            raise ValueError("API_TOKEN environment variable is not set")
        user_token, self.api_token = Config.API_TOKEN.split("=")
        self.user, self.token_name = user_token.split("!")

        # Try to initialize ProxmoxAPI
        try:
            self.proxmox: Optional[ProxmoxAPI] = ProxmoxAPI(
                host, user=self.user, token_name=self.token_name, token_value=self.api_token, verify_ssl=verify_ssl
            )
        except (ResourceException, Exception) as e:
            error_msg = str(e)
            if "SSL" in error_msg or "certificate" in error_msg:
                if use_cli_fallback:
                    logger.warning(f"API connection failed ({error_msg}), using CLI fallback")
                    self.cli_mode = True
                    self.proxmox = None
                else:
                    raise
            else:
                raise

    def _exec_ssh_command(self, command: str) -> Dict[str, Any]:
        """Execute command via SSH and return parsed JSON."""
        ssh_user = os.getenv("SSH_USER", "root")
        ssh_key = os.path.expanduser(os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa"))

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=self.host, username=ssh_user, key_filename=ssh_key)

        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        ssh.close()

        if error:
            logger.error(f"SSH command error: {error}")
            raise RuntimeError(f"Command failed: {error}")

        return json.loads(output)  # type: ignore[no-any-return]

    def get_node_status(self) -> Dict[str, Any]:
        """Retrieve node status information."""
        if self.cli_mode:
            # Use pvesh CLI command
            node_name = self.host.replace(".maas", "")
            command = f"pvesh get /nodes/{node_name}/status --output-format json"
            return self._exec_ssh_command(command)
        else:
            return self.proxmox.nodes(self.host).status.get()  # type: ignore[no-any-return, union-attr]

    def get_storage_content(self, storage: str) -> List[Dict[str, Any]]:
        """Retrieve storage content."""
        if self.proxmox is None:
            raise RuntimeError("Cannot get storage content in CLI mode - not yet implemented")
        print(f"host: {self.host}")
        return self.proxmox.nodes(self.host).storage(storage).content.get()  # type: ignore[no-any-return]

    def iso_exists(self, storage: str) -> bool:
        """Check if the ISO already exists in Proxmox storage."""
        if self.proxmox is None:
            logger.warning("Cannot check ISO existence in CLI mode")
            return False
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

    def upload_iso(self, storage: str, iso_path: str) -> None:
        """Upload an ISO to Proxmox storage (only if it does not exist)."""
        if self.proxmox is None:
            raise RuntimeError("Cannot upload ISO in CLI mode - not yet implemented")
        if self.iso_exists(storage):
            return  # Skip upload if ISO is already present

        with open(iso_path, "rb") as iso_file:
            self.proxmox.nodes(self.host).storage(storage).upload.post(content="iso", filename=iso_file)
