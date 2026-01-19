# Weekend Projects

Homelab projects to tackle when you have some free time.

## Active Projects

### lldap - Lightweight LDAP Server
- **URL**: https://github.com/lldap/lldap
- **GitHub Issue**: [#162](https://github.com/homeiac/home/issues/162)
- **Priority**: Medium
- **Status**: Not Started
- **Description**: Deploy lightweight LDAP for centralized authentication across homelab services
- **Benefits**:
  - Simple web UI for user management
  - Rust-based, low resource usage
  - Perfect for SSO across Proxmox, Grafana, etc.
- **Deployment Options**: LXC container or Kubernetes

### Proxmox CSI Plugin - Shared Storage for K3s
- **URL**: https://github.com/sergelogvinov/proxmox-csi-plugin
- **GitHub Issue**: [#163](https://github.com/homeiac/home/issues/163)
- **Priority**: High
- **Status**: Not Started
- **Description**: Native Proxmox storage integration for Kubernetes PVCs
- **Context**: Longhorn failed miserably, Crucible still promising but requires additional storage sleds
- **Benefits**:
  - Direct integration with existing Proxmox storage (local-zfs, NFS)
  - No additional distributed storage layer overhead
  - Leverages infrastructure already in place

### PageLM - Audio Podcasts from Blog Posts
- **URL**: https://github.com/CaviraOSS/PageLM
- **GitHub Issue**: [#170](https://github.com/homeiac/home/issues/170)
- **Priority**: Low
- **Status**: Not Started
- **Description**: Generate audio podcasts from blog posts for "learning on the go"
- **Benefits**:
  - Transforms existing documentation into audio content
  - Multiple TTS engine options (Edge TTS, ElevenLabs, Google)
  - Open-source NotebookLM alternative
- **Requirements**: Node.js v21.18+, ffmpeg
- **Deployment Options**: K8s, CI/CD integration, or on-demand

### OpenMemory - Persistent AI Memory (Claude Integration)
- **URL**: https://github.com/homeiac/OpenMemory (forked from CaviraOSS)
- **GitHub Issue**: [#171](https://github.com/homeiac/home/issues/171)
- **Priority**: High
- **Status**: **Implemented** (MCP server running at localhost:8080)
- **Description**: Give Claude Code persistent memory across sessions via MCP
- **Implementation**:
  - Fork: `homeiac/OpenMemory` with LGM tools added
  - Tools: `openmemory_lgm_store`, `openmemory_lgm_context` + 5 base tools
  - Behavioral guidelines: CLAUDE.md "OpenMemory Integration" section
  - Test script: `scripts/openmemory/verify-mcp-backend.sh`
- **Behavioral Requirements**:
  - R7: Auto-query context at session start
  - R8: Reinforce memories that help solve problems
  - R9: Fallback to CLAUDE.md when OpenMemory unavailable
  - R10: Ask before changing behavior based on memories
- **Storage Triggers**: Issue resolution, discovery, user request, session end
- **Configuration**: `~/.claude.json` → `mcpServers.openmemory`
- **Usage**: See CLAUDE.md "OpenMemory Integration" section for guidelines

### OpenMemory Server - Cross-Project Shared Memory
- **URL**: https://github.com/CaviraOSS/OpenMemory
- **GitHub Issue**: [#172](https://github.com/homeiac/home/issues/172)
- **Priority**: Medium
- **Status**: Not Started
- **Description**: Centralized OpenMemory server for multiple projects
- **Benefits**:
  - Single instance serves home, chorus, devops repos
  - Web dashboard for memory visualization
  - Shared infrastructure knowledge base
- **Deployment Options**: K8s with PVC or Docker on Proxmox LXC

### OpenReason - AI Planning Validation
- **URL**: https://github.com/CaviraOSS/OpenReason
- **GitHub Issue**: [#173](https://github.com/homeiac/home/issues/173)
- **Priority**: Medium
- **Status**: Not Started
- **Description**: Check and balance for Claude's planning and execution
- **Benefits**:
  - 5-stage verification pipeline (classify → skeleton → solve → verify → finalize)
  - Catches missing steps, invalid reasoning, contradictions
  - Confidence scores before execution
  - Auto-repairs broken reasoning steps
- **Use Cases**: Validate infra plans, check debugging hypotheses, verify refactoring

## Backlog

_Add future weekend project ideas here_

## Completed

_Move completed projects here with completion date_

---

## Next Session - Frigate/Coral Decision

1. Test face recognition: walk in front of cameras, check if Frigate recognizes faces (Asha/G) - if useful, keep on pumped-piglet
2. If face recognition not useful: move Coral USB back to still-fawn, update deployment (node selector → still-fawn, hwaccel → vaapi), disable face_recognition
3. Compare power usage: still-fawn (~25W total) vs pumped-piglet (~80-100W) with Frigate running
