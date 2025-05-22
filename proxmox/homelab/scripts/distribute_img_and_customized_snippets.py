#!/usr/bin/env python3
"""distribute_img_snippets.py

Distributes the Ubuntu cloud-init image **and** the snippet files needed to
custom-init each VM.  The primary (jump) host seeded with SSH access is used
as a hop to copy artefacts to every other Proxmox node.

Key improvements
----------------
* `install-k3sup-qemu-agent.yaml` is treated as a *template*; the placeholder
  ``{{ host_name }}`` is rendered per-host so that each VM receives a snippet
  containing its own hostname.
* Helper `render_template` keeps templating dependency-free.
* Helper `upload_regular_file` removes SFTP boiler-plate.
* `upload_snippets_to_primary` now uploads one **rendered** snippet per host
  (named ``<host>-install-k3sup-qemu-agent.yaml``) and copies every other
  snippet only once.
* `distribute_snippets_to_hosts` recognises the per-host filenames and copies
  the right one to each target node.
"""

import os
import sys
import argparse
import tempfile
import paramiko

from pathlib import Path

# Bootstrap project path so we can import Config
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
sys.path.insert(0, SRC_DIR)

from homelab.config import Config  # type: ignore

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
ISO_URL = os.getenv(
    "UBUNTU_IMG_URL",
    "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img",
)
IMAGE_NAME = os.path.basename(ISO_URL)
LOCAL_IMG_DIR = PROJECT_ROOT
REMOTE_ISO_DIR = "/var/lib/vz/template/iso"
LOCAL_SNIPPET_DIR = os.path.join(PROJECT_ROOT, "snippets")
REMOTE_SNIPPET_DIR = "/var/lib/vz/snippets"
TEMPLATE_SNIPPET = "install-k3sup-qemu-agent.yaml"  # the special one


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────
def ssh_connect(host: str):
    """Return a connected Paramiko SSHClient using env vars for auth."""
    user = os.getenv("SSH_USER", "root")
    key = os.path.expanduser(os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa"))
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=user, key_filename=key)
    return client



def render_template(src_path: str, vm_name: str) -> str:
    """
    Read *src_path* and replace every {{ vm_name }} (with or without spaces)
    by *vm_name*.  No third-party libs, no loops.
    """
    text = Path(src_path).read_text(encoding="utf-8")
    return (
        text.replace("{{ vm_name }}", vm_name)
            .replace("{{vm_name}}", vm_name)  # handles the tight form too
    )


def upload_regular_file(ssh: paramiko.SSHClient, local_path: str, remote_path: str):
    """Copy a single file to *already connected* host using SFTP."""
    sftp = ssh.open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()


def file_exists(ssh: paramiko.SSHClient, remote_path: str) -> bool:
    stdin, stdout, _ = ssh.exec_command(
        f"test -f {remote_path} && echo exists || echo missing"
    )
    return "exists" in stdout.read().decode()


def remote_file_exists(
    ssh: paramiko.SSHClient, user: str, host: str, remote_path: str
) -> bool:
    test = (
        f"ssh -o StrictHostKeyChecking=no {user}@{host} "
        f"test -f {remote_path} && echo exists || echo missing"
    )
    stdin, stdout, _ = ssh.exec_command(test)
    return "exists" in stdout.read().decode()


# ─────────────────────────────────────────────────────────────────────────────
# Image distribution
# ─────────────────────────────────────────────────────────────────────────────
def distribute_img(primary: str, *, force: bool = False):
    ssh = ssh_connect(primary)
    user = os.getenv("SSH_USER", "root")

    # ensure ISO dir
    ssh.exec_command(f"mkdir -p {REMOTE_ISO_DIR}")

    # download on primary if missing
    check_cmd = f"test -f {REMOTE_ISO_DIR}/{IMAGE_NAME} && echo exists || echo missing"
    stdin, out, _ = ssh.exec_command(check_cmd)
    if "missing" in out.read().decode():
        print(f"⬇️  Downloading {IMAGE_NAME} on {primary}")
        ssh.exec_command(f"curl -L {ISO_URL} -o {REMOTE_ISO_DIR}/{IMAGE_NAME}")
    else:
        print(f"ℹ️  {IMAGE_NAME} already on {primary}")

    # copy from primary to every other node
    for host in Config.get_nodes():
        host_name = host["name"]
        remote_path = f"{REMOTE_ISO_DIR}/{IMAGE_NAME}"

        exists = remote_file_exists(ssh, user, host_name, remote_path)
        if exists:
            print(f"ℹ️  Skipping {IMAGE_NAME} on {host_name}: already exists")
            continue

        print(f"➡️  Copying {IMAGE_NAME} to {host_name}:{REMOTE_ISO_DIR}")
        scp_cmd = f"scp -o StrictHostKeyChecking=no {remote_path} {user}@{host_name}:{REMOTE_ISO_DIR}/"
        ssh.exec_command(scp_cmd)

    ssh.close()


