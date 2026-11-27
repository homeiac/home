# Run Codex Luna in Kubernetes Pods Using Your Subscription

The setup is small: a pod with the Codex CLI, persistent credentials, and a ChatGPT subscription account with access to Luna. The pod runs the client; inference happens in OpenAI's cloud, so no GPU is needed in Kubernetes.

**1. Prepare the pod.** Bake a pinned Codex CLI release into your worker image. Mount a private, writable PVC at `/var/lib/codex`, set `CODEX_HOME=/var/lib/codex`, and make that directory writable by the container's user. Allow outbound HTTPS to OpenAI's authentication and Codex services.

Put this in `/var/lib/codex/config.toml`:

```toml
model = "gpt-6-luna"
model_reasoning_effort = "low"
forced_login_method = "chatgpt"
cli_auth_credentials_store = "file"
```

`gpt-6-luna` is the model ID used by this project's worker. Your signed-in account must have access to it. Keep the pod configuration in GitOps; keep credentials out of Git and container images.

**2. Sign in using the subscription.** Enable device-code login in your ChatGPT security settings or through your workspace administrator. Replace `NAMESPACE` and `POD` below with your worker's values:

```bash
kubectl -n NAMESPACE exec -it POD -- codex login --device-auth
```

Open the printed link on your laptop, enter the code, and select the intended subscription workspace. Then verify:

```bash
kubectl -n NAMESPACE exec POD -- codex login status
```

The status should show ChatGPT authentication. This uses your account's Codex entitlements and limits. [OpenAI's authentication guide](https://developers.openai.com/codex/auth/) documents subscription sign-in and the device-code flow.

**3. Run a smoke test.**

```bash
kubectl -n NAMESPACE exec POD -- codex exec \
  --skip-git-repo-check --sandbox read-only \
  -m gpt-6-luna 'Reply with exactly: Luna is ready'
```

Keep the PVC when replacing the pod. Codex stores `auth.json` there and refreshes credentials during use, so the directory must remain writable. For multiple workers, give each its own credential directory and sign-in. More pods still share the account's usage limits.
