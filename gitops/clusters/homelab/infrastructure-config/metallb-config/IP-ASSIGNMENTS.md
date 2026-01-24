# MetalLB IP Assignments

Reserved IP pool: `192.168.4.80-192.168.4.120`

## Static Assignments (defined in service annotations)

| IP | Service | Namespace | Notes |
|----|---------|-----------|-------|
| 192.168.4.80 | traefik | kube-system | **RESERVED** - Main ingress, all HTTP(S) traffic |
| 192.168.4.81 | frigate | frigate | NVR web UI, RTSP, WebRTC TCP |
| 192.168.4.82 | stable-diffusion-webui | stable-diffusion | SD WebUI |
| 192.168.4.84 | frigate-webrtc-udp | frigate | WebRTC UDP streams |
| 192.168.4.85 | ollama-lb | ollama | Ollama API |
| 192.168.4.120 | samba-lb | samba | SMB/CIFS shares |

## Rules

1. **ALWAYS** add `metallb.universe.tf/loadBalancerIPs` annotation to LoadBalancer services
2. **NEVER** let MetalLB auto-assign IPs (causes race conditions on cluster rebuild)
3. Traefik MUST have .80 - all ingress routes depend on it
4. Update this file when adding new LoadBalancer services
