# Scripts Index

Quick reference for all scripts in this repository. Each directory has its own README.md with detailed script listings.

## Directories

| Directory | Purpose | Scripts | Index |
|-----------|---------|:-------:|-------|
| [backup/](backup/) | PBS backup automation, rclone to Google Drive, external datastore setup | 9 | [README](backup/README.md) |
| [claudecodeui/](claudecodeui/) | Claude Code UI project management, authentication testing | 3+ | [README](claudecodeui/README.md) |
| [crossplane/](crossplane/) | Crossplane provider setup, VM/LXC import, SOPS secrets | 5 | [README](crossplane/README.md) |
| [frigate/](frigate/) | Frigate NVR config, storage mounts, detector switching, backup exclusions | 26 | [README](frigate/README.md) |
| [frigate-coral-lxc/](frigate-coral-lxc/) | Full Coral TPU LXC setup: udev rules, USB passthrough, VAAPI, hookscripts | 30 | [README](frigate-coral-lxc/README.md) |
| [frigate-health-checker/](frigate-health-checker/) | Pre-push health validation for Frigate | 1 | - |
| [ha-dns-homelab/](ha-dns-homelab/) | DNS chain diagnosis, OPNsense/HAOS DNS fix steps, Frigate URL resolution | 9 | [README](ha-dns-homelab/README.md) |
| [ha-frigate-migration/](ha-frigate-migration/) | Frigate URL migration in HA, rollback scripts | 2 | [README](ha-frigate-migration/README.md) |
| [haos/](haos/) | HA API tools: automation traces, entity states, service calls, TTS testing | 28 | [README](haos/README.md) |
| [k3s/](k3s/) | K3s VM management via qm guest exec (no SSH), CPU diagnostics, PBS backups | 14 | [README](k3s/README.md) |
| [lib-sh/](lib-sh/) | Shared bash library for HA API calls (`ha-api.sh`) | 1 | - |
| [maas-dns/](maas-dns/) | MAAS DNS forwarders, forward zones, BIND restart, DNS chain diagnosis | 9 | [README](maas-dns/README.md) |
| [mac-studio/](mac-studio/) | Mac Studio initial setup | 1 | [README](mac-studio/README.md) |
| [monitoring/](monitoring/) | Grafana email alerts, Flux dashboard import | 3 | [README](monitoring/README.md) |
| [openmemory/](openmemory/) | OpenMemory ingestion, session analysis, project management, stats | 8 | [README](openmemory/README.md) |
| [perf/](perf/) | USE Method diagnostics, memory deep-dive, network timing, crisis tools | 10 | [README](perf/README.md) |
| [proxmox/](proxmox/) | Proxmox host utilities (NTP sync) | 1 | [README](proxmox/README.md) |
| [rke2-windows-eval/](rke2-windows-eval/) | RKE2 + Rancher evaluation: VM creation, Windows node registration, tmpfs testing | 39 | [README](rke2-windows-eval/README.md) |
| [sops/](sops/) | SOPS secret encryption, namespace copying | 3 | [README](sops/README.md) |
| [voice-pe/](voice-pe/) | Voice PE ESPHome debugging: TTS, Piper, Wyoming, entity states, serial monitor | 41 | [README](voice-pe/README.md) |

## Commonly Used Scripts

### Home Assistant
| Script | Purpose |
|--------|---------|
| `haos/get-automation-trace.sh <id>` | Debug automation with full event chain timeline |
| `haos/check-ha-api.sh` | Verify HA API is responding |
| `haos/restart-ha.sh` | Restart Home Assistant via API |
| `haos/get-entity-state.sh <entity>` | Get any entity's current state |
| `haos/list-automations.sh [prefix]` | List automations, optionally filtered |

### Voice PE
| Script | Purpose |
|--------|---------|
| `voice-pe/test-tts-message.sh <msg>` | Test TTS announcement directly |
| `voice-pe/check-entities.sh` | Check all Voice PE entity states |
| `voice-pe/serial-monitor.sh` | Monitor ESPHome serial output |
| `voice-pe/check-piper-status.sh` | Check Piper TTS addon status |

### K3s (no SSH - use these instead)
| Script | Purpose |
|--------|---------|
| `k3s/exec-still-fawn.sh <cmd>` | Run command on still-fawn VM (VMID 108) |
| `k3s/exec-pumped-piglet.sh <cmd>` | Run command on pumped-piglet VM (VMID 105) |
| `k3s/diagnose-cpu.sh <node>` | Full CPU diagnostics for a node |

### Frigate
| Script | Purpose |
|--------|---------|
| `frigate/check-status.sh` | Check Frigate pod/container status |
| `frigate/get-config.sh` | Dump current Frigate config |
| `frigate/add-storage-mount.sh` | Add media storage mount |

### OpenMemory
| Script | Purpose |
|--------|---------|
| `openmemory/analyze-sessions.sh` | Analyze Claude session metrics |
| `openmemory/ingest-file.sh <file>` | Ingest a file into OpenMemory |
| `openmemory/add-project.sh` | Add a project to tracking |

## Regenerating Directory READMEs

After adding new scripts, regenerate the per-directory READMEs:
```bash
./scripts/generate-readme.sh              # All directories
./scripts/generate-readme.sh scripts/haos # Single directory
```

The generator extracts the description from line 2 of each script (first comment after shebang).
