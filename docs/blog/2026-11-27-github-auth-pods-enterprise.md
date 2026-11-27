# Create GitHub Pull Requests from Kubernetes Pods

A pod needs two things to open a PR: a GitHub identity allowed to write to the repository, and network access permitted by the enterprise. Signing in successfully on your laptop proves only the laptop works.

I tested separate Rancher Desktop pods with a personal account and an enterprise-managed account. Both read their repositories, pushed disposable branches, and created draft PRs with the correct author. The tests then closed the PRs and deleted the branches. No enterprise policy changes were needed.

**Authenticate where your organization permits it.** If pod-initiated login is allowed, run `gh auth login --hostname github.com --git-protocol https --web` inside the pod and complete its device-code flow in your browser. Otherwise, sign in on your approved workstation. [GitHub CLI supports browser login and environment-token authentication](https://cli.github.com/manual/gh_auth_login).

**Transfer the selected credential only when policy permits it.** Copying `~/.config/gh/hosts.yml` from a Mac can miss the actual token: it may live in the macOS keychain. Use `gh auth token --hostname github.com --user ACCOUNT` and stream its output directly to the pod. Never run that command bare in a recorded terminal. [The `--user` option selects the intended account](https://cli.github.com/manual/gh_auth_token).

The [companion scripts](https://github.com/homeiac/home/tree/master/scripts/github-pods) handle that transfer through `kubectl exec` standard input. They set `GH_TOKEN` for one command, verify its identity, and leave no token in YAML, images, Kubernetes Secrets, or credential files.

```bash
bash scripts/github-pods/prepare.sh
python3 scripts/github-pods/pod-test.py check \
  --account YOUR_LOGIN --pod enterprise --repo ORG/REPO
```

For a pushed feature branch, open the PR from the pod:

```bash
python3 scripts/github-pods/pod-test.py exec \
  --account YOUR_LOGIN --pod enterprise --command \
  gh pr create --repo ORG/REPO --base main --head FEATURE_BRANCH \
  --draft --title 'Describe the change' --body 'Describe validation.'
```

**Respect the enterprise boundary.** Token transfer does not make a pod compliant or bypass SSO, app approval, IP allowlists, or conditional access. If the laptop succeeds and the pod gets a policy-related 403, use an organization-approved runner or approved network path. Ask the administrator to resolve the restriction; copying another token is not the fix. [GitHub documents enterprise IP restrictions](https://docs.github.com/en/enterprise-cloud@latest/admin/configuring-settings/hardening-security-for-your-enterprise/restricting-network-traffic-to-your-enterprise-with-an-ip-allow-list).

These pods are temporary. Remove them when finished:

```bash
python3 scripts/github-pods/pod-test.py cleanup
```
