#!/usr/bin/env python3
import os
import sys
import argparse
import paramiko

# Ensure we can import our library
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
sys.path.insert(0, SRC_DIR)

from homelab.config import Config


def run_on_host(hostname, user, key_path, commands):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=hostname, username=user, key_filename=key_path)
    for cmd in commands:
        print(f"\n[{hostname}]$ {cmd}")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        if out:
            print(out)
        if err:
            print(f"ERROR: {err}", file=sys.stderr)
    ssh.close()


def main():
    parser = argparse.ArgumentParser(
        description="SSH into all nodes from Config.get_nodes() and run commands."
    )
    parser.add_argument(
        "-c", "--cmd", action="append", required=True,
        help="Command to run on each host (repeatable)"
    )
    args = parser.parse_args()

    # Load nodes from environment via Config
    nodes = Config.get_nodes()
    if not nodes:
        print("❌ No nodes found. Please set NODE_1, NODE_2, etc. in your environment.", file=sys.stderr)
        sys.exit(1)

    # SSH credentials (defaults)
    ssh_user = os.getenv("SSH_USER", "root")
    ssh_key = os.getenv("SSH_KEY_PATH", os.path.expanduser("~/.ssh/id_rsa"))

    for node in nodes:
        hostname = node["name"]
        print(f"\n=== Connecting to {hostname} ===")
        run_on_host(hostname, ssh_user, ssh_key, args.cmd)

if __name__ == "__main__":
    main()
