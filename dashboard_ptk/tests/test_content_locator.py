"""Tests for shared content directory resolution."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.content_locator import resolve_content_dir


def test_content_locator_prefers_configured_override() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        configured_dir = repo_root / "src" / "blog" / "posts"
        auto_dir = repo_root / "content" / "blog"
        configured_dir.mkdir(parents=True, exist_ok=True)
        auto_dir.mkdir(parents=True, exist_ok=True)
        (configured_dir / "001_configured.mdx").write_text("---\ndate: \"2026-03-04\"\n---\n")
        (auto_dir / "001_auto.mdx").write_text("---\ndate: \"2026-03-04\"\n---\n")

        projects_config = Path(tmpdir) / "projects.json"
        projects_config.write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "name": "Site",
                            "website_id": "site",
                            "repo_root": str(repo_root),
                            "content_dir": str(configured_dir),
                        }
                    ]
                }
            )
        )

        resolution = resolve_content_dir(
            repo_root=repo_root,
            website_id="site",
            include_empty_auto_fallback=True,
            projects_config_path=projects_config,
        )

        assert resolution.selected == configured_dir.resolve()
        assert resolution.selected_source == "configured"
        assert resolution.selected_has_markdown is True


def test_content_locator_falls_back_when_configured_missing() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        auto_dir = repo_root / "content" / "blog"
        auto_dir.mkdir(parents=True, exist_ok=True)
        (auto_dir / "001_auto.mdx").write_text("---\ndate: \"2026-03-04\"\n---\n")

        missing_configured = repo_root / "missing" / "posts"
        projects_config = Path(tmpdir) / "projects.json"
        projects_config.write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "name": "Site",
                            "website_id": "site",
                            "repo_root": str(repo_root),
                            "content_dir": str(missing_configured),
                        }
                    ]
                }
            )
        )

        resolution = resolve_content_dir(
            repo_root=repo_root,
            website_id="site",
            include_empty_auto_fallback=True,
            projects_config_path=projects_config,
        )

        assert resolution.configured_path == missing_configured.resolve()
        assert resolution.configured_exists is False
        assert resolution.selected == auto_dir.resolve()
        assert resolution.selected_source == "auto_with_markdown"


def test_content_locator_can_select_empty_candidate_when_allowed() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        empty_dir = repo_root / "content"
        empty_dir.mkdir(parents=True, exist_ok=True)

        resolution = resolve_content_dir(
            repo_root=repo_root,
            include_empty_auto_fallback=True,
        )

        assert resolution.selected == empty_dir.resolve()
        assert resolution.selected_source == "auto_empty"
        assert resolution.selected_has_markdown is False


if __name__ == "__main__":
    test_content_locator_prefers_configured_override()
    test_content_locator_falls_back_when_configured_missing()
    test_content_locator_can_select_empty_candidate_when_allowed()
    print("ok")
