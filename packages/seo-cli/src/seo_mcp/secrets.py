"""Minimal secrets loader for seo-mcp.

Goal: make CLIs work across repos without copying .env files everywhere.

Loading order (never overrides already-set environment variables):
1) Explicit env vars (e.g. CAPSOLVER_API_KEY)
2) $AUTOMATION_SECRETS_FILE (optional)
3) ~/.config/automation/secrets.env
4) automation repo root `.env` (best-effort discovery from this package location)
5) nearest `.env` walking up from CWD
"""

from __future__ import annotations

import os
from pathlib import Path


def _parse_env_file_for_key(path: Path, key: str) -> str:
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if not line.startswith(key + "="):
                continue
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    except Exception:
        return ""
    return ""


def _find_ancestor_dir_with(start: Path, rel: Path) -> Path | None:
    start = start.resolve()
    for p in (start,) + tuple(start.parents):
        if (p / rel).exists():
            return p
    return None


def _automation_repo_root_from_package() -> Path | None:
    """Best-effort: find the automation repo root that contains .github/skills."""
    here = Path(__file__).resolve().parent
    return _find_ancestor_dir_with(here, Path(".github") / "skills")


def load_capsolver_api_key() -> bool:
    """Ensure CAPSOLVER_API_KEY is present in os.environ (setdefault only)."""
    key = "CAPSOLVER_API_KEY"
    if os.environ.get(key):
        return True

    # 1) Explicit secrets file override
    override = os.environ.get("AUTOMATION_SECRETS_FILE", "").strip()
    if override:
        p = Path(os.path.expanduser(override))
        if p.is_file():
            v = _parse_env_file_for_key(p, key)
            if v:
                os.environ.setdefault(key, v)
                return True

    # 2) Standard per-machine secrets file
    p = Path.home() / ".config" / "automation" / "secrets.env"
    if p.is_file():
        v = _parse_env_file_for_key(p, key)
        if v:
            os.environ.setdefault(key, v)
            return True

    # 3) Automation repo root `.env` (your current setup)
    repo_root = _automation_repo_root_from_package()
    if repo_root is not None:
        dotenv = repo_root / ".env"
        if dotenv.is_file():
            v = _parse_env_file_for_key(dotenv, key)
            if v:
                os.environ.setdefault(key, v)
                return True

    # 4) Search up from CWD for a .env (repo-local)
    for directory in (Path.cwd(), *Path.cwd().parents):
        dotenv_path = directory / ".env"
        if not dotenv_path.is_file():
            continue
        v = _parse_env_file_for_key(dotenv_path, key)
        if v:
            os.environ.setdefault(key, v)
            return True

    return bool(os.environ.get(key))

