"""Shared content directory resolution for preflight and runtime flows."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import PROJECTS_CONFIG


COMMON_CONTENT_DIR_RELATIVE = (
    "webapp/content/blog",
    "src/blog/posts",
    "src/content",
    "content/blog",
    "content",
    "posts",
    "blog",
)


@dataclass
class ContentDirResolution:
    """Resolution details for content directory discovery."""

    selected: Path | None = None
    selected_source: str | None = None  # configured | auto_with_markdown | auto_empty
    selected_has_markdown: bool = False
    configured_path: Path | None = None
    configured_exists: bool = False
    with_markdown: list[Path] = field(default_factory=list)
    empty_candidates: list[Path] = field(default_factory=list)
    searched_candidates: list[Path] = field(default_factory=list)


def resolve_content_dir(
    *,
    repo_root: Path,
    website_id: str | None = None,
    include_empty_auto_fallback: bool = False,
    projects_config_path: Path | None = None,
) -> ContentDirResolution:
    """Resolve content directory using configured override + common fallback order."""
    root = Path(repo_root).expanduser().resolve()
    resolution = ContentDirResolution()

    configured = _configured_content_dir(
        repo_root=root,
        website_id=website_id,
        projects_config_path=projects_config_path,
    )
    if configured is not None:
        resolution.configured_path = configured
        resolution.configured_exists = configured.exists() and configured.is_dir()
        if resolution.configured_exists:
            has_markdown = _dir_has_markdown(configured)
            resolution.selected = configured
            resolution.selected_source = "configured"
            resolution.selected_has_markdown = has_markdown
            return resolution

    for rel_path in COMMON_CONTENT_DIR_RELATIVE:
        candidate = root / rel_path
        resolution.searched_candidates.append(candidate)
        if not candidate.exists() or not candidate.is_dir():
            continue
        if _dir_has_markdown(candidate):
            resolution.with_markdown.append(candidate)
            if resolution.selected is None:
                resolution.selected = candidate
                resolution.selected_source = "auto_with_markdown"
                resolution.selected_has_markdown = True
        else:
            resolution.empty_candidates.append(candidate)

    if resolution.selected is None and include_empty_auto_fallback and resolution.empty_candidates:
        resolution.selected = resolution.empty_candidates[0]
        resolution.selected_source = "auto_empty"
        resolution.selected_has_markdown = False

    return resolution


def _configured_content_dir(
    *,
    repo_root: Path,
    website_id: str | None,
    projects_config_path: Path | None,
) -> Path | None:
    config_path = Path(projects_config_path).expanduser().resolve() if projects_config_path else PROJECTS_CONFIG
    if not config_path.exists():
        return None

    try:
        payload = json.loads(config_path.read_text())
    except Exception:
        return None

    projects = payload.get("projects", [])
    if not isinstance(projects, list):
        return None

    normalized_repo = repo_root.expanduser().resolve()
    match = None

    if website_id:
        for project in projects:
            if not isinstance(project, dict):
                continue
            if str(project.get("website_id", "")) != website_id:
                continue
            repo_field = project.get("repo_root")
            if not repo_field:
                continue
            try:
                if Path(repo_field).expanduser().resolve() == normalized_repo:
                    match = project
                    break
            except Exception:
                continue

    if match is None:
        for project in projects:
            if not isinstance(project, dict):
                continue
            repo_field = project.get("repo_root")
            if not repo_field:
                continue
            try:
                if Path(repo_field).expanduser().resolve() == normalized_repo:
                    match = project
                    break
            except Exception:
                continue

    if not match:
        return None
    content_dir = str(match.get("content_dir", "")).strip()
    if not content_dir:
        return None
    return Path(content_dir).expanduser().resolve()


def _dir_has_markdown(path: Path) -> bool:
    return any(path.glob("*.md")) or any(path.glob("*.mdx"))
