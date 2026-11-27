# Create GitHub Pull Requests from Kubernetes Pods

Sign in to GitHub on your laptop, then run a script that passes that login's token to a Kubernetes pod. **Every command below runs in your laptop terminal.**

You need macOS, Rancher Desktop using the Moby runtime, and `gh`, `git`, `docker`, `kubectl`, and Python 3 installed.

**1. On your laptop: sign in to GitHub.**

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth status
```

Complete the browser login with the account you want the pod to use. For work, choose your enterprise account and complete SSO. If that account is already signed in, skip login. Note its GitHub username from `gh auth status`.

**2. On your laptop: get the scripts, launch the pods, and transfer authentication.**

```bash
git clone --depth 1 https://github.com/homeiac/home.git home-gh-pods
cd home-gh-pods
bash scripts/github-pods/prepare.sh

python3 scripts/github-pods/pod-test.py check \
  --account YOUR_LOGIN --pod enterprise --repo ORG/REPO
```

Replace `YOUR_LOGIN` with that username and `ORG/REPO` with your target repository. For example, the personal-account test uses `--account gshiva --pod personal --repo homeiac/home`.

`prepare.sh` creates two local test pods named `personal` and `enterprise`. `check` reads the selected account's token from your laptop, streams it into the chosen pod, and verifies identity, repository access, and Git HTTPS access. You do not copy a file or paste a token.

**3. On your laptop: tell the pod to create the PR.**

Use an existing, pushed feature branch; replace the uppercase placeholders and change `main` if your repository uses another base branch.

```bash
python3 scripts/github-pods/pod-test.py exec \
  --account YOUR_LOGIN --pod enterprise --command \
  gh pr create --repo ORG/REPO --base main --head FEATURE_BRANCH \
  --draft --title 'Describe the change' --body 'Describe validation.'
```

The script runs `gh pr create` **inside the pod**. Authentication is passed again for each invocation; it is not saved as a permanent pod login. Keep using this wrapper for authenticated commands. [GitHub CLI supports this `GH_TOKEN` authentication method](https://cli.github.com/manual/gh_auth_login).

**4. On your laptop: remove the test pods when finished.**

```bash
python3 scripts/github-pods/pod-test.py cleanup
```

Both personal and enterprise-managed accounts passed this flow on Rancher Desktop, including draft-PR creation and cleanup. Your organization must permit credential use in the pod and its network access. A policy-related 403 needs an approved runner or administrator resolution; token transfer does not override enterprise controls.
