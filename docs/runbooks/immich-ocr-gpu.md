# Immich OCR on the shared RTX 3070

Issue #217. Flux owns the Immich HelmRelease, dashboards and the bounded host
maintenance Job in `apps/photo-enrichment/gpu-maintenance`. The driver is
installed in Ubuntu VM 105, not the Proxmox host; GPU Operator driver management
remains disabled. Immich, Frigate and Ollama use the existing four scheduling
shares. These shares do not partition VRAM.

## Upgrade and recovery

The desired driver is Ubuntu `580.178.04-0ubuntu0.24.04.1`; the prior loaded driver
was `535.288.01`. Run `scripts/k3s/gpu-driver/generate.py prepare`, review and push
the generated manifests, then reconcile `photo-enrichment-preview`. Preparation
saves installed driver packages and the package plan in
`/var/lib/homelab-gpu-driver/580.178.04/`. It refreshes only Ubuntu's apt sources
because the unrelated retired Coral repository has no Release file. It also
finishes the specifically audited pending kernel 6.8.0-100 configuration.

After the prepare Job succeeds, inspect `apt-plan.txt` for unrelated changes.
Generate the `install` phase, review, commit and reconcile. Installation pins the
NVIDIA source packages, checks modules for the running and next boot kernel, and
schedules one reboot after 30 seconds. Do not deploy Immich's CUDA image until
`nvidia-smi` confirms the new loaded driver and existing GPU services recover.
The maintenance Job is privileged and node-pinned; it has no service account token.

If the driver fails, revert the Immich HelmRelease to its prior CPU image first.
Generate the `rollback` phase and push/reconcile. It installs the locally saved
535 packages and schedules a reboot. If Kubernetes is unavailable on VM 105,
use the Proxmox guest agent (inventory address; never SSH to the VM) to run the
same reviewed rollback script. Never remove the rollback directory until the
upgrade has been accepted. A kernel boot failure requires the VM console and the
prior kernel from GRUB, not another blind driver installation.

## Verification

Run `scripts/knowledge-index/check-immich-acceleration.sh` to inspect ONNX Runtime
providers, OCR model provider logs, VRAM, utilization, pressure and allocation.
CUDA being available alone does not prove OCR is using it: verify the OCR model
session selected CUDAExecutionProvider and that jobs complete without CUDA/OOM
errors. Keep a single ML worker and existing concurrency initially.

Run `scripts/knowledge-index/verify-shared-gpu-services.py --generate` before and
after maintenance. It checks Frigate camera processing and requests a short reply
from the model already loaded in Ollama. The pre-upgrade baseline had two active
cameras and three inactive cameras; Frigate's detector was CPU, despite older
repository descriptions. Do not attribute those pre-existing conditions to CUDA.

Run `scripts/knowledge-index/check-immich-queue.py ocr` and compare sustained
completion rates after model warm-up. Completed OCR jobs include photos with no
text. GPU utilization and memory on the Photo App dashboard are whole-device
measurements, not per-service attribution. The value stream map shows OCR queued
jobs and measured completions/minute; edges represent dependencies, not timing.

`check-immich-observability.py` validates live dashboard queries. Dashboard sources
are `immich_dashboard.py`, `gen-photo-app-dashboard.py` and `gen-dashboard.py`;
regenerate both ConfigMaps after editing. Never hand-edit Grafana's stored copy.
