"""Shared environment resolution for dashboard runtime and preflight checks."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


class EnvResolver:
    """Resolve env vars from process env + standard env files with stable precedence."""

    def __init__(self, repo_root: Path, automation_root: Path | None = None):
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.automation_root = (
            Path(automation_root).expanduser().resolve()
            if automation_root is not None
            else self.default_automation_root()
        )

    @staticmethod
    def default_automation_root() -> Path:
        # /.../automation/dashboard_ptk/dashboard/engine/env_resolver.py -> /.../automation
        return Path(__file__).resolve().parents[3]

    def env_files(self) -> list[Path]:
        """Ordered highest-priority-first for first-write-wins merge."""
        files = [
            Path.home() / ".config" / "automation" / "secrets.env",
            self.repo_root / ".env.local",
            self.repo_root / ".env",
            self.automation_root / ".env",
        ]
        unique: list[Path] = []
        seen: set[Path] = set()
        for path in files:
            resolved = path.expanduser().resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(resolved)
        return unique

    def build_env(
        self,
        base_env: Mapping[str, str] | None = None,
        overrides: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """Build subprocess environment using consistent source precedence."""
        env = dict(base_env) if base_env is not None else os.environ.copy()

        # Prevent subprocesses from inheriting dashboard venv context accidentally.
        env.pop("VIRTUAL_ENV", None)

        for env_file in self.env_files():
            for key, value in self._read_env_file(env_file).items():
                env.setdefault(key, value)

        if overrides:
            env.update({str(k): str(v) for k, v in overrides.items()})
        return env

    def resolve_key(
        self,
        key: str,
        base_env: Mapping[str, str] | None = None,
    ) -> tuple[str | None, str | None, bool]:
        """Resolve a single key and return (value, source, saw_empty_value)."""
        source_env = base_env if base_env is not None else os.environ
        saw_empty = False

        if key in source_env:
            raw = source_env.get(key, "")
            stripped = raw.strip() if raw is not None else ""
            if stripped:
                return stripped, f"env:{key}", False
            saw_empty = True

        for env_file in self.env_files():
            value = self._read_env_key(env_file, key)
            if value is None:
                continue
            stripped = value.strip()
            if stripped:
                return stripped, str(env_file), saw_empty
            saw_empty = True

        return None, None, saw_empty

    @staticmethod
    def _read_env_key(env_file: Path, key: str) -> str | None:
        return EnvResolver._read_env_file(env_file).get(key)

    @staticmethod
    def _read_env_file(env_file: Path) -> dict[str, str]:
        data: dict[str, str] = {}
        if not env_file.exists():
            return data

        try:
            for raw_line in env_file.read_text().splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :].strip()
                if "=" not in line:
                    continue
                parsed_key, value = line.split("=", 1)
                key = parsed_key.strip()
                if not key:
                    continue
                data[key] = value.strip().strip("\"'")
        except Exception:
            return {}
        return data