# ─────────────────────────────────────────────────────────────────────────────
# Snippet distribution
# ─────────────────────────────────────────────────────────────────────────────
def distribute_snippets(primary: str, *, force: bool = False):
    if not os.path.isdir(LOCAL_SNIPPET_DIR):
        print(f"ℹ️  No snippets directory at {LOCAL_SNIPPET_DIR}; skipping.")
        return

    ssh = ssh_connect(primary)
    user = os.getenv("SSH_USER", "root")

    # ensure remote snippet dir on primary
    ssh.exec_command(f"mkdir -p {REMOTE_SNIPPET_DIR}")

    upload_snippets_to_primary(ssh, force)
    distribute_snippets_to_hosts(ssh, user, force)

    ssh.close()


def upload_snippets_to_primary(ssh: paramiko.SSHClient, force: bool):
    """Upload all snippets to the primary.

    • Plain snippets are copied **once**.
    • TEMPLATE_SNIPPET is rendered once **per host**, saved as
      ``<host>-TEMPLATE_SNIPPET`` so we keep them separate.
    """
    snippets = os.listdir(LOCAL_SNIPPET_DIR)
    hosts = Config.get_nodes()

    # 1. Handle template snippet per host
    template_src = os.path.join(LOCAL_SNIPPET_DIR, TEMPLATE_SNIPPET)
    for host in hosts:
        host_name = host["name"]
        rendered = render_template(template_src, host_name)
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tmp:
            tmp.write(rendered)
            tmp_path = tmp.name

        remote_path = f"{REMOTE_SNIPPET_DIR}/{host_name}-{TEMPLATE_SNIPPET}"
        if not force and file_exists(ssh, remote_path):
            print(f"ℹ️  Skipping rendered snippet for {host_name}: already exists")
        else:
            print(f"⬆️  Uploading {host_name}-{TEMPLATE_SNIPPET} to primary")
            upload_regular_file(ssh, tmp_path, remote_path)
        os.unlink(tmp_path)

    # 2. Copy every other snippet exactly once
    for fname in snippets:
        if fname == TEMPLATE_SNIPPET:
            continue  # already handled
        local_path = os.path.join(LOCAL_SNIPPET_DIR, fname)
        remote_path = f"{REMOTE_SNIPPET_DIR}/{fname}"

        if not force and file_exists(ssh, remote_path):
            print(f"ℹ️  Skipping {fname} on primary: already exists")
            continue
        print(f"⬆️  Uploading snippet {fname} to primary")
        upload_regular_file(ssh, local_path, remote_path)


def distribute_snippets_to_hosts(ssh: paramiko.SSHClient, user: str, force: bool):
    """
    Copy snippets from the primary to each node.

    · For TEMPLATE_SNIPPET we **keep a host-specific copy on the primary**
      (e.g.  node1-install-k3sup-qemu-agent.yaml) but deliver it to the
      target host under its original name:  install-k3sup-qemu-agent.yaml.

    · All other snippets are copied verbatim.
    """
    for host in Config.get_nodes():
        host_name = host["name"]

        for fname in os.listdir(LOCAL_SNIPPET_DIR):
            # ── decide the source filename on PRIMARY and the target filename on HOST ──
            if fname == TEMPLATE_SNIPPET:
                remote_fname_primary = f"{host_name}-{TEMPLATE_SNIPPET}"
                remote_fname_target = TEMPLATE_SNIPPET  # ← un-prefixed on host
            else:
                remote_fname_primary = remote_fname_target = fname

            remote_path_primary = f"{REMOTE_SNIPPET_DIR}/{remote_fname_primary}"
            remote_path_target = f"{REMOTE_SNIPPET_DIR}/{remote_fname_target}"

            # skip if the (un-prefixed) file is already on the host
            if not force and remote_file_exists(
                ssh, user, host_name, remote_path_target
            ):
                print(
                    f"ℹ️  Skipping {remote_fname_target} on {host_name}: already exists"
                )
                continue

            print(
                f"➡️  Copying {remote_fname_target} to {host_name}:{REMOTE_SNIPPET_DIR}"
            )
            scp_cmd = (
                f"scp -o StrictHostKeyChecking=no {remote_path_primary} "
                f"{user}@{host_name}:{remote_path_target}"
            )
            stdin, stdout, stderr = ssh.exec_command(scp_cmd)
            if stdout.channel.recv_exit_status() == 0:
                print(f"✅ {remote_fname_target} copied to {host_name}")
            else:
                err = stderr.read().decode().strip()
                print(f"❌ Failed to copy {remote_fname_target} to {host_name}: {err}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry-point
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Distribute cloud-init image and snippets"
    )
    parser.add_argument(
        "-f", "--force", action="store_true", help="Overwrite even if files exist"
    )
    args = parser.parse_args()

    nodes = Config.PVE_IPS  # type: ignore
    if len(nodes) < 2:
        print("❌ Need at least two PVE_IPS (primary + targets).", file=sys.stderr)
        sys.exit(1)

    primary = nodes[1]
    print(f"🔑 Using primary/jump host: {primary}")

    distribute_img(primary, force=args.force)
    distribute_snippets(primary, force=args.force)

    print("🎉 Image and snippets distributed to all nodes.")


if __name__ == "__main__":
    main()
