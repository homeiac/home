# GitHub authentication in Rancher Desktop pods

Run only on a trusted Rancher Desktop cluster that is approved to use your GitHub
identity. The helper selects a saved `github.com` account without changing the
active account on the laptop. The token comes from `gh auth token --user`; it is
streamed through Kubernetes exec stdin and exported as `GH_TOKEN` only in that
command's process tree. Cluster administrators and processes with sufficient
inspection privileges remain part of the trust boundary.

Prerequisites: Rancher Desktop with the Moby runtime, `docker`, `kubectl`, Python 3,
and a workstation GitHub CLI login. Every Kubernetes call explicitly selects
`rancher-desktop`; the current kubeconfig context is preserved.

```bash
bash scripts/github-pods/prepare.sh
python3 scripts/github-pods/pod-test.py check \
  --account YOUR_LOGIN --pod personal --repo OWNER/REPO
```

The other pod is named `enterprise`. Both run unprivileged with a read-only image,
memory-backed temporary storage, no service-account token, and a one-hour deadline.
Setup refuses an existing namespace instead of replacing it. Use `cleanup` before
running setup again. No credentials are needed to build the image or create pods.

## Run an authenticated command

```bash
python3 scripts/github-pods/pod-test.py exec \
  --account YOUR_LOGIN --pod enterprise --command \
  gh pr create --repo OWNER/REPO --base main --head YOUR_PUSHED_BRANCH \
  --draft --title 'Describe the change' --body 'Describe validation.'
```

`exec` verifies the account before executing the command. Its token comes from the
laptop afresh on each invocation. Environment tokens are not automatically refreshed
inside the pod. Reauthenticate on the approved workstation when necessary.

For Git commands, use `git -c credential.helper= -c
'credential.helper=!gh auth git-credential' ...` through the same `exec` action.
The normal `check` action tests REST, GraphQL and Git HTTPS reads independently.

## Optional end-to-end PR test

```bash
python3 scripts/github-pods/pod-test.py pr-smoke \
  --account YOUR_LOGIN --pod enterprise --repo OWNER/REPO
```

This action writes to GitHub: it pushes two uniquely named temporary branches
pointing to existing commits, opens and verifies a draft PR between them, closes
the PR, and deletes both branches. It makes no new commit and never merges into
the default branch. The repository needs at least two commits. Repository workflows
may run for the pushes or PR. Use a repository approved for the test.

If the network fails mid-operation, inspect the printed branch names and PR URL
before retrying. A failed close preserves the branches for recovery. Enterprise
SSO, OAuth approvals, network allowlists, branch rules and PR permissions still
apply. Use an approved runner when credential export or pod execution is prohibited.
This helper does not change those controls.

## Cleanup and verification

```bash
python3 scripts/github-pods/pod-test.py cleanup
python3 -m unittest discover -s scripts/github-pods/tests -v
```

Cleanup deletes only the labeled test namespace. The local image remains available
for reuse. On 2026-11-27, both a personal account and an enterprise-managed account
passed the full test against their respective authorized repositories. This result
does not establish approval for other organizations or execution environments.
