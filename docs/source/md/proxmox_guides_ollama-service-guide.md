# Ollama Service via Flux

This guide shows how to expose the Ollama deployment through a Kubernetes Service managed by FluxCD.

The `service-server.yaml` manifest under `gitops/clusters/homelab/apps/ollama/` selects pods labeled `app=ollama-server` and forwards port `80` to `11434`.

Commit the file and Flux will create or update the service automatically.
