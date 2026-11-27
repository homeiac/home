"""Credential isolation and destructive-cleanup guards for the pod helper."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SPEC = importlib.util.spec_from_file_location("pod_test", Path(__file__).parents[1] / "pod-test.py")
pod_test = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pod_test)


class CredentialTests(unittest.TestCase):
    def test_failure_redacts_token(self) -> None:
        with patch.object(pod_test.subprocess, "run", return_value=subprocess.CompletedProcess(
                ["gh"], 1, "", "rejected test-sensitive-value")):
            with self.assertRaisesRegex(RuntimeError, r"rejected \[REDACTED\]"):
                pod_test.run(["gh"], secret="test-sensitive-value")

    def test_success_redacts_token(self) -> None:
        with patch.object(pod_test.subprocess, "run", return_value=subprocess.CompletedProcess(
                ["gh"], 0, "test-sensitive-value", "")):
            self.assertEqual(pod_test.run(["gh"], secret="test-sensitive-value"), "[REDACTED]")

    def test_keychain_selection_ignores_ambient_account(self) -> None:
        with patch.dict(os.environ, {"GH_TOKEN": "wrong-account", "GITHUB_TOKEN": "wrong-account"}), \
                patch.object(pod_test.subprocess, "run", return_value=subprocess.CompletedProcess(
                    ["gh"], 0, "selected-value\n", "")) as process:
            self.assertEqual(pod_test.token_for("expected-account"), "selected-value")
            self.assertNotIn("GH_TOKEN", process.call_args.kwargs["env"])
            self.assertNotIn("GITHUB_TOKEN", process.call_args.kwargs["env"])
            self.assertEqual(process.call_args.args[0][-2:], ["--user", "expected-account"])

    def test_missing_token_does_not_print_subprocess_output(self) -> None:
        with patch.object(pod_test.subprocess, "run", return_value=subprocess.CompletedProcess(
                ["gh"], 1, "potentially-sensitive", "potentially-sensitive")):
            with self.assertRaises(RuntimeError) as error:
                pod_test.token_for("account")
            self.assertNotIn("potentially-sensitive", str(error.exception))

    def test_token_is_stdin_only(self) -> None:
        with patch.object(pod_test, "kubectl", return_value="ok") as kubectl:
            pod_test.pod_command("personal", "sensitive", ["gh", "api", "user"])
            self.assertNotIn("sensitive", repr(kubectl.call_args.args))
            self.assertEqual(kubectl.call_args.kwargs["data"], "sensitive\n")
            self.assertEqual(kubectl.call_args.args[:3], ("exec", "-i", "personal"))

    def test_wrong_account_stops_before_command(self) -> None:
        with patch.object(pod_test, "token_for", return_value="value"), \
                patch.object(pod_test, "pod_command", return_value="wrong-account\n") as command:
            with self.assertRaisesRegex(RuntimeError, "Account mismatch"):
                pod_test.execute("expected-account", "enterprise", ["gh", "pr", "create"])
            self.assertEqual(command.call_count, 1)

    def test_exec_uses_verified_account(self) -> None:
        with patch.object(pod_test, "token_for", return_value="value"), \
                patch.object(pod_test, "pod_command", side_effect=["account\n", "ok\n"]) as command:
            pod_test.execute("account", "personal", ["gh", "api", "user"])
            self.assertEqual(command.call_count, 2)

    def test_context_is_never_implicit(self) -> None:
        with patch.object(pod_test, "run", return_value="ok") as run:
            pod_test.kubectl("get", "pods")
            self.assertEqual(run.call_args.args[0][:5], ["kubectl", "--context", "rancher-desktop",
                                                        "-n", "gh-auth-pod-test"])

    def test_cleanup_refuses_unowned_namespace(self) -> None:
        with patch.object(pod_test.sys, "argv", ["pod-test.py", "cleanup"]), \
                patch.object(pod_test, "kubectl", return_value='{"metadata":{"labels":{}}}') as kubectl:
            with self.assertRaisesRegex(RuntimeError, "unowned namespace"):
                pod_test.main()
            self.assertEqual(kubectl.call_count, 1)

    def test_prepare_pods_have_no_credentials_or_cluster_token(self) -> None:
        with patch.object(pod_test, "kubectl", return_value="") as kubectl:
            pod_test.prepare()
            documents = [json.loads(call.kwargs["data"]) for call in kubectl.call_args_list
                         if "data" in call.kwargs]
            self.assertEqual(len(documents), 3)
            for document in documents[1:]:
                self.assertFalse(document["spec"]["automountServiceAccountToken"])
                self.assertTrue(document["spec"]["securityContext"]["runAsNonRoot"])
                self.assertNotIn("secret", json.dumps(document).lower())
                self.assertNotIn("GH_TOKEN", json.dumps(document))

    def test_check_stops_at_wrong_host_identity(self) -> None:
        with patch.object(pod_test, "token_for", return_value="value"), \
                patch.object(pod_test, "run", return_value="other\n"), \
                patch.object(pod_test, "pod_command", return_value="account\n") as command:
            with self.assertRaisesRegex(RuntimeError, "Account mismatch"):
                pod_test.check("account", "personal", "owner/repo")
            self.assertEqual(command.call_count, 1)

    def test_pr_smoke_creates_no_commits_and_cleans_remote_refs(self) -> None:
        self._pr_smoke_case()

    def test_failed_pr_create_still_removes_test_refs(self) -> None:
        self._pr_smoke_case(fail_create=True)

    def test_failed_pr_close_preserves_remote_refs(self) -> None:
        self._pr_smoke_case(fail_close=True)

    def _pr_smoke_case(self, fail_create: bool = False, fail_close: bool = False) -> None:
        commands = []

        def execute(pod: str, token: str, command: list[str]) -> str:
            commands.append(command)
            if command[:2] == ["gh", "api"]:
                return "main\n"
            if "rev-parse" in command:
                return "existing-commit\n"
            if command[:3] == ["gh", "pr", "create"]:
                if fail_create:
                    raise RuntimeError("create rejected")
                return "https://github.com/owner/repo/pull/1\n"
            if command[:3] == ["gh", "pr", "close"] and fail_close:
                raise RuntimeError("close rejected")
            if command[:3] == ["gh", "pr", "view"]:
                if command[-1] == ".state":
                    return "CLOSED\n"
                return json.dumps({"author": {"login": "account"}, "isDraft": True,
                    "baseRefName": "codex/gh-auth-smoke-base-fixed",
                    "headRefName": "codex/gh-auth-smoke-head-fixed"})
            return ""

        with patch.object(pod_test, "check"), \
                patch.object(pod_test, "token_for", return_value="value"), \
                patch.object(pod_test.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed")), \
                patch.object(pod_test, "pod_command", side_effect=execute), \
                patch.object(pod_test, "kubectl", return_value=""):
            if fail_create or fail_close:
                with self.assertRaises(RuntimeError):
                    pod_test.pr_smoke("account", "personal", "owner/repo")
            else:
                pod_test.pr_smoke("account", "personal", "owner/repo")
        self.assertFalse(any("commit" in command or "add" in command[:3] for command in commands))
        deleted = [command for command in commands if "--delete" in command]
        self.assertEqual(len(deleted), 0 if fail_close else 1)
        if deleted:
            self.assertEqual(deleted[0][-2:], ["codex/gh-auth-smoke-base-fixed",
                                              "codex/gh-auth-smoke-head-fixed"])


if __name__ == "__main__":
    unittest.main()
