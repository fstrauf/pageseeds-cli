"""Tests for project manager config normalization behavior."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import importlib.util
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _bootstrap_repo(root: Path) -> None:
    automation_dir = root / ".github" / "automation"
    automation_dir.mkdir(parents=True, exist_ok=True)
    (automation_dir / "articles.json").write_text('{"articles": [], "nextArticleId": 1}')


def test_edit_project_normalizes_repo_and_content_dir() -> None:
    if importlib.util.find_spec("rich") is None:
        print("skipped (rich not installed)")
        return

    from dashboard.core.project_manager import ProjectManager

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        repo_a = tmp / "repo-a"
        repo_b = tmp / "repo-b"
        _bootstrap_repo(repo_a)
        _bootstrap_repo(repo_b)

        projects_path = tmp / "projects.json"
        projects_path.write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "name": "Example",
                            "website_id": "example",
                            "repo_root": str(repo_a),
                            "content_dir": "",
                        }
                    ]
                }
            )
        )

        with patch("dashboard.core.project_manager.PROJECTS_CONFIG", projects_path):
            manager = ProjectManager()
            ok, _ = manager.edit_project(
                "example",
                repo_root=str(repo_b),
                content_dir=str(repo_b / "content" / "blog"),
            )
            assert ok is True

            updated = manager.get_by_id("example")
            assert updated is not None
            assert updated.repo_root == str(repo_b.resolve())
            assert updated.content_dir == str((repo_b / "content" / "blog").resolve())

            payload = json.loads(projects_path.read_text())
            entry = payload["projects"][0]
            assert entry["repo_root"] == str(repo_b.resolve())
            assert entry["content_dir"] == str((repo_b / "content" / "blog").resolve())


if __name__ == "__main__":
    test_edit_project_normalizes_repo_and_content_dir()
    print("ok")
