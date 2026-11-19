#!/usr/bin/env python3
"""Read GPU/tenant health during shared captioning and face recognition; emit no camera URLs (#217)."""
import json
import logging
import os
from pathlib import Path
import re
import subprocess


def main() -> None:
    """Report readiness, restarts, memory, temperature and categorized recent errors."""
    env = dict(os.environ, KUBECONFIG=os.environ.get("KUBECONFIG", str(Path.home()/"kubeconfig")))
    def run(*args: str) -> str:
        return subprocess.check_output(["kubectl", "--request-timeout=20s", *args], env=env, text=True, stderr=subprocess.DEVNULL)
    for namespace, deployment in (("frigate", "frigate"), ("ollama", "ollama-gpu")):
        data = json.loads(run("-n", namespace, "get", "deployment", deployment, "-o", "json"))
        logging.info("Tenant %s: desired=%s ready=%s", deployment, data["spec"]["replicas"], data.get("status", {}).get("readyReplicas",0))
        selector = ",".join(k+"="+v for k,v in data["spec"]["selector"]["matchLabels"].items())
        pods = json.loads(run("-n", namespace, "get", "pods", "-l", selector, "-o", "json"))
        logging.info("%s container states: %s", deployment, json.dumps([{
            "ready": c.get("ready"), "restarts": c.get("restartCount"),
            "last_reason": c.get("lastState",{}).get("terminated",{}).get("reason")}
            for p in pods["items"] for c in p.get("status",{}).get("containerStatuses",[])]))
        if data.get("status",{}).get("readyReplicas",0):
            logs = run("-n", namespace, "logs", "deployment/"+deployment, "--since=5m", "--tail=1000")
            patterns = {"out_of_memory": r"out of memory|CUDA_ERROR_OUT_OF_MEMORY|OOMKilled",
                        "model_build_complete": r"Finished building ArcFace model",
                        "traceback": r"Traceback \(most recent call last\)",
                        "cuda_error": r"CUDA.*[Ee]rror|CUDNN.*[Ee]rror",
                        "model_load_failure": r"Failed to load|Failed to create.*session"}
            logging.info("%s recent log signals: %s", deployment, json.dumps({k:len(re.findall(p,logs)) for k,p in patterns.items()}))
            if namespace == "frigate":
                model_state = run("-n", namespace, "exec", "deployment/"+deployment, "--", "python3", "-c",
                    "import json; from pathlib import Path; root=Path('/config/model_cache'); "
                    "print(json.dumps({str(p.relative_to(root)):p.stat().st_size for p in root.rglob('*') "
                    "if p.is_file() and ('face' in str(p.relative_to(root)).lower() or 'landmark' in p.name.lower())}))")
                logging.info("Face model cache sizes: %s", model_state.strip())
                providers = run("-n", namespace, "exec", "deployment/"+deployment, "--", "python3", "-c",
                                "import onnxruntime; print(onnxruntime.get_available_providers())")
                logging.info("Frigate available ONNX providers: %s", providers.strip())
    gpu = run("-n", "ollama", "exec", "deployment/ollama-gpu", "--", "nvidia-smi",
              "--query-gpu=utilization.gpu,memory.used,memory.free,temperature.gpu,power.draw", "--format=csv,noheader")
    logging.info("GPU utilization, used/free VRAM, temperature, power: %s", gpu.strip())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
