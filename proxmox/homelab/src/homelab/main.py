from homelab.iso_manager import IsoManager
from homelab.vm_manager import VMManager


def main():
    """Main entry point for the script."""
    IsoManager.download_iso()
    IsoManager.upload_iso_to_nodes()
    VMManager.create_vm()


if __name__ == "__main__":
    main()
