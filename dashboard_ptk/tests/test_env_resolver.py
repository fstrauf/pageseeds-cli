"""Tests for shared environment resolution precedence."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.env_resolver import EnvResolver


def test_build_env_uses_consistent_precedence() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        repo_root = tmp_root / "target_repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        automation_root = tmp_root / "automation_repo"
        automation_root.mkdir(parents=True, exist_ok=True)

        fake_home = tmp_root / "home"
        secrets_dir = fake_home / ".config" / "automation"
        secrets_dir.mkdir(parents=True, exist_ok=True)

        # Highest priority file source.
        (secrets_dir / "secrets.env").write_text("ONLY_SECRETS=secrets\nSHARED=secrets\n")
        (repo_root / ".env.local").write_text("ONLY_LOCAL=local\nSHARED=local\n")
        (repo_root / ".env").write_text("ONLY_REPO=repo\nSHARED=repo\n")
        (automation_root / ".env").write_text("ONLY_AUTOMATION=automation\nSHARED=automation\n")

        resolver = EnvResolver(repo_root=repo_root, automation_root=automation_root)
        with patch("dashboard.engine.env_resolver.Path.home", return_value=fake_home):
            env = resolver.build_env(base_env={"FROM_ENV": "env", "SHARED": "env"}, overrides={"OVERRIDE": "x"})

        assert env["FROM_ENV"] == "env"
        assert env["SHARED"] == "env"  # Real env always wins.
        assert env["ONLY_SECRETS"] == "secrets"
        assert env["ONLY_LOCAL"] == "local"
        assert env["ONLY_REPO"] == "repo"
        assert env["ONLY_AUTOMATION"] == "automation"
        assert env["OVERRIDE"] == "x"


def test_resolve_key_reports_empty_then_fallback_source() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        repo_root = tmp_root / "target_repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        automation_root = tmp_root / "automation_repo"
        automation_root.mkdir(parents=True, exist_ok=True)
        (automation_root / ".env").write_text("REDDIT_REFRESH_TOKEN=from_automation\n")
        fake_home = tmp_root / "home"
        fake_home.mkdir(parents=True, exist_ok=True)

        resolver = EnvResolver(repo_root=repo_root, automation_root=automation_root)
        with patch.dict(os.environ, {"REDDIT_REFRESH_TOKEN": "   "}, clear=True):
            with patch("dashboard.engine.env_resolver.Path.home", return_value=fake_home):
                token, source, saw_empty = resolver.resolve_key("REDDIT_REFRESH_TOKEN")

        assert token == "from_automation"
        assert source == str((automation_root / ".env").resolve())
        assert saw_empty


if __name__ == "__main__":
    test_build_env_uses_consistent_precedence()
    test_resolve_key_reports_empty_then_fallback_source()
    print("ok")
