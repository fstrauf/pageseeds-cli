"""Path helpers for persisted workflow history artifacts."""
from __future__ import annotations

from pathlib import Path


def resolve_reddit_history_path(repo_root: str | Path | None = None) -> Path:
    """Resolve the canonical Reddit history path for a project repo."""
    root = Path(repo_root).expanduser().resolve() if repo_root else Path.cwd().resolve()
    return root / ".github" / "automation" / "reddit" / "_posted_history.json"

