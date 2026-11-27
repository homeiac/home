#!/usr/bin/env python3
"""Test selected macOS-keychain GitHub credentials in isolated local pods.

Credentials are transported through kubectl stdin, never argv, manifests or disk.
Only use this on a trusted local cluster approved to use the selected identity.
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import uuid

CONTEXT = "rancher-desktop"
NAMESPACE = "gh-auth-pod-test"
PODS = ("personal", "enterprise")
LOG = logging.getLogger(__name__)


def run(command: list[str], *, data: str | None = None,
        env: dict[str, str] | None = None, secret: str = "") -> str:
    """Run a bounded command and redact its credential from failure output."""
    result = subprocess.run(command, input=data, text=True, capture_output=True,
                            env=env, timeout=300)
    output = result.stdout + result.stderr
    if secret:
        output = output.replace(secret, "[REDACTED]")
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {output.strip()}")
    return result.stdout.replace(secret, "[REDACTED]") if secret else result.stdout


def kubectl(*args: str, data: str | None = None, secret: str = "") -> str:
    """Always target the explicitly requested local cluster."""
    return run(["kubectl", "--context", CONTEXT, "-n", NAMESPACE, *args],
               data=data, secret=secret)


def prepare() -> None:
    """Create a dedicated namespace and two pods with no API service token."""
    namespace = {"apiVersion": "v1", "kind": "Namespace",
                 "metadata": {"name": NAMESPACE,
                              "labels": {"app.kubernetes.io/managed-by": "gh-auth-pod-test"}}}
    # create fails safely if the namespace already exists; never adopt other work.
    kubectl("create", "-f", "-", data=json.dumps(namespace))
    for name in PODS:
        pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name},
               "spec": {"automountServiceAccountToken": False,
                        "activeDeadlineSeconds": 3600, "restartPolicy": "Never",
                        "securityContext": {"runAsNonRoot": True, "runAsUser": 10001,
                                            "runAsGroup": 10001, "fsGroup": 10001,
                                            "seccompProfile": {"type": "RuntimeDefault"}},
                        "containers": [{"name": "gh", "image": "gh-auth-pod-test:1",
                            "imagePullPolicy": "Never",
                            "securityContext": {"allowPrivilegeEscalation": False,
                                "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]}},
                            "resources": {"requests": {"cpu": "50m", "memory": "64Mi"},
                                          "limits": {"cpu": "1", "memory": "512Mi"}},
                            "volumeMounts": [{"name": n, "mountPath": "/" + n}
                                             for n in ("tmp", "work")] }],
                        "volumes": [{"name": n, "emptyDir": {"medium": "Memory",
                                                             "sizeLimit": "256Mi"}}
                                    for n in ("tmp", "work")]}}
        kubectl("create", "-f", "-", data=json.dumps(pod))
    kubectl("wait", "--for=condition=Ready", "pod", "--all", "--timeout=120s")
    LOG.info("Created personal and enterprise pods on %s", CONTEXT)


def token_for(account: str) -> str:
    """Read exactly the named local login, ignoring ambient token overrides."""
    env = dict(os.environ)
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        env.pop(key, None)
    result = subprocess.run(["gh", "auth", "token", "--hostname", "github.com",
                             "--user", account], env=env, capture_output=True,
                            text=True, timeout=30)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("No saved token for the selected account; sign in on the approved host")
    return result.stdout.strip()


def pod_command(pod: str, token: str, command: list[str]) -> str:
    """Expose the token only to one exec process and its children."""
    wrapper = 'set -eu; IFS= read -r GH_TOKEN; export GH_TOKEN; mkdir -p "$HOME"; exec "$@"'
    return kubectl("exec", "-i", pod, "--", "sh", "-c", wrapper, "gh-pod", *command,
                   data=token + "\n", secret=token)


def execute(account: str, pod: str, command: list[str]) -> None:
    """Run an explicit command after checking its selected pod identity."""
    token = token_for(account)
    actual = pod_command(pod, token, ["gh", "api", "user", "--jq", ".login"]).strip()
    if actual != account:
        raise RuntimeError("Account mismatch; refusing the command")
    LOG.info("%s", pod_command(pod, token, command).strip())


def check(account: str, pod: str, repo: str) -> None:
    """Compare host and pod identity, repository access, and Git transport."""
    token = token_for(account)
    env = dict(os.environ, GH_TOKEN=token, GH_PROMPT_DISABLED="1")
    host = run(["gh", "api", "user", "--jq", ".login"], env=env, secret=token).strip()
    identity = pod_command(pod, token, ["gh", "api", "user", "--jq", ".login"]).strip()
    if host != account or identity != account:
        raise RuntimeError("Account mismatch; refusing repository operations")
    LOG.info("Host and pod identity verified: %s", identity)
    LOG.info("Repository access: %s", pod_command(pod, token, ["gh", "api", "repos/" + repo,
        "--jq", "{full_name,default_branch,permissions}"]).strip())
    LOG.info("GraphQL: %s", pod_command(pod, token, ["gh", "repo", "view", repo,
        "--json", "nameWithOwner,viewerPermission"]).strip())
    pod_command(pod, token, ["git", "-c", "credential.helper=",
        "-c", "credential.helper=!gh auth git-credential", "ls-remote",
        "https://github.com/" + repo + ".git", "HEAD"])
    LOG.info("Git HTTPS read succeeded")
    kubectl("exec", pod, "--", "sh", "-c", 'test ! -f "$GH_CONFIG_DIR/hosts.yml"')
    LOG.info("No persistent gh credential file created")


def pr_smoke(account: str, pod: str, repo: str) -> None:
    """Push existing commits to disposable refs, open a draft PR, then clean up."""
    check(account, pod, repo)
    token = token_for(account)
    suffix = uuid.uuid4().hex[:12]
    base = "codex/gh-auth-smoke-base-" + suffix
    head = "codex/gh-auth-smoke-head-" + suffix
    folder = "/work/" + suffix
    default = pod_command(pod, token, ["gh", "api", "repos/" + repo,
                                      "--jq", ".default_branch"]).strip()
    git = ["git", "-C", folder, "-c", "credential.helper=", "-c",
           "credential.helper=!gh auth git-credential"]
    pushed = False
    pr_url = ""
    try:
        pod_command(pod, token, ["git", "init", "--bare", folder])
        pod_command(pod, token, git + ["remote", "add", "origin",
                                      "https://github.com/" + repo + ".git"])
        pod_command(pod, token, git + ["fetch", "--filter=blob:none", "--depth=2",
                                      "origin", "refs/heads/" + default])
        tip = pod_command(pod, token, git + ["rev-parse", "FETCH_HEAD"]).strip()
        parent = pod_command(pod, token, git + ["rev-parse", "FETCH_HEAD^1"]).strip()
        LOG.info("Disposable refs for this test: %s, %s", base, head)
        pod_command(pod, token, git + ["push", "--atomic", "origin",
            parent + ":refs/heads/" + base, tip + ":refs/heads/" + head])
        pushed = True
        pr_url = pod_command(pod, token, ["gh", "pr", "create", "--repo", repo,
            "--base", base, "--head", head, "--draft", "--title",
            "Authentication smoke test from Rancher Desktop pod",
            "--body", "Temporary authentication verification using two existing commits. "
            "No new code or commits. Targets a disposable base branch. Do not merge. "
            "The test closes this draft and deletes both branches automatically."]).strip()
        if not pr_url.startswith("https://github.com/" + repo + "/pull/"):
            raise RuntimeError("Unexpected PR creation response")
        LOG.info("Created draft PR from pod: %s", pr_url)
        result = json.loads(pod_command(pod, token, ["gh", "pr", "view", pr_url,
            "--json", "author,isDraft,baseRefName,headRefName,state,url"]))
        if (result["author"]["login"] != account or not result["isDraft"]
                or result["baseRefName"] != base or result["headRefName"] != head):
            raise RuntimeError("Created PR failed identity, draft or branch verification")
        LOG.info("Verified PR author, draft state and disposable branches")
    finally:
        # Preserve refs if closing fails, making manual recovery straightforward.
        if pr_url:
            pod_command(pod, token, ["gh", "pr", "close", pr_url])
            state = pod_command(pod, token, ["gh", "pr", "view", pr_url,
                                             "--json", "state", "--jq", ".state"]).strip()
            if state != "CLOSED":
                raise RuntimeError("Test PR did not close; preserving branches")
            LOG.info("Closed test PR: %s", pr_url)
        if pushed:
            pod_command(pod, token, git + ["push", "--atomic", "origin", "--delete", base, head])
            LOG.info("Deleted both disposable remote branches")
        kubectl("exec", pod, "--", "rm", "-rf", folder)


def main() -> None:
    """Prepare, inspect, or remove only this script's named test resources."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "exec", "pr-smoke", "cleanup"))
    parser.add_argument("--account")
    parser.add_argument("--pod", choices=PODS)
    parser.add_argument("--repo")
    parser.add_argument("--command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "cleanup":
        namespace = json.loads(kubectl("get", "namespace", NAMESPACE, "-o", "json"))
        if namespace["metadata"].get("labels", {}).get("app.kubernetes.io/managed-by") != "gh-auth-pod-test":
            raise RuntimeError("Refusing to delete an unowned namespace")
        kubectl("delete", "namespace", NAMESPACE, "--wait=true", "--timeout=90s")
        LOG.info("Removed test namespace and both pods")
    elif args.action == "exec":
        if not args.account or not args.pod or not args.command:
            parser.error("exec requires --account, --pod and --command COMMAND...")
        execute(args.account, args.pod, args.command)
    else:
        if not args.account or not args.pod or not args.repo or not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
            parser.error("check/pr-smoke requires --account, --pod and --repo OWNER/NAME")
        if args.action == "pr-smoke":
            pr_smoke(args.account, args.pod, args.repo)
        else:
            check(args.account, args.pod, args.repo)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        LOG.error("%s", error)
        sys.exit(1)
