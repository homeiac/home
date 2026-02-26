# Ollama GPU Server Setup

This guide shows how to run the Ollama server on a Kubernetes node with an NVIDIA GPU. It assumes the
NVIDIA device plugin is installed on the cluster.

## Deployment via Flux

FluxCD manages the Ollama deployment under `gitops/clusters/homelab/apps/ollama/`.
Commit the manifest files to the repository and Flux will create the namespace,
deployment and service automatically. The deployment mounts an empty directory at
`/root/.ollama` for model storage. Replace it with a persistent volume claim if you want
the models to survive pod restarts.

## Adding and Serving Models

1. Pull a model into the running pod:

   ```bash
   kubectl exec deployment/ollama-gpu -- ollama pull qwen3:4b
   ```

2. Verify the model is available:

   ```bash
   kubectl exec deployment/ollama-gpu -- ollama list
   ```

3. Send a test request to the service:

   ```bash
   curl http://<service-ip>:80/api/generate -d '{"model":"qwen3:4b","prompt":"Hello"}'
   ```

### Model Swap Script

To swap models (pull new, remove old, verify GPU):

```bash
scripts/ollama/update-model.sh qwen3:4b qwen2.5:3b
```

Add `--ha` to also update the Home Assistant conversation agent.
