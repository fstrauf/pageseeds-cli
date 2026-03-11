"""Tests for project activation preflight checks."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.preflight import ProjectPreflight
from dashboard.engine.types import ToolResult


class FakeToolRegistry:
    def __init__(self, result: ToolResult):
        self.result = result
        self.calls: list[dict] = []

    def run_command(self, command, context, timeout=300, env_overrides=None):
        self.calls.append(
            {
                "command": command,
                "repo_root": str(context.repo_root),
                "timeout": timeout,
                "env_overrides": env_overrides,
            }
        )
        return self.result


def test_preflight_initializes_missing_directories_and_reports_missing_articles() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)

        report = ProjectPreflight(
            repo_root=repo_root,
            website_id="coffee",
            check_cli=False,
            check_reddit_auth=False,
        ).run()

        assert (repo_root / ".github" / "automation").exists()
        assert (repo_root / ".github" / "automation" / "artifacts").exists()
        assert (repo_root / ".github" / "automation" / "task_results").exists()
        assert (repo_root / ".github" / "automation" / "reddit").exists()
        assert report.created_paths
        assert any(f.check == "articles_json" and f.severity == "error" for f in report.findings)


def test_preflight_reports_missing_required_cli() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        automation_dir = repo_root / ".github" / "automation"
        automation_dir.mkdir(parents=True, exist_ok=True)
        (automation_dir / "articles.json").write_text('{"articles": [], "nextArticleId": 1}')

        def _which(name: str):
            if name == "seo-cli":
                return None
            return f"/usr/local/bin/{name}"

        with patch("dashboard.engine.preflight.shutil.which", side_effect=_which):
            report = ProjectPreflight(
                repo_root=repo_root,
                website_id="coffee",
                required_clis=("automation-cli", "seo-cli", "seo-content-cli"),
                check_cli=True,
                check_reddit_auth=False,
            ).run()

        assert any(
            f.check == "missing_cli" and "seo-cli" in f.message and f.severity == "error"
            for f in report.findings
        )


def test_preflight_runs_reddit_auth_check_when_token_present() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        automation_dir = repo_root / ".github" / "automation"
        automation_dir.mkdir(parents=True, exist_ok=True)
        (automation_dir / "articles.json").write_text('{"articles": [], "nextArticleId": 1}')

        fake_registry = FakeToolRegistry(
            ToolResult(
                success=True,
                command=["automation-cli", "reddit", "auth-status"],
                stdout='{"success": true, "authenticated": false, "error": "invalid_grant"}',
            )
        )
        with patch.dict(os.environ, {"REDDIT_REFRESH_TOKEN": "token-123"}, clear=False):
            report = ProjectPreflight(
                repo_root=repo_root,
                website_id="coffee",
                tool_registry=fake_registry,
                check_cli=False,
                check_reddit_auth=True,
            ).run()

        assert len(fake_registry.calls) == 1
        assert fake_registry.calls[0]["command"] == ["automation-cli", "reddit", "auth-status"]
        assert fake_registry.calls[0]["env_overrides"] == {"REDDIT_REFRESH_TOKEN": "token-123"}
        assert any(
            f.check == "reddit_auth" and f.severity == "warning" and "not ready" in f.message.lower()
            for f in report.findings
        )


def test_preflight_reports_missing_configured_content_dir() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        repo_root = tmp / "repo"
        automation_dir = repo_root / ".github" / "automation"
        automation_dir.mkdir(parents=True, exist_ok=True)
        (automation_dir / "articles.json").write_text('{"articles": [], "nextArticleId": 1}')
        (repo_root / "content" / "blog").mkdir(parents=True, exist_ok=True)
        (repo_root / "content" / "blog" / "001_test.mdx").write_text("# test")

        projects_config = tmp / "projects.json"
        projects_config.write_text(
            '{"projects":[{"name":"Repo","website_id":"coffee","repo_root":"%s","content_dir":"%s"}]}'
            % (str(repo_root), str(repo_root / "missing-content"))
        )

        with patch("dashboard.engine.content_locator.PROJECTS_CONFIG", projects_config):
            report = ProjectPreflight(
                repo_root=repo_root,
                website_id="coffee",
                check_cli=False,
                check_reddit_auth=False,
            ).run()

        assert any(
            f.check == "content_dir_configured" and f.severity == "warning"
            for f in report.findings
        )
        assert any(
            f.check == "content_dir" and f.severity == "info" and "content/blog" in f.message
            for f in report.findings
        )


def test_preflight_fix_gitignore_exclusions() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        gitignore = repo_root / ".gitignore"
        gitignore.write_text("node_modules/\n")

        preflight = ProjectPreflight(
            repo_root=repo_root,
            website_id="coffee",
            check_cli=False,
            check_reddit_auth=False,
        )
        ok, _ = preflight.fix_gitignore_exclusions()
        assert ok is True

        content = gitignore.read_text()
        assert ".github/automation/" in content
        assert content.count(".github/automation/") == 1

        ok_again, _ = preflight.fix_gitignore_exclusions()
        assert ok_again is True
        content_again = gitignore.read_text()
        assert content_again.count(".github/automation/") == 1


if __name__ == "__main__":
    test_preflight_initializes_missing_directories_and_reports_missing_articles()
    test_preflight_reports_missing_required_cli()
    test_preflight_runs_reddit_auth_check_when_token_present()
    test_preflight_reports_missing_configured_content_dir()
    test_preflight_fix_gitignore_exclusions()
    print("ok")
