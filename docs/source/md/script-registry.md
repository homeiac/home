# Script Registry - Homelab Operations

**Last Updated:** 2025-12-14
**Maintainer:** homeiac/home repository
**Purpose:** Central registry of all operational scripts for K3s, Home Assistant, Frigate, and infrastructure management

---

## Table of Contents

1. [K3s Operations](#k3s-operations)
2. [Home Assistant Operations](#home-assistant-operations)
3. [Frigate NVR Operations](#frigate-nvr-operations)
4. [Coral TPU Automation](#coral-tpu-automation)
5. [Frigate Coral LXC Deployment](#frigate-coral-lxc-deployment)
6. [Package Detection & LLM Vision](#package-detection--llm-vision)
7. [Voice Assistant Debugging](#voice-assistant-debugging)
8. [Infrastructure & Utilities](#infrastructure--utilities)

---

## K3s Operations

**CRITICAL:** SSH DOES NOT WORK to K3s VMs. Always use `qm guest exec` via these wrapper scripts.

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/k3s/exec-still-fawn.sh` | Execute commands on still-fawn (VMID 108) | `./exec-still-fawn.sh "uptime"` | [K3s SSH Management](../../proxmox/homelab/docs/k3s-ssh-management.md) |
| `scripts/k3s/exec-pumped-piglet.sh` | Execute commands on pumped-piglet (VMID 105) | `./exec-pumped-piglet.sh "kubectl get pods"` | [K3s SSH Management](../../proxmox/homelab/docs/k3s-ssh-management.md) |
| `scripts/k3s/exec.sh` | Generic exec wrapper for any K3s node | `./exec.sh still-fawn "top"` | [K3s SSH Management](../../proxmox/homelab/docs/k3s-ssh-management.md) |
| `scripts/k3s/diagnose-cpu.sh` | Full CPU diagnostics (uptime, top, memory, I/O) | `./diagnose-cpu.sh still-fawn` | [K3s ETCD Performance](k3s-etcd-performance-tuning-runbook.md) |
| `scripts/k3s/frigate-cpu-stats.sh` | Monitor Frigate container CPU usage | `./frigate-cpu-stats.sh` | [Frigate K8s Migration](blog-frigate-016-k8s-migration.md) |
| `scripts/k3s/backup-frigate-config.sh` | Backup Frigate config from K8s ConfigMap | `./backup-frigate-config.sh` | [Frigate Storage Migration](frigate-storage-migration-report.md) |
| `scripts/k3s/export-frigate-zone.sh` | Export Frigate zone configuration | `./export-frigate-zone.sh` | [Frigate HomeAssistant Integration](frigate-homeassistant-integration-guide.md) |
| `scripts/k3s/doorbell-motion-analysis.sh` | Analyze doorbell motion zones | `./doorbell-motion-analysis.sh` | - |
| `scripts/k3s/test-doorbell-mask.sh` | Test doorbell motion mask | `./test-doorbell-mask.sh` | - |
| `scripts/k3s/apply-doorbell-mask.sh` | Apply doorbell motion mask | `./apply-doorbell-mask.sh` | - |

### Common K3s Workflows

```bash
# Check CPU consumption on still-fawn
./scripts/k3s/diagnose-cpu.sh still-fawn

# Execute kubectl command on pumped-piglet
./scripts/k3s/exec-pumped-piglet.sh "kubectl get pods -A"

# Backup Frigate configuration before changes
./scripts/k3s/backup-frigate-config.sh
```

---

## Home Assistant Operations

**CRITICAL:** HAOS has NO SSH. Always use API or `qm guest exec` via these scripts.

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/haos/check-ha-api.sh` | Verify HA API is responding | `./check-ha-api.sh` | - |
| `scripts/haos/restart-ha.sh` | Restart Home Assistant core | `./restart-ha.sh` | - |
| `scripts/haos/guest-exec.sh` | Execute command in HAOS VM (VMID 116) | `./guest-exec.sh "cat /config/automations.yaml"` | - |
| `scripts/haos/list-integrations.sh` | List all configured integrations | `./list-integrations.sh` | - |
| `scripts/haos/backup-dashboard.sh` | Backup Lovelace dashboard | `./backup-dashboard.sh` | - |
| `scripts/haos/fix-frigate-dashboard.sh` | Fix Frigate dashboard after migration | `./fix-frigate-dashboard.sh` | [HA Frigate DNS Migration](../../docs/troubleshooting/2025-12-13-action-log-ha-frigate-dns-migration.md) |

### Common HAOS Workflows

```bash
# Verify API before making changes
./scripts/haos/check-ha-api.sh

# Restart HA after automation changes
./scripts/haos/restart-ha.sh

# Check integration configuration
./scripts/haos/list-integrations.sh
```

**Environment Variables:**
- `HA_TOKEN`: Required for API access (stored in `proxmox/homelab/.env`)
- `HA_URL`: Home Assistant URL (default: `http://192.168.4.240:8123`)

---

## Frigate NVR Operations

### Migration & Verification Scripts

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/frigate/migrate.sh` | Migrate Frigate from LXC to K8s | `./migrate.sh` | [Frigate Server Migration](blog-frigate-server-migration.md) |
| `scripts/frigate/verify-frigate-k8s.sh` | Verify Frigate is running in K8s | `./verify-frigate-k8s.sh` | [Frigate K8s Migration](blog-frigate-016-k8s-migration.md) |
| `scripts/frigate/check-ha-frigate-integration.sh` | Check HA Frigate integration status | `./check-ha-frigate-integration.sh` | [Frigate HomeAssistant Integration](frigate-homeassistant-integration-guide.md) |
| `scripts/frigate/update-ha-frigate-url.sh` | Update Frigate URL in HA integration | `./update-ha-frigate-url.sh` | [HA Frigate IP Migration](../../docs/troubleshooting/2025-12-13-action-log-ha-frigate-ip-migration.md) |
| `scripts/frigate/switch-ha-to-k8s-frigate.sh` | Switch HA to K8s Frigate instance | `./switch-ha-to-k8s-frigate.sh` | [Frigate Server Migration](blog-frigate-server-migration.md) |

### Rollback & Troubleshooting

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/frigate/rollback-to-still-fawn.sh` | Rollback to LXC Frigate | `./rollback-to-still-fawn.sh` | [Frigate Server Migration](blog-frigate-server-migration.md) |
| `scripts/frigate/shutdown-still-fawn-frigate.sh` | Shutdown LXC Frigate instance | `./shutdown-still-fawn-frigate.sh` | [Frigate Server Migration](blog-frigate-server-migration.md) |

### Storage Management (3TB ZFS Pool)

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/frigate/investigate-3tb-still-fawn.sh` | Check 3TB pool status on still-fawn | `./investigate-3tb-still-fawn.sh` | [Frigate Storage Migration](frigate-storage-migration-report.md) |
| `scripts/frigate/investigate-3tb-pumped-piglet.sh` | Check 3TB pool status on pumped-piglet | `./investigate-3tb-pumped-piglet.sh` | [Frigate Storage Migration](frigate-storage-migration-report.md) |
| `scripts/frigate/unmount-3tb-still-fawn.sh` | Unmount 3TB pool from still-fawn | `./unmount-3tb-still-fawn.sh` | [Frigate Storage Migration](frigate-storage-migration-report.md) |
| `scripts/frigate/force-export-3tb-still-fawn.sh` | Force export 3TB pool from still-fawn | `./force-export-3tb-still-fawn.sh` | [Frigate Storage Migration](frigate-storage-migration-report.md) |
| `scripts/frigate/mount-3tb-pumped-piglet.sh` | Mount 3TB pool on pumped-piglet | `./mount-3tb-pumped-piglet.sh` | [Frigate Storage Migration](frigate-storage-migration-report.md) |
| `scripts/frigate/check-pool-status.sh` | Check ZFS pool health | `./check-pool-status.sh` | [Frigate Storage Migration](frigate-storage-migration-report.md) |
| `scripts/frigate/cleanup-still-fawn-pool-cache.sh` | Clean ZFS pool cache on still-fawn | `./cleanup-still-fawn-pool-cache.sh` | [Frigate Storage Migration](frigate-storage-migration-report.md) |
| `scripts/frigate/reboot-still-fawn.sh` | Reboot still-fawn host | `./reboot-still-fawn.sh` | - |

### Model & Detection

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/frigate/build-yolov9-onnx.sh` | Build YOLOv9 ONNX model | `./build-yolov9-onnx.sh` | [Frigate ONNX GPU Detection](blog-frigate-onnx-gpu-detection.md) |

### Common Frigate Workflows

```bash
# Verify Frigate is healthy in K8s
./scripts/frigate/verify-frigate-k8s.sh

# Check Home Assistant integration status
./scripts/frigate/check-ha-frigate-integration.sh

# Storage migration workflow
./scripts/frigate/investigate-3tb-still-fawn.sh
./scripts/frigate/unmount-3tb-still-fawn.sh
./scripts/frigate/mount-3tb-pumped-piglet.sh
./scripts/frigate/check-pool-status.sh
```

---

## Coral TPU Automation

**WARNING:** NEVER test Coral from host while LXC has it mounted! This corrupts Coral state ("did not claim interface 0").

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/coral-tpu-automation/comprehensive-check.sh` | Full Coral TPU diagnostics | `./comprehensive-check.sh` | [Coral TPU Automation Runbook](coral-tpu-automation-runbook.md) |
| `scripts/coral-tpu-automation/coral-tpu-init.sh` | Initialize Coral TPU | `./coral-tpu-init.sh` | [Coral TPU Automation Runbook](coral-tpu-automation-runbook.md) |
| `scripts/coral-tpu-automation/safe-test.sh` | Safe Coral test (inside container only) | `./safe-test.sh` | [Frigate Coral Evidence-Based Debugging](blog-frigate-coral-evidence-based-debugging.md) |
| `scripts/coral-tpu-automation/quick-test.sh` | Quick Coral functionality test | `./quick-test.sh` | [Coral TPU Automation Runbook](coral-tpu-automation-runbook.md) |
| `scripts/coral-tpu-automation/deploy.sh` | Deploy Coral TPU automation | `./deploy.sh` | [Coral TPU Automation Runbook](coral-tpu-automation-runbook.md) |
| `scripts/coral-tpu-automation/test-coral-automation.sh` | Test Coral automation workflow | `./test-coral-automation.sh` | [Coral TPU Automation Runbook](coral-tpu-automation-runbook.md) |
| `scripts/coral-tpu-automation/test-safety.sh` | Test safety checks | `./test-safety.sh` | [Coral TPU Automation Runbook](coral-tpu-automation-runbook.md) |
| `scripts/coral-tpu-automation/debug-test.sh` | Debug Coral issues | `./debug-test.sh` | [Coral TPU Automation Runbook](coral-tpu-automation-runbook.md) |
| `scripts/coral-tpu-automation/mock-coral-init.sh` | Mock Coral init for testing | `./mock-coral-init.sh` | - |

### Common Coral Workflows

```bash
# Full diagnostics after boot
./scripts/coral-tpu-automation/comprehensive-check.sh

# Test Coral inside container only (safe)
./scripts/coral-tpu-automation/safe-test.sh

# If Coral fails "did not claim interface 0"
# ONLY FIX: Physical unplug/replug
```

**Related Documentation:**
- [Coral TPU Automation Runbook](coral-tpu-automation-runbook.md)
- [Coral Migration to pumped-piglet](blog-coral-migration-pumped-piglet.md)
- [Coral AMD GPU still-fawn](blog-coral-amd-gpu-still-fawn.md)

---

## Frigate Coral LXC Deployment

**Sequential deployment scripts for Frigate + Coral TPU in Proxmox LXC.**

### Prerequisites (01-05)

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/frigate-coral-lxc/01-check-prerequisites.sh` | Check BIOS VT-d, IOMMU groups | `./01-check-prerequisites.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/02-verify-coral-usb.sh` | Verify Coral USB detected on host | `./02-verify-coral-usb.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/03-find-sysfs-path.sh` | Find Coral USB sysfs path | `./03-find-sysfs-path.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/03a-create-container-automated.sh` | Automated LXC creation | `./03a-create-container-automated.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/04-check-udev-rules.sh` | Check udev rules for Coral | `./04-check-udev-rules.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/04a-check-dev-dri.sh` | Check /dev/dri devices | `./04a-check-dev-dri.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/05-create-udev-rules.sh` | Create udev rules | `./05-create-udev-rules.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/05a-install-dfu-util.sh` | Install dfu-util for Coral firmware | `./05a-install-dfu-util.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/05b-download-firmware.sh` | Download Coral firmware | `./05b-download-firmware.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/05c-create-udev-rules.sh` | Create advanced udev rules | `./05c-create-udev-rules.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/06-reload-udev.sh` | Reload udev rules | `./06-reload-udev.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |

### Container Configuration (10-13)

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/frigate-coral-lxc/10-stop-container.sh` | Stop LXC container | `./10-stop-container.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/11-add-usb-passthrough.sh` | Add USB passthrough to LXC | `./11-add-usb-passthrough.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/12-add-cgroup-permissions.sh` | Add cgroup permissions | `./12-add-cgroup-permissions.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/13-add-vaapi-passthrough.sh` | Add VA-API passthrough | `./13-add-vaapi-passthrough.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |

### Hookscript Management (20-21)

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/frigate-coral-lxc/hookscript-template.sh` | Hookscript template | Reference only | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/20-create-hookscript.sh` | Create hookscript for Coral | `./20-create-hookscript.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/21-attach-hookscript.sh` | Attach hookscript to LXC | `./21-attach-hookscript.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |

### Verification (30-34)

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/frigate-coral-lxc/30-start-container.sh` | Start LXC container | `./30-start-container.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/31-verify-hookscript.sh` | Verify hookscript executed | `./31-verify-hookscript.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/32-verify-frigate-api.sh` | Verify Frigate API responds | `./32-verify-frigate-api.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/33-verify-coral-detection.sh` | Verify Coral detections working | `./33-verify-coral-detection.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/34-verify-usb-in-container.sh` | Verify USB visible in container | `./34-verify-usb-in-container.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |

### Frigate Configuration (40-45)

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/frigate-coral-lxc/40-update-frigate-config.sh` | Update Frigate config for Coral | `./40-update-frigate-config.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/41-restart-frigate.sh` | Restart Frigate service | `./41-restart-frigate.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/42-configure-cameras.sh` | Configure camera streams | `./42-configure-cameras.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/43-verify-cameras.sh` | Verify camera streams working | `./43-verify-cameras.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/44-add-storage-mount.sh` | Add NFS/storage mount | `./44-add-storage-mount.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |
| `scripts/frigate-coral-lxc/45-verify-storage.sh` | Verify storage mount | `./45-verify-storage.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |

### Rollback (90)

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/frigate-coral-lxc/90-rollback-full.sh` | Full rollback of LXC changes | `./90-rollback-full.sh` | [Frigate Coral LXC Deployment](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md) |

### Deployment Workflow

```bash
# Prerequisites
./scripts/frigate-coral-lxc/01-check-prerequisites.sh
./scripts/frigate-coral-lxc/02-verify-coral-usb.sh
./scripts/frigate-coral-lxc/03-find-sysfs-path.sh

# Container setup
./scripts/frigate-coral-lxc/10-stop-container.sh
./scripts/frigate-coral-lxc/11-add-usb-passthrough.sh
./scripts/frigate-coral-lxc/12-add-cgroup-permissions.sh
./scripts/frigate-coral-lxc/13-add-vaapi-passthrough.sh

# Hookscript
./scripts/frigate-coral-lxc/20-create-hookscript.sh
./scripts/frigate-coral-lxc/21-attach-hookscript.sh

# Start and verify
./scripts/frigate-coral-lxc/30-start-container.sh
./scripts/frigate-coral-lxc/33-verify-coral-detection.sh
```

**Related Documentation:**
- [Frigate Coral LXC Deployment Blueprint](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md)
- [Frigate Coral LXC Methodology](../../docs/blog/2025-12-11-frigate-coral-lxc-deployment-methodology.md)
- [Action Log: still-fawn Frigate Coral](../../docs/troubleshooting/action-log-still-fawn-frigate-coral.md)

---

## Package Detection & LLM Vision

**Home Assistant package detection automation using LLM Vision and Frigate.**

### Configuration & Setup

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/package-detection/check-prerequisites.sh` | Check LLM Vision integration | `./check-prerequisites.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/check-llmvision-config.sh` | Check LLM Vision config | `./check-llmvision-config.sh` | [LLM Vision Camera Entity Fix](blog-llm-vision-camera-entity-fix.md) |
| `scripts/package-detection/pull-vision-model.sh` | Pull Ollama vision model | `./pull-vision-model.sh` | [Ollama Input Text Myth](blog-ollama-input-text-myth-busted.md) |
| `scripts/package-detection/list-cameras.sh` | List available cameras | `./list-cameras.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |

### Testing & Validation

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/package-detection/test-llm-vision.sh` | Test LLM Vision service call | `./test-llm-vision.sh` | [LLM Vision Camera Entity Fix](blog-llm-vision-camera-entity-fix.md) |
| `scripts/package-detection/test-llm-vision-with-metrics.sh` | Test with performance metrics | `./test-llm-vision-with-metrics.sh` | [LLM Vision Camera Entity Fix](blog-llm-vision-camera-entity-fix.md) |
| `scripts/package-detection/test-notification.sh` | Test notification delivery | `./test-notification.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/test-full-flow.sh` | Test end-to-end workflow | `./test-full-flow.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |

### Deployment

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/package-detection/deploy-automation.sh` | Deploy package detection automation | `./deploy-automation.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/deploy-automation-v2.sh` | Deploy automation v2 | `./deploy-automation-v2.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/deploy-pulse-automation.sh` | Deploy LED pulse automation | `./deploy-pulse-automation.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/deploy-fixed-script.sh` | Deploy fixed script version | `./deploy-fixed-script.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/deploy-sentence-trigger.sh` | Deploy voice sentence trigger | `./deploy-sentence-trigger.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/preflight-check.sh` | Pre-deployment checks | `./preflight-check.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |

### Helper Management

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/package-detection/setup-helpers.sh` | Setup input_text helpers | `./setup-helpers.sh` | [Ollama Input Text Myth](blog-ollama-input-text-myth-busted.md) |
| `scripts/package-detection/create-helpers.sh` | Create required helpers | `./create-helpers.sh` | [Ollama Input Text Myth](blog-ollama-input-text-myth-busted.md) |
| `scripts/package-detection/verify-helpers.sh` | Verify helpers exist | `./verify-helpers.sh` | [Ollama Input Text Myth](blog-ollama-input-text-myth-busted.md) |
| `scripts/package-detection/check-input-text.sh` | Check input_text state | `./check-input-text.sh` | [Ollama Input Text Myth](blog-ollama-input-text-myth-busted.md) |
| `scripts/package-detection/fix-input-text.sh` | Fix input_text issues | `./fix-input-text.sh` | [Ollama Input Text Myth](blog-ollama-input-text-myth-busted.md) |

### Voice Integration

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/package-detection/setup-voice-intent.sh` | Setup voice intent | `./setup-voice-intent.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/setup-custom-sentences.sh` | Setup custom sentences | `./setup-custom-sentences.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/test-voice-pe-led.sh` | Test voice LED feedback | `./test-voice-pe-led.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |

### Debugging

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/package-detection/check-ha-logs.sh` | Check HA logs for errors | `./check-ha-logs.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/check-registry.sh` | Check entity registry | `./check-registry.sh` | [LLM Vision Camera Entity Fix](blog-llm-vision-camera-entity-fix.md) |
| `scripts/package-detection/check-script-state.sh` | Check script state | `./check-script-state.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/check-led-effects.sh` | Check LED effect state | `./check-led-effects.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/debug-config.sh` | Debug configuration issues | `./debug-config.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/fix-config.sh` | Fix common config issues | `./fix-config.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/restore-config.sh` | Restore config backup | `./restore-config.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |
| `scripts/package-detection/restart-and-check.sh` | Restart HA and check status | `./restart-and-check.sh` | [Package Detection LLM Vision](blog-package-detection-llm-vision.md) |

### Common Package Detection Workflows

```bash
# Initial setup
./scripts/package-detection/check-prerequisites.sh
./scripts/package-detection/pull-vision-model.sh
./scripts/package-detection/setup-helpers.sh

# Test before deployment
./scripts/package-detection/test-llm-vision.sh
./scripts/package-detection/test-notification.sh

# Deploy automation
./scripts/package-detection/preflight-check.sh
./scripts/package-detection/deploy-automation.sh

# Debug issues
./scripts/package-detection/check-ha-logs.sh
./scripts/package-detection/check-input-text.sh
```

**Related Documentation:**
- [Package Detection LLM Vision Blog](blog-package-detection-llm-vision.md)
- [LLM Vision Camera Entity Fix](blog-llm-vision-camera-entity-fix.md)
- [Ollama Input Text Myth Busted](blog-ollama-input-text-myth-busted.md)

---

## Voice Assistant Debugging

**Debugging scripts for Home Assistant Voice PE (Processing Engine) and Ollama integration.**

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/voice-pe-debug/check-conversation-agents.sh` | Check available conversation agents | `./check-conversation-agents.sh` | - |
| `scripts/voice-pe-debug/check-voice-pe-pipeline.sh` | Check Voice PE pipeline config | `./check-voice-pe-pipeline.sh` | - |
| `scripts/voice-pe-debug/check-light-state.sh` | Check light entity states | `./check-light-state.sh` | - |
| `scripts/voice-pe-debug/list-lights.sh` | List all light entities | `./list-lights.sh` | - |
| `scripts/voice-pe-debug/quick-test.sh` | Quick Voice PE test | `./quick-test.sh` | - |
| `scripts/voice-pe-debug/reload-ollama.sh` | Reload Ollama integration | `./reload-ollama.sh` | - |
| `scripts/voice-pe-debug/test-ollama-direct.sh` | Test Ollama directly | `./test-ollama-direct.sh` | - |
| `scripts/voice-pe-debug/test-ollama-e2e.sh` | End-to-end Ollama test | `./test-ollama-e2e.sh` | - |
| `scripts/voice-pe-debug/test-pipeline.sh` | Test Voice PE pipeline | `./test-pipeline.sh` | - |

### Common Voice Debugging Workflow

```bash
# Check configuration
./scripts/voice-pe-debug/check-conversation-agents.sh
./scripts/voice-pe-debug/check-voice-pe-pipeline.sh

# Test Ollama
./scripts/voice-pe-debug/test-ollama-direct.sh
./scripts/voice-pe-debug/test-ollama-e2e.sh

# Test pipeline
./scripts/voice-pe-debug/test-pipeline.sh
./scripts/voice-pe-debug/quick-test.sh
```

---

## Infrastructure & Utilities

### Network & VLAN

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/flint3_network_snapshot.sh` | Take Flint3 router network snapshot | `./flint3_network_snapshot.sh` | - |
| `scripts/flint3_verify_vlans.sh` | Verify VLAN configuration | `./flint3_verify_vlans.sh` | - |

### Benchmarking

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/ollama_benchmark.sh` | Benchmark Ollama performance | `./ollama_benchmark.sh` | - |

### Backup & Migration

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/migrate_backup_storage.sh` | Migrate backup storage | `./migrate_backup_storage.sh` | [Backup Storage Migration Runbook](backup-storage-migration-runbook.md) |

### Hardware & Drivers

| Script | Purpose | Usage | Related Docs |
|--------|---------|-------|--------------|
| `scripts/install_luma.led_matrix.sh` | Install LED matrix library | `./install_luma.led_matrix.sh` | - |
| `scripts/fix_llmvision.sh` | Fix LLM Vision integration | `./fix_llmvision.sh` | [LLM Vision Camera Entity Fix](blog-llm-vision-camera-entity-fix.md) |

---

## Best Practices

### Script Development Standards

1. **Always create scripts, never one-liners** - Even simple commands should be scripted
2. **Location**: `scripts/<component>/` (e.g., `scripts/frigate/`, `scripts/k3s/`)
3. **Naming**: Descriptive names with `.sh` extension
4. **Comments**: Include purpose, usage, and examples
5. **Environment**: Source credentials from `.env`, never hardcode

### Security

**NEVER write credentials in scripts:**

```bash
#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"
[[ -f "$ENV_FILE" ]] && HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -z "$HA_TOKEN" ]] && { echo "ERROR: HA_TOKEN not found"; exit 1; }
```

### SSH Access Rules

- **K3s VMs**: SSH DOES NOT WORK - use `qm guest exec` via wrapper scripts
- **HAOS**: SSH DOES NOT EXIST - use API or `qm guest exec`
- **Proxmox Hosts**: SSH works fine
- **Coral TPU**: NEVER test from host while LXC has it mounted

### Common Environment Variables

| Variable | Purpose | Default | Location |
|----------|---------|---------|----------|
| `HA_TOKEN` | Home Assistant API token | N/A | `proxmox/homelab/.env` |
| `HA_URL` | Home Assistant URL | `http://192.168.4.240:8123` | `proxmox/homelab/.env` |
| `FRIGATE_URL` | Frigate NVR URL | `http://192.168.4.83:5000` | Environment |

---

## Quick Reference

### Most Common Operations

```bash
# K3s CPU diagnostics
./scripts/k3s/diagnose-cpu.sh still-fawn

# Check Home Assistant API
./scripts/haos/check-ha-api.sh

# Verify Frigate status
./scripts/frigate/verify-frigate-k8s.sh

# Check Frigate integration in HA
./scripts/frigate/check-ha-frigate-integration.sh

# Coral TPU diagnostics
./scripts/coral-tpu-automation/comprehensive-check.sh

# Test package detection
./scripts/package-detection/test-llm-vision.sh
```

### Emergency Procedures

```bash
# Restart Home Assistant
./scripts/haos/restart-ha.sh

# Rollback Frigate to LXC
./scripts/frigate/rollback-to-still-fawn.sh

# Rollback Coral LXC changes
./scripts/frigate-coral-lxc/90-rollback-full.sh

# Reboot K3s node
./scripts/k3s/exec-still-fawn.sh "sudo reboot"
```

---

## Related Documentation

### Core Documentation
- [CLAUDE.md](../../CLAUDE.md) - Repository guidelines and AI instructions
- [K3s SSH Management](../../proxmox/homelab/docs/k3s-ssh-management.md) - SSH access patterns

### Frigate Documentation
- [Frigate HomeAssistant Integration Guide](frigate-homeassistant-integration-guide.md)
- [Frigate Storage Migration Report](frigate-storage-migration-report.md)
- [Frigate 0.16 Upgrade Lessons](../reference/frigate-016-upgrade-lessons.md)
- [Frigate Upgrade Decision Framework](../reference/frigate-upgrade-decision-framework.md)

### Coral TPU Documentation
- [Coral TPU Automation Runbook](coral-tpu-automation-runbook.md)
- [Coral M.2 PCIe Installation Guide](../guides/coral-m2-pcie-installation-guide.md)
- [Frigate Coral LXC Deployment Blueprint](../../docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md)

### K3s Documentation
- [K3s ETCD Performance Tuning Runbook](k3s-etcd-performance-tuning-runbook.md)
- [K3s IP Allocation Troubleshoot](runbooks/k3s-ip-allocation-troubleshoot.md)
- [K3s Migration ETCD to SQLite](guides/k3s-migration-etcd-to-sqlite.md)

### Blog Posts
- [Package Detection LLM Vision](blog-package-detection-llm-vision.md)
- [LLM Vision Camera Entity Fix](blog-llm-vision-camera-entity-fix.md)
- [Frigate Coral Evidence-Based Debugging](blog-frigate-coral-evidence-based-debugging.md)
- [K3s ETCD Performance Disaster](blog-k3s-etcd-performance-disaster.md)

---

**Last Updated:** 2025-12-14
**Repository:** github.com/homeiac/home
**Maintainer:** AI-managed homelab infrastructure
