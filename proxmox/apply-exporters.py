#!/usr/bin/env python3
"""
apply_exporters.py  —  copy & run exporter-desired.sh on many hosts.

* INI‐style inventory (allow_no_value = True).
* Skips [k3s] group by default — those nodes already run the DaemonSet exporter.
* Override skip with --include-k3s.

Examples
--------
# Real run on every NON-k3s group
python apply_exporters.py

# Real run only on [proxmox]
python apply_exporters.py --group proxmox

# Force run even on [k3s] (if you really need it)
python apply_exporters.py --include-k3s
"""
import argparse, configparser, pathlib, subprocess, sys

SCRIPT = "exporter-desired.sh"
DEFAULT_SKIP = {"k3s"}          # groups NEVER processed unless --include-k3s

# ----- helper ----------------------------------------------------
def banner(msg, col):
    colours = {"y":33, "g":32, "r":31, "b":34}
    print(f"\033[{colours.get(col,0)}m{msg}\033[0m")

def parse_inventory(path, wanted_group=None, skip_groups=None):
    cp = configparser.ConfigParser(allow_no_value=True, delimiters=("="," "))
    cp.optionxform = str                       # preserve case
    cp.read(path)
    hosts = []
    for section in cp.sections():
        if skip_groups and section in skip_groups: continue
        if wanted_group and section != wanted_group: continue
        for host in cp[section]:
            hosts.append((section, host.strip()))
    return hosts

# ----- main -------------------------------------------------------
def main():
    a = argparse.ArgumentParser()
    a.add_argument("--group", help="only this [section]")
    a.add_argument("--dry-run", action="store_true", help="simulate only")
    a.add_argument("--include-k3s", action="store_true",
                   help="process [k3s] group (normally skipped)")
    a.add_argument("inventory", nargs="?", default="inventory.txt")
    args = a.parse_args()

    inv = pathlib.Path(args.inventory).expanduser()
    if not inv.exists():
        sys.exit(f"Inventory file {inv} not found")

    skip = set() if args.include_k3s else DEFAULT_SKIP
    hosts = parse_inventory(inv, args.group, skip)

    banner(f"*** Inventory: {inv} | Group: {args.group or '<all>'} |"
           f" Dry-run: {args.dry_run} | Skip: {skip}", "b")

    for grp, host in hosts:
        banner(f"\n>>> [{grp}] {host} — deploying", "y")
        if args.dry_run:
            print(f"   DRY-RUN scp {SCRIPT} root@{host}:/tmp/")
            print(f"   DRY-RUN ssh root@{host} bash /tmp/{SCRIPT}")
            banner(f"<<< [{grp}] {host} — simulated", "b")
            continue

        if subprocess.run(["scp","-q",SCRIPT,f"root@{host}:/tmp/"]).returncode:
            banner(f"<<< [{grp}] {host} — SCP FAILED", "r"); continue
        if subprocess.run(["ssh","-tt",f"root@{host}",f"bash /tmp/{SCRIPT}"]).returncode:
            banner(f"<<< [{grp}] {host} — REMOTE SCRIPT FAILED", "r")
        else:
            banner(f"<<< [{grp}] {host} — SUCCESS", "g")

if __name__ == "__main__":
    main()

