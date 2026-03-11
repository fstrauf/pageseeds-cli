"""Regression tests for Reddit history path resolution."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.history_paths import resolve_reddit_history_path


def test_reddit_history_path_uses_repo_automation_directory() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        expected = (
            repo_root.resolve()
            / ".github"
            / "automation"
            / "reddit"
            / "_posted_history.json"
        )
        resolved = resolve_reddit_history_path(repo_root)
        assert resolved == expected


if __name__ == "__main__":
    test_reddit_history_path_uses_repo_automation_directory()
    print("ok")
