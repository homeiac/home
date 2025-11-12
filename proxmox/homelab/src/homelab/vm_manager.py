#!/usr/bin/env python3
"""
src/homelab/vm_manager.py

Provision Ubuntu cloud-init VMs on Proxmox via API + CLI, using a pre-downloaded .img.
"""

import os
import sys
import time
from typing import Any, Optional

import paramiko

from homelab.config import Config
from homelab.health_checker import VMHealthChecker
from homelab.proxmox_api import ProxmoxClient
from homelab.resource_manager import ResourceManager


class VMManager:
    """Handles cloud-init VM creation on Proxmox using a raw .img disk."""

    @staticmethod
    def vm_exists(proxmox: Any, node_name: str) -> Optional[int]:
        """Return existing vmid if a VM matching the name template exists, else None."""
        expected = Config.VM_NAME_TEMPLATE.format(node=node_name.replace("_", "-"))
        for vm in proxmox.nodes(node_name).qemu.get():
            if vm.get("name") == expected:
                return int(vm["vmid"])
        return None

    @staticmethod
    def delete_vm(proxmox: Any, node_name: str, vmid: int) -> bool:
        """
        Delete VM if it exists.

        Args:
            proxmox: Proxmox API client
            node_name: Node hostname
            vmid: VM ID to delete

        Returns:
            True if VM was deleted, False if it didn't exist
        """
        try:
            # Check if VM exists
            status = proxmox.nodes(node_name).qemu(vmid).status.current.get()

            # Stop VM if running
            if status.get("status") == "running":
                print(f"⏹️  Stopping VM {vmid}")
                proxmox.nodes(node_name).qemu(vmid).status.stop.post()

                # Wait for VM to stop (max 30 seconds)
                timeout = time.time() + 30
                while time.time() < timeout:
                    st = proxmox.nodes(node_name).qemu(vmid).status.current.get()
                    if st.get("status") == "stopped":
                        break
                    time.sleep(2)

            # Delete VM
            print(f"🗑️  Deleting VM {vmid}")
            proxmox.nodes(node_name).qemu(vmid).delete()
            time.sleep(2)  # Give Proxmox time to process

            return True

        except Exception as e:
            # VM doesn't exist
            print(f"ℹ️  VM {vmid} does not exist on {node_name}")
            return False

    @staticmethod
    def get_next_available_vmid(proxmox: Any) -> int:
        """Find the next free VMID using cluster-wide resources query."""
        used = set()

        # Use cluster resources API to get ALL VMs/CTs (including offline nodes)
        try:
            resources = proxmox.cluster.resources.get(type='vm')
            for resource in resources:
                used.add(int(resource['vmid']))
        except Exception:
            # Fallback to per-node query (skip offline nodes)
            for n in proxmox.nodes.get():
                nodename = n["node"]
                node_status = n.get("status", "unknown")

                # Skip offline nodes to avoid connection errors
                if node_status != "online":
                    continue

                for vm in proxmox.nodes(nodename).qemu.get():
                    used.add(int(vm["vmid"]))
                for ct in proxmox.nodes(nodename).lxc.get():
                    used.add(int(ct["vmid"]))

        for candidate in range(100, 9999):
            if candidate not in used:
                return candidate
        raise RuntimeError("No available VMIDs found")

    @staticmethod
    def _import_disk_via_cli(host: str, vmid: int, img_path: str, storage: str) -> None:
        """
        SSH into the Proxmox host and run 'qm importdisk' to import the cloud-init image.
        """
        ssh_user = os.getenv("SSH_USER", "root")
        ssh_key = os.path.expanduser(os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa"))

        print(f"💾 Importing {os.path.basename(img_path)} → {storage} on {host}")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=ssh_user, key_filename=ssh_key)

        cmd = f"qm importdisk {vmid} {img_path} {storage}"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()

        if out:
            print(out)
        if err:
            print(f"ERROR importing disk: {err}", file=sys.stderr)

        ssh.close()

    @staticmethod
    def _resize_disk_via_cli(host: str, vmid: int, disk: str, size: str) -> None:
        """
        SSH into the Proxmox host and run 'qm resize' to grow the VM disk.
        """
        ssh_user = os.getenv("SSH_USER", "root")
        ssh_key = os.path.expanduser(os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa"))

        print(f"🔧 Resizing {disk} of VM {vmid} on {host} → {size}")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=ssh_user, key_filename=ssh_key)

        cmd = f"qm resize {vmid} {disk} {size}"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()

        if out:
            print(out)
        if err:
            print(f"ERROR resizing disk: {err}", file=sys.stderr)

        ssh.close()

    @staticmethod
    def create_or_update_vm() -> None:
        """
        Loop through all nodes in Config.get_nodes(), create missing VMs
        using a cloud-init .img, and start them.
        """
        for idx, node in enumerate(Config.get_nodes()):
            name = node["name"]
            storage = node["img_storage"]

            if not storage:
                print(f"⚠️  Skipping node {name!r}: no storage defined.")
                continue

            # Try to connect to node, skip if offline
            try:
                client = ProxmoxClient(name)
                proxmox = client.proxmox
            except Exception as e:
                print(f"⚠️  Skipping node {name!r}: cannot connect ({type(e).__name__})")
                continue

            # 1) Check if VM exists and its health
            try:
                vmid = VMManager.vm_exists(proxmox, name)
            except Exception as e:
                print(f"⚠️  Skipping node {name!r}: error checking VM ({type(e).__name__})")
                continue

            if vmid:
                # VM exists - check health
                try:
                    health_checker = VMHealthChecker(proxmox, name)
                    health = health_checker.check_vm_health(vmid)

                    if health.should_delete:
                        print(f"⚠️  VM {vmid} unhealthy: {health.reason}")
                        print(f"🔄 Deleting and will recreate...")
                        VMManager.delete_vm(proxmox, name, vmid)
                        vmid = None  # Will recreate below
                    else:
                        if health.is_healthy:
                            print(f"✅ VM {Config.VM_NAME_TEMPLATE.format(node=name)} (vmid={vmid}) is healthy, skipping.")
                        else:
                            print(f"⚠️  VM {vmid} unhealthy but won't delete: {health.reason}")
                        continue

                except Exception as e:
                    print(f"⚠️  Error checking VM health: {e}")
                    continue

            # If we get here, need to create VM (either didn't exist or was deleted)

            # 2) Calculate resources
            try:
                status = client.get_node_status()
            except Exception as e:
                print(f"⚠️  Skipping node {name!r}: error getting status ({type(e).__name__})")
                continue
            cpus, memb = ResourceManager.calculate_vm_resources(
                status, node.get("cpu_ratio", 1.0), node.get("memory_ratio", 1.0)
            )
            mem_mb = memb // (1024 * 1024)

            # 3) Allocate VMID & name
            vmid = VMManager.get_next_available_vmid(proxmox)
            vmname = Config.VM_NAME_TEMPLATE.format(node=name)
            print(f"🆕 Creating VM {vmname!r} on {name!r}: {cpus} CPUs, {mem_mb}MB RAM (vmid={vmid})")

            # 4) Build NIC arguments dynamically
            create_args = {
                "vmid": vmid,
                "name": vmname,
                "cores": cpus,
                "memory": mem_mb,
            }
            bridges = Config.get_network_ifaces_for(idx)
            for net_idx, br in enumerate(bridges):
                # e.g. net0="virtio,bridge=vmbr0", net1="virtio,bridge=vmbr1"
                create_args[f"net{net_idx}"] = f"virtio,bridge={br}"

            # Create the VM shell
            proxmox.nodes(name).qemu.create(**create_args)

            # 5) Import the raw .img via CLI on the Proxmox host
            img_path = f"/var/lib/vz/template/iso/{Config.ISO_NAME}"
            VMManager._import_disk_via_cli(host=name, vmid=vmid, img_path=img_path, storage=storage)

            # 6) Attach imported disk, cloud-init drive, enable guest agent
            proxmox.nodes(name).qemu(vmid).config.post(
                scsihw="virtio-scsi-pci",
                scsi0=f"{storage}:vm-{vmid}-disk-0",
                ide2=f"{storage}:cloudinit",
                boot="c",
                bootdisk="scsi0",
                agent=1,
            )

            VMManager._resize_disk_via_cli(host=name, vmid=vmid, disk="scsi0", size=os.getenv("VM_DISK_SIZE", "200G"))

            cloud_cfg = "user=local:snippets/install-k3sup-qemu-agent.yaml"

            # 7) Configure cloud-init: user, SSH key, network
            proxmox.nodes(name).qemu(vmid).config.post(
                ciuser=Config.CLOUD_USER,
                cipassword=Config.CLOUD_PASSWORD,
                sshkeys=Config.SSH_PUBKEY,
                ipconfig0=Config.CLOUD_IP_CONFIG,
                cicustom=cloud_cfg,
            )

            # 8) Start the VM
            print(f"▶️  Starting VM {vmid}")
            proxmox.nodes(name).qemu(vmid).status.start.post()

            # 9) Wait for VM to report as running
            deadline = time.time() + Config.VM_START_TIMEOUT
            while time.time() < deadline:
                st = proxmox.nodes(name).qemu(vmid).status.current.get()
                if st.get("status") == "running":
                    print(f"✅ VM {vmname!r} (vmid={vmid}) is running.\n")
                    break
                time.sleep(5)
            else:
                print(f"❌ VM {vmname!r} did not start in time.", file=sys.stderr)


if __name__ == "__main__":
    VMManager.create_or_update_vm()
