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
If the container cannot reach the host systemd bus, run the guarded
`reboot-guest.py` helper with `CB_HOST` set from the inventory. It checks the
GitOps install marker and both modules before requesting the reboot through the
existing Proxmox guest agent; it adds no persistent process-namespace access.
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
session selected CUDAExecutionProvider or nv_tensorrt_rtx and that jobs complete without CUDA/OOM
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

## Validated rollout (2026-11-20)

Driver 580.178.04 loaded on kernel 6.8.0-100 after a guarded guest-agent reboot.
Both the current and next-boot DKMS modules were verified before the reboot.
Frigate's two previously active streams recovered; Ollama `gemma4:e2b` returned
`OK` through `/api/chat` both before and after enabling Immich. Its cold model
load took several minutes, then photo summaries resumed.

Immich v3.4.2-cuda automatically selects `nv_tensorrt_rtx` for both PP-OCRv5_mobile
models. It compiles/cache-specializes different image and text-box dimensions;
initial throughput includes these warm-up stalls. The existing cache PVC retains
those artifacts. Do not claim steady-state speed from the initial warm-up rate.
The retained OCR failed queue stayed at zero, but the native failed-attempt counter
recorded worker-outage errors. A zero retained queue must not be treated as no
errors. The dashboard now shows the actual failed-attempt rate, and recovery
requires a missing-only OCR scan after the worker is healthy.

An empty thumbnail queue can have no completion counter immediately after a
server restart. The dashboard shows zero throughput only when telemetry confirms
the backlog is empty; otherwise an absent counter remains unknown.

OCR batch size is capped at 1 via `MACHINE_LEARNING_MAX_BATCH_SIZE__OCR`. The
initial default of 6 spent minutes compiling batch/width variants and completed
only a handful of jobs. A fixed batch reuses already warmed graphs and bounds
memory on the shared 8 GB GPU; model weights and recognition thresholds are unchanged.

The GitOps `immich-ocr-recovery` Job schedules one native `OcrQueueAll` handler
with `force:false`, through the bundled BullMQ client. It never clears jobs or
writes Immich tables. Its fixed job ID and retained completion record make a
repeat reconciliation idempotent. It runs behind existing FIFO work and discovers
only missing OCR results. This avoids creating new administrator credentials.

Final verification at 23:40 UTC: the missing-only recovery scan completed and
processed 302 additional assets. A read-only database audit found 75,727 of
75,728 eligible assets with `ocrAt` set. The remaining asset
`a8326034-31bb-48c7-8249-721a96830738` has no `asset_file` preview; the native OCR
handler returns Failed before calling ML in that case. It is not a GPU failure.
The cumulative failed-attempt counter was 413 (including maintenance failures
and the missing-preview retry), so do not report the rollout as error-free.
Use `audit-immich-ocr.py` to distinguish missing results from an empty queue.

The measured peak five-minute success rate was approximately 367 jobs/minute
after warm-up; this is not a controlled CPU/GPU speedup benchmark. Both OCR models
selected `nv_tensorrt_rtx` again during recovery. The ML worker's 22:54 shutdown
was its documented inactivity unload, not a container crash. Final ML container
restart count was zero, GPU memory usage about 3 GiB, and all three service
deployments were available. Frigate retained its two active source streams and
Ollama returned `OK` from a real chat request. All 46 dashboard queries passed
live validation; the OCR/GPU panels were also checked in Chrome.

## Video transcoding

The Immich HelmRelease assigns the fourth existing GPU share to `immich-server`.
The chart mounts the application configuration with NVENC encoding and software
decoding. The upload storage template is copied from the prior database setting.
With a configuration file mounted, change system settings through Git; the admin
UI displays them read-only. The default video conversion policy still applies.

The Photo App dashboard shows video conversion backlog, job outcomes, and shared
RTX video encoder activity. Job success includes remuxes and software fallback.
To confirm hardware encoding on an Immich job, find its NVENC start and success
messages in server logs and check that no retry or fallback occurred for that job.
Rollback by reverting the server GPU assignment and chart configuration together.
