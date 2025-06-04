# Ollama GPU Server Setup

This guide shows how to run the Ollama server on a Kubernetes node with an NVIDIA GPU. It assumes the
NVIDIA device plugin is installed on the cluster.

## Deployment

Apply the manifest from the `k8s` directory:

```bash
kubectl apply -f k8s/ollama-gpu-server.yaml
```

The deployment mounts an empty directory at `/root/.ollama` for model storage. Replace it with a persistent
volume claim if you want the models to survive pod restarts.

## Adding and Serving Models

1. Pull a model into the running pod:

   ```bash
   kubectl exec deployment/ollama-server -- ollama pull llama3
   ```

2. Verify the model is available:

   ```bash
   kubectl exec deployment/ollama-server -- ollama list
   ```

3. Send a test request to the service:

   ```bash
   curl http://<service-ip>:80/api/generate -d '{"model":"llama3","prompt":"Hello"}'
   ```
