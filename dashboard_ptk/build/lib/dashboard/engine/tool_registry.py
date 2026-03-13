"""Centralized deterministic CLI execution."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .env_resolver import EnvResolver
from .types import ExecutionContext, ToolResult


@dataclass
class ToolSpec:
    """Named deterministic tool invocation."""

    tool_id: str
    executable: str
    arg_template: list[str]
    timeout: int = 300
    retries: int = 0
    output_mode: str = "json"


class ToolRegistry:
    """Registry for deterministic command execution with unified behavior."""

    def __init__(self):
        self.specs: dict[str, ToolSpec] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(
            ToolSpec(
                tool_id="gsc_indexing_report",
                executable="automation-cli",
                arg_template=[
                    "seo",
                    "gsc-indexing-report",
                    "--site",
                    "{site}",
                    "--sitemap-url",
                    "{sitemap_url}",
                    "--limit",
                    "{limit}",
                    "--workers",
                    "{workers}",
                ],
                timeout=300,
                retries=0,
                output_mode="json",
            )
        )
        self.register(
            ToolSpec(
                tool_id="keyword_generator",
                executable="seo-cli",
                arg_template=["keyword-generator", "--keyword", "{keyword}", "--country", "{country}"],
                timeout=180,
                retries=0,
                output_mode="json",
            )
        )
        self.register(
            ToolSpec(
                tool_id="keyword_difficulty_batch",
                executable="seo-cli",
                arg_template=[
                    "batch-keyword-difficulty",
                    "--keywords-file",
                    "{keywords_file}",
                    "--country",
                    "{country}",
                ],
                timeout=180,
                retries=0,
                output_mode="json",
            )
        )

    def register(self, spec: ToolSpec) -> None:
        self.specs[spec.tool_id] = spec

    def run(self, tool_id: str, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """Run named tool spec with rendered params."""
        spec = self.specs.get(tool_id)
        if not spec:
            return ToolResult(success=False, command=[], stderr=f"Unknown tool_id: {tool_id}", error_type="config")

        rendered_args = [arg.format(**params) for arg in spec.arg_template]
        command = [spec.executable] + rendered_args
        return self._run_subprocess(
            command,
            cwd=context.repo_root,
            timeout=spec.timeout,
            retries=spec.retries,
            env_overrides=None,
        )

    def run_command(
        self,
        command: list[str],
        context: ExecutionContext,
        timeout: int = 300,
        retries: int = 0,
        env_overrides: dict[str, str] | None = None,
    ) -> ToolResult:
        """Run ad-hoc command through centralized runtime.

        Supports legacy commands that start with automation namespace tokens
        (e.g. ["seo", ...], ["posthog", ...]).
        """
        normalized = self._normalize_legacy_command(command)
        return self._run_subprocess(
            normalized,
            cwd=context.repo_root,
            timeout=timeout,
            retries=retries,
            env_overrides=env_overrides,
        )

    def _normalize_legacy_command(self, command: list[str]) -> list[str]:
        if not command:
            return command

        first = command[0]
        if first in {"automation-cli", "seo-cli", "seo-content-cli", "kimi"}:
            return command

        automation_namespaces = {"seo", "repo", "reddit", "skills", "geo", "posthog", "campaign"}
        if first in automation_namespaces:
            return ["automation-cli"] + command

        return command

    def _load_env(self, repo_root: Path, env_overrides: dict[str, str] | None) -> dict[str, str]:
        return EnvResolver(repo_root=repo_root).build_env(overrides=env_overrides)

    def _run_subprocess(
        self,
        command: list[str],
        cwd: Path,
        timeout: int,
        retries: int,
        env_overrides: dict[str, str] | None,
    ) -> ToolResult:
        if not command:
            return ToolResult(success=False, command=[], stderr="No command provided", error_type="config")

        executable = command[0]
        executable_path = shutil.which(executable)
        if not executable_path:
            return ToolResult(
                success=False,
                command=command,
                stderr=f"Executable not found in PATH: {executable}",
                error_type="not_found",
            )

        full_cmd = [executable_path] + command[1:]
        env = self._load_env(cwd, env_overrides)

        attempts = retries + 1
        last_result: ToolResult | None = None

        for _ in range(attempts):
            try:
                completed = subprocess.run(
                    full_cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(cwd),
                    timeout=timeout,
                    env=env,
                )
                last_result = ToolResult(
                    success=completed.returncode == 0,
                    command=command,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    returncode=completed.returncode,
                    error_type=None if completed.returncode == 0 else "exit_nonzero",
                )
                if last_result.success:
                    return last_result
            except subprocess.TimeoutExpired as exc:
                last_result = ToolResult(
                    success=False,
                    command=command,
                    stderr=f"Timeout after {timeout}s: {exc}",
                    error_type="timeout",
                )
            except Exception as exc:  # pragma: no cover - defensive path
                last_result = ToolResult(
                    success=False,
                    command=command,
                    stderr=str(exc),
                    error_type="exception",
                )

        return last_result or ToolResult(success=False, command=command, stderr="Unknown error", error_type="exception")
