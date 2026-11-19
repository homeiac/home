#!/usr/bin/env python3
"""Temporarily start an intentionally paused Frigate, probe recognition, restore replicas (#217).

Requires explicit operator approval via --allow-temporary-start. Does not change Flux
annotations, other tenants, models, configuration, or the face training library.
"""
import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> None:
    """Preserve and restore the exact replica count even when probes fail."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-temporary-start", action="store_true", required=True)
    parser.add_argument("--keep-running", action="store_true", help="Explicitly retain a ready replica, including for diagnosis after a failed recognition probe")
    parser.add_argument("--warmup-seconds", type=int, default=180)
    args = parser.parse_args()
    env = dict(os.environ, KUBECONFIG=os.environ.get("KUBECONFIG", str(Path.home()/"kubeconfig")))
    base = ["kubectl", "--request-timeout=30s", "-n", "frigate"]
    def run(*args: str) -> str:
        return subprocess.check_output([*base, *args], env=env, text=True)
    original = json.loads(run("get", "deployment", "frigate", "-o", "json"))
    replicas = original["spec"]["replicas"]
    annotations = original["metadata"].get("annotations", {})
    if replicas != 0 or annotations.get("kustomize.toolkit.fluxcd.io/reconcile") != "disabled":
        raise ValueError("Expected paused Frigate with Flux reconciliation disabled; inspect before changing")
    backup = Path(tempfile.mkdtemp(prefix="frigate-validation-"))/"replica-state.json"
    backup.write_text(json.dumps({"replicas":replicas,"annotations":{
        key: annotations.get(key) for key in ("kustomize.toolkit.fluxcd.io/reconcile", "homelab.local/paused-replicas")}}))
    backup.chmod(0o600)
    logging.info("Replica-state backup: %s", backup)
    ready = False
    try:
        logging.info("Temporarily starting only Frigate")
        logging.info(run("scale", "deployment/frigate", "--current-replicas=0", "--replicas=1").strip())
        # The caller can continue reporting progress while this subprocess waits.
        subprocess.run([*base, "rollout", "status", "deployment/frigate", "--timeout=240s"], env=env, check=True)
        ready = True
        subprocess.run([sys.executable, str(Path(__file__).with_name("check-frigate-enrichment.py")), "--recognize-reference", "--warmup-seconds", str(args.warmup_seconds)], env=env, check=True)
    finally:
        desired = 1 if args.keep_running and ready else replicas
        logging.info("Leaving Frigate at %s replicas", desired)
        logging.info(run("scale", "deployment/frigate", "--replicas="+str(desired)).strip())
        restored = json.loads(run("get", "deployment", "frigate", "-o", "json"))
        if restored["spec"]["replicas"] != desired:
            raise RuntimeError("Replica restoration failed")
        for key in ("kustomize.toolkit.fluxcd.io/reconcile", "homelab.local/paused-replicas"):
            if restored["metadata"].get("annotations", {}).get(key) != annotations.get(key):
                raise RuntimeError("Pause annotation changed concurrently")
        logging.info("Desired replica count verified; existing Flux pause annotations preserved")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
