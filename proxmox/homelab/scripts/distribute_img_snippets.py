#!/usr/bin/env python3
import os
import sys
import argparse
import paramiko

# Bootstrap project path so we can import Config
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
sys.path.insert(0, SRC_DIR)

from homelab.config import Config

# Constants
ISO_URL = os.getenv(
    "ISO_URL",
    "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img",
)
IMAGE_NAME = os.path.basename(ISO_URL)
LOCAL_IMG_DIR = PROJECT_ROOT
REMOTE_ISO_DIR = "/var/lib/vz/template/iso"
LOCAL_SNIPPET_DIR = os.path.join(PROJECT_ROOT, "snippets")
REMOTE_SNIPPET_DIR = "/var/lib/vz/snippets"


def ssh_connect(host):
    user = os.getenv("SSH_USER", "root")
    key = os.path.expanduser(os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa"))
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=user, key_filename=key)
    return client


def distribute_img(primary, force=False):
    ssh = ssh_connect(primary)
    user = os.getenv("SSH_USER", "root")

    # ensure ISO dir
    ssh.exec_command(f"mkdir -p {REMOTE_ISO_DIR}")

    # download if missing
    check_cmd = f"test -f {REMOTE_ISO_DIR}/{IMAGE_NAME} && echo exists || echo missing"
    stdin, out, _ = ssh.exec_command(check_cmd)
    if "missing" in out.read().decode():
        print(f"⬇️  Downloading {IMAGE_NAME} on {primary}")
        ssh.exec_command(f"curl -L {ISO_URL} -o {REMOTE_ISO_DIR}/{IMAGE_NAME}")
    else:
        print(f"ℹ️  {IMAGE_NAME} already on {primary}")

    # scp to all hosts
    for host in Config.get_nodes():
        remote_path = f"{REMOTE_ISO_DIR}/{IMAGE_NAME}"
        # skip if exists and not forcing
        if not force:
            test = f"ssh -o StrictHostKeyChecking=no {user}@{host} test -f {remote_path} && echo exists || echo missing"
            stdin, out, _ = ssh.exec_command(test)
            if "exists" in out.read().decode():
                print(f"ℹ️  Skipping {IMAGE_NAME} on {host}: already exists")
                continue
        print(f"➡️  Copying {IMAGE_NAME} to {host}:{REMOTE_ISO_DIR}")
        scp_cmd = (
            f"scp -o StrictHostKeyChecking=no "
            f"{remote_path} {user}@{host}:{REMOTE_ISO_DIR}/"
        )
        ssh.exec_command(scp_cmd)

    ssh.close()


def distribute_snippets(primary, force=False):
    if not os.path.isdir(LOCAL_SNIPPET_DIR):
        print(f"ℹ️  No snippets directory at {LOCAL_SNIPPET_DIR}; skipping.")
        return

    ssh = ssh_connect(primary)
    user = os.getenv("SSH_USER", "root")

    # ensure snippets dir
    ssh.exec_command(f"mkdir -p {REMOTE_SNIPPET_DIR}")

    upload_snippets_to_primary(ssh, force)
    distribute_snippets_to_hosts(ssh, user, force)

    ssh.close()


def render_template(src_path: str, context: dict) -> str:
    """Read src_path, replace all {{ key }} with context[key], and return the result."""
    text = open(src_path).read()
    for key, val in context.items():
        text = text.replace(f"{{{{ {key} }}}}", val)
    return text


def upload_snippets_to_primary(ssh, force):
    for fname in os.listdir(LOCAL_SNIPPET_DIR):
        local_path = os.path.join(LOCAL_SNIPPET_DIR, fname)
        remote_path = f"{REMOTE_SNIPPET_DIR}/{fname}"
        if not force and file_exists(ssh, remote_path):
            print(f"ℹ️  Skipping upload of {fname} on primary: already exists")
            continue
        print(f"⬆️  Uploading snippet {fname} to primary:{REMOTE_SNIPPET_DIR}")
        sftp = ssh.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()


def distribute_snippets_to_hosts(ssh, user, force):
    for host in Config.get_nodes():
        host_name = host["name"]
        for fname in os.listdir(LOCAL_SNIPPET_DIR):
            remote_path = f"{REMOTE_SNIPPET_DIR}/{fname}"

            if not force and remote_file_exists(ssh, user, host_name, remote_path):
                print(f"ℹ️  Skipping {fname} on {host_name}: already exists")
                continue
            print(f"➡️  Copying snippet {fname} to {host_name}:{REMOTE_SNIPPET_DIR}")
            scp_cmd = (
                f"scp -o StrictHostKeyChecking=no "
                f"{remote_path} {user}@{host_name}:{REMOTE_SNIPPET_DIR}/"
            )
            try:
                print(f"🔄 Executing SCP command: {scp_cmd}")
                stdin, stdout, stderr = ssh.exec_command(scp_cmd)
                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0:
                    print(
                        f"✅ Successfully copied snippet {fname} to {host}:{REMOTE_SNIPPET_DIR}"
                    )
                else:
                    error_message = stderr.read().decode().strip()
                    print(
                        f"❌ Failed to copy snippet {fname} to {host}:{REMOTE_SNIPPET_DIR}. Error: {error_message}"
                    )
            except Exception as e:
                print(
                    f"❌ Exception occurred while copying snippet {fname} to {host}:{REMOTE_SNIPPET_DIR}: {e}"
                )


def file_exists(ssh, remote_path):
    test = f"test -f {remote_path} && echo exists || echo missing"
    stdin, out, _ = ssh.exec_command(test)
    return "exists" in out.read().decode()


def remote_file_exists(ssh, user, host, remote_path):
    test = f"ssh -o StrictHostKeyChecking=no {user}@{host} test -f {remote_path} && echo exists || echo missing"
    stdin, out, _ = ssh.exec_command(test)
    return "exists" in out.read().decode()


def main():
    parser = argparse.ArgumentParser(
        description="Distribute cloud-init image and snippets"
    )
    parser.add_argument(
        "-f", "--force", action="store_true", help="Overwrite even if files exist"
    )
    args = parser.parse_args()

    nodes = Config.PVE_IPS
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
