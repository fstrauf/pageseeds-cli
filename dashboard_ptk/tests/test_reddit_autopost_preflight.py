"""Tests for Reddit auto-post preflight auth behavior."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.models import Project, Task
from dashboard.tasks.reddit import RedditRunner


class DummySession:
    def __init__(self, responses: list[str]):
        self._responses = responses[:]

    def prompt(self, _message: str) -> str:
        return self._responses.pop(0) if self._responses else ""


class DummyTaskList:
    def __init__(self, repo_root: Path):
        self.automation_dir = repo_root / ".github" / "automation"
        self.automation_dir.mkdir(parents=True, exist_ok=True)
        (self.automation_dir / "reddit").mkdir(parents=True, exist_ok=True)
        self.artifacts_dir = self.automation_dir / "artifacts"
        self.task_results_dir = self.automation_dir / "task_results"
        self.artifacts_dir.mkdir(exist_ok=True)
        self.task_results_dir.mkdir(exist_ok=True)
        self.saved = False

    def save(self) -> None:
        self.saved = True


def _make_task() -> Task:
    return Task(
        id="TST-001",
        type="reddit_reply",
        title="Reply: Test reddit thread",
        phase="implementation",
        status="todo",
        notes="Thanks for sharing this. Tracking net worth over time changed how I think about daily spending.",
        post_id="1abc123",
        subreddit="ynab",
        post_date=datetime.now().strftime("%Y-%m-%d"),
    )


def _make_runner(repo_root: Path, responses: list[str]) -> tuple[RedditRunner, DummyTaskList]:
    task_list = DummyTaskList(repo_root)
    project = Project(name="Test", website_id="test", repo_root=str(repo_root))
    runner = RedditRunner(task_list, project, DummySession(responses))
    return runner, task_list


def test_reply_autopost_missing_auth_blocks_before_cli_call() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        runner, task_list = _make_runner(Path(tmpdir), responses=["2"])
        task = _make_task()

        runner._resolve_reddit_refresh_token = lambda: (None, None, False)
        called = {"value": False}

        def _never_called(*_args, **_kwargs):
            called["value"] = True
            return False, "", ""

        runner.run_cli_command = _never_called

        result = runner._run_reply_task(task)

        assert not result
        assert not called["value"]
        assert not task_list.saved


def test_reply_autopost_passes_resolved_token_to_cli() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        runner, task_list = _make_runner(Path(tmpdir), responses=["2", "yes"])
        task = _make_task()
        runner._resolve_reddit_refresh_token = lambda: ("token-123", "test-source", False)

        captured: dict[str, object] = {"calls": []}

        def _fake_run_cli(cmd, cwd=None, timeout=300, env_overrides=None):
            captured["calls"].append(
                {"cmd": cmd, "timeout": timeout, "env_overrides": env_overrides}
            )
            if cmd == ["reddit", "auth-status"]:
                return True, '{"success": true, "authenticated": true, "error": null}', ""
            return True, '{"success": true, "comment_id": "xyz"}', ""

        runner.run_cli_command = _fake_run_cli

        result = runner._run_reply_task(task)

        assert result
        assert task.status == "done"
        assert task_list.saved
        calls = captured["calls"]
        assert len(calls) == 2
        assert calls[0]["cmd"] == ["reddit", "auth-status"]
        assert calls[0]["timeout"] == 45
        assert calls[0]["env_overrides"] == {"REDDIT_REFRESH_TOKEN": "token-123"}
        assert calls[1]["cmd"] == ["reddit", "submit-comment", "--post-id", "1abc123", "--text", task.notes]
        assert calls[1]["env_overrides"] == {"REDDIT_REFRESH_TOKEN": "token-123"}


def test_reply_autopost_batch_auto_confirm_skips_per_task_confirmation() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        runner, task_list = _make_runner(Path(tmpdir), responses=[])
        task = _make_task()
        runner._resolve_reddit_refresh_token = lambda: ("token-123", "test-source", False)
        runner.set_execution_context(
            {
                "auto_confirm": True,
                "reddit_reply": {"action": "auto_post", "skip_confirm": True},
            }
        )

        captured: dict[str, object] = {"calls": []}

        def _fake_run_cli(cmd, cwd=None, timeout=300, env_overrides=None):
            captured["calls"].append(
                {"cmd": cmd, "timeout": timeout, "env_overrides": env_overrides}
            )
            if cmd == ["reddit", "auth-status"]:
                return True, '{"success": true, "authenticated": true, "error": null}', ""
            return True, '{"success": true, "comment_id": "xyz"}', ""

        runner.run_cli_command = _fake_run_cli

        result = runner._run_reply_task(task)

        assert result
        assert task.status == "done"
        assert task_list.saved
        calls = captured["calls"]
        assert len(calls) == 2
        assert calls[0]["cmd"] == ["reddit", "auth-status"]
        assert calls[1]["cmd"] == ["reddit", "submit-comment", "--post-id", "1abc123", "--text", task.notes]


def test_reply_autopost_blocks_when_cli_auth_status_reports_invalid_token() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        runner, task_list = _make_runner(Path(tmpdir), responses=["2"])
        task = _make_task()
        runner._resolve_reddit_refresh_token = lambda: ("token-123", "test-source", False)

        captured: dict[str, object] = {"calls": []}

        def _fake_run_cli(cmd, cwd=None, timeout=300, env_overrides=None):
            captured["calls"].append(
                {"cmd": cmd, "timeout": timeout, "env_overrides": env_overrides}
            )
            if cmd == ["reddit", "auth-status"]:
                return True, '{"success": true, "authenticated": false, "error": "invalid_grant"}', ""
            return True, '{"success": true, "comment_id": "xyz"}', ""

        runner.run_cli_command = _fake_run_cli

        result = runner._run_reply_task(task)

        assert not result
        assert not task_list.saved
        calls = captured["calls"]
        assert len(calls) == 1
        assert calls[0]["cmd"] == ["reddit", "auth-status"]


def test_resolve_reddit_token_ignores_empty_env_and_falls_back_to_secrets() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        repo_root = tmp_root / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        runner, _ = _make_runner(repo_root, responses=[])

        fake_home = tmp_root / "home"
        secrets_dir = fake_home / ".config" / "automation"
        secrets_dir.mkdir(parents=True, exist_ok=True)
        (secrets_dir / "secrets.env").write_text("REDDIT_REFRESH_TOKEN=from_secrets\n")

        with patch.dict(os.environ, {"REDDIT_REFRESH_TOKEN": "   "}, clear=False):
            with patch("dashboard.engine.env_resolver.Path.home", return_value=fake_home):
                token, source, saw_empty = runner._resolve_reddit_refresh_token()

        assert token == "from_secrets"
        assert source and source.endswith("secrets.env")
        assert saw_empty


def test_resolve_reddit_token_falls_back_to_automation_workspace_env() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        repo_root = tmp_root / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        runner, _ = _make_runner(repo_root, responses=[])

        automation_env = tmp_root / ".env"
        automation_env.write_text("REDDIT_REFRESH_TOKEN=from_automation_env\n")

        fake_home = tmp_root / "home"
        fake_home.mkdir(parents=True, exist_ok=True)

        with patch.dict(os.environ, {}, clear=True):
            with patch("dashboard.engine.env_resolver.Path.home", return_value=fake_home):
                with patch.object(
                    RedditRunner,
                    "_automation_workspace_env_path",
                    return_value=automation_env,
                ):
                    token, source, saw_empty = runner._resolve_reddit_refresh_token()

        assert token == "from_automation_env"
        assert source == str(automation_env.resolve())
        assert not saw_empty


if __name__ == "__main__":
    test_reply_autopost_missing_auth_blocks_before_cli_call()
    test_reply_autopost_passes_resolved_token_to_cli()
    test_reply_autopost_batch_auto_confirm_skips_per_task_confirmation()
    test_reply_autopost_blocks_when_cli_auth_status_reports_invalid_token()
    test_resolve_reddit_token_ignores_empty_env_and_falls_back_to_secrets()
    test_resolve_reddit_token_falls_back_to_automation_workspace_env()
    print("ok")
