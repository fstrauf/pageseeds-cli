"""Centralized credential resolution for Google Search Console.

Precedence (highest to lowest):
1. Explicit arguments/paths passed to functions
2. Machine-local secrets.env (GSC_SERVICE_ACCOUNT_PATH or GOOGLE_APPLICATION_CREDENTIALS)
3. Target repo .env.local/.env files
4. Shell environment variables (fallback only)

This ensures secrets.env is the authoritative source of truth.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Mapping, Sequence

# Environment file precedence (highest first)
DEFAULT_SECRETS_ENV = Path.home() / ".config" / "automation" / "secrets.env"

SERVICE_ACCOUNT_ENV_KEYS: Sequence[str] = (
    "GSC_SERVICE_ACCOUNT_PATH",
    "GOOGLE_APPLICATION_CREDENTIALS",
)
OAUTH_CLIENT_SECRETS_ENV_KEYS: Sequence[str] = ("GSC_REPORT_OAUTH_CLIENT_SECRETS",)


def _read_env_file(path: Path) -> dict[str, str]:
    """Read key=value pairs from an env file."""
    values: dict[str, str] = {}
    if not path.exists():
        return values

    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key:
                values[key] = value
    except Exception:
        pass
    return values


def _iter_secret_sources(repo_root: Path | None = None) -> Iterable[tuple[Path, dict[str, str]]]:
    """Yield (path, values) for secret sources in priority order."""
    sources = [DEFAULT_SECRETS_ENV]
    
    if repo_root is not None:
        sources.extend([
            Path(repo_root) / ".env.local",
            Path(repo_root) / ".env",
        ])
    
    for path in sources:
        resolved = path.expanduser().resolve()
        if resolved.exists():
            yield resolved, _read_env_file(resolved)


def _first_non_empty(values: dict[str, str], keys: Sequence[str]) -> str | None:
    """Return first non-empty value for given keys."""
    for key in keys:
        val = (values.get(key) or "").strip()
        if val:
            return val
    return None


def _looks_like_service_account_json(path: str) -> bool:
    """Check if file contains valid service account credentials."""
    try:
        with open(os.path.expanduser(path), "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return False
    return bool(
        payload.get("type") == "service_account"
        or ("client_email" in payload and "private_key" in payload)
    )


def resolve_service_account_path(
    explicit_path: str | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Resolve service account path with secrets.env as authoritative source.
    
    Precedence:
    1. explicit_path argument
    2. Machine-local secrets.env (GSC_SERVICE_ACCOUNT_PATH or GOOGLE_APPLICATION_CREDENTIALS)
    3. Target repo .env.local/.env
    4. Shell GOOGLE_APPLICATION_CREDENTIALS (fallback)
    
    Args:
        explicit_path: Explicit path passed via CLI argument
        repo_root: Optional repo root to check for .env files
        
    Returns:
        Path to service account JSON file, or None if not found
    """
    # 1. Explicit path (highest priority)
    if explicit_path:
        path = explicit_path.strip()
        if _looks_like_service_account_json(path):
            return os.path.expanduser(path)
        return None

    # 2-3. Check env files first (authoritative source)
    for _, values in _iter_secret_sources(repo_root):
        candidate = _first_non_empty(values, SERVICE_ACCOUNT_ENV_KEYS)
        if candidate and _looks_like_service_account_json(candidate):
            return os.path.expanduser(candidate)

    # 4. Fallback: shell environment variable
    env_path = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if env_path and _looks_like_service_account_json(env_path):
        return os.path.expanduser(env_path)

    return None


def resolve_oauth_client_secrets_path(
    explicit_path: str | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Resolve OAuth client secrets path.
    
    Precedence:
    1. explicit_path argument
    2. Machine-local secrets.env (GSC_REPORT_OAUTH_CLIENT_SECRETS)
    3. Target repo .env.local/.env
    4. Shell GSC_REPORT_OAUTH_CLIENT_SECRETS (fallback)
    
    Args:
        explicit_path: Explicit path passed via CLI argument
        repo_root: Optional repo root to check for .env files
        
    Returns:
        Path to OAuth client secrets JSON file, or None if not found
    """
    # 1. Explicit path
    if explicit_path:
        path = Path(explicit_path.strip()).expanduser()
        return str(path) if path.exists() else None

    # 2-3. Check env files first
    for _, values in _iter_secret_sources(repo_root):
        candidate = _first_non_empty(values, OAUTH_CLIENT_SECRETS_ENV_KEYS)
        if candidate:
            path = Path(candidate).expanduser()
            if path.exists():
                return str(path)

    # 4. Fallback: shell environment variable
    env_path = (os.environ.get("GSC_REPORT_OAUTH_CLIENT_SECRETS") or "").strip()
    if env_path:
        path = Path(env_path).expanduser()
        if path.exists():
            return str(path)

    return None


def get_credential_info(repo_root: Path | None = None) -> dict:
    """Get diagnostic info about credential resolution.
    
    Useful for debugging credential issues.
    """
    info = {
        "secrets_env_exists": DEFAULT_SECRETS_ENV.exists(),
        "secrets_env_path": str(DEFAULT_SECRETS_ENV),
        "shell_gac": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""),
        "resolved_path": resolve_service_account_path(repo_root=repo_root),
        "env_file_values": {},
    }
    
    for path, values in _iter_secret_sources(repo_root):
        info["env_file_values"][str(path)] = {
            k: v for k, v in values.items()
            if any(keyword in k for keyword in ["GSC", "GOOGLE", "SERVICE_ACCOUNT"])
        }
    
    return info
