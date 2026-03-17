"""Agent runtime with pluggable provider adapters (Kimi, GitHub Copilot, etc.)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from .types import AgentRawResult, ExecutionContext, PromptSpec


class AgentAdapter(ABC):
    """Adapter contract for agent providers."""

    provider: str = "unknown"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when adapter runtime is installed and callable."""

    @abstractmethod
    def run(self, prompt: PromptSpec, cwd: Path) -> AgentRawResult:
        """Execute a prompt and return raw output."""


class KimiAdapter(AgentAdapter):
    """Kimi CLI adapter (primary provider in v1)."""

    provider = "kimi"

    def is_available(self) -> bool:
        return shutil.which("kimi") is not None

    def run(self, prompt: PromptSpec, cwd: Path) -> AgentRawResult:
        if not self.is_available():
            return AgentRawResult(success=False, provider=self.provider, error="kimi CLI not found in PATH")

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as output_file:
            output_path = output_file.name

        try:
            env = os.environ.copy()
            with open(output_path, "w") as out_f:
                result = subprocess.run(
                    ["kimi", "--print", "-p", prompt.text],
                    stdout=out_f,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(cwd),
                    timeout=prompt.timeout,
                    env=env,
                )

            output_text = Path(output_path).read_text() if Path(output_path).exists() else ""
            if result.returncode == 0:
                return AgentRawResult(success=True, provider=self.provider, output_text=output_text)

            if output_text and len(output_text) > 120:
                return AgentRawResult(
                    success=True,
                    provider=self.provider,
                    output_text=output_text,
                    error=f"Agent exited non-zero ({result.returncode}) but output captured",
                )

            return AgentRawResult(
                success=False,
                provider=self.provider,
                output_text=output_text,
                error=f"Exit code {result.returncode}: {result.stderr}",
            )
        except subprocess.TimeoutExpired:
            partial = Path(output_path).read_text() if Path(output_path).exists() else ""
            if partial and len(partial) > 120:
                return AgentRawResult(
                    success=True,
                    provider=self.provider,
                    output_text=partial,
                    error=f"Timed out after {prompt.timeout}s, partial output captured",
                )
            return AgentRawResult(success=False, provider=self.provider, error=f"Timeout after {prompt.timeout}s")
        except Exception as exc:  # pragma: no cover - defensive path
            partial = Path(output_path).read_text() if Path(output_path).exists() else ""
            return AgentRawResult(success=False, provider=self.provider, output_text=partial, error=str(exc))
        finally:
            try:
                if Path(output_path).exists():
                    os.unlink(output_path)
            except Exception:
                pass


class CopilotAdapter(AgentAdapter):
    """GitHub Copilot CLI adapter.

    Uses the ``copilot`` standalone CLI (GitHub Copilot CLI, not ``gh copilot``).
    The model defaults to ``claude-sonnet-4.6`` but can be overridden via the
    ``COPILOT_MODEL`` environment variable (e.g. ``gpt-5.2``, ``claude-opus-4.6``).

    Install: https://github.com/github/copilot-cli
    Auth: relies on credentials stored by ``copilot login`` in the system keychain.
    Do NOT inject COPILOT_GITHUB_TOKEN / GH_TOKEN — those override keychain lookup
    and will fail the subscription benefit check with a 402.

    Binary resolution order:
    1. ``COPILOT_BIN`` env var (explicit override)
    2. ``~/.local/bin/copilot`` (standalone CLI, preferred)
    3. ``shutil.which("copilot")`` (PATH fallback, skipped if it is the VS Code shim)
    """

    provider = "copilot"
    _DEFAULT_MODEL = "claude-sonnet-4.6"
    # VS Code copilot-chat extension ships a shell shim — avoid it.
    _VSCODE_SHIM_MARKER = "copilot-chat"

    @classmethod
    def _find_bin(cls) -> str | None:
        """Return the path to the standalone copilot binary, avoiding the VS Code shim."""
        # 1. Explicit override
        override = os.environ.get("COPILOT_BIN", "").strip()
        if override and Path(override).is_file():
            return override

        # 2. Prefer the standalone install location
        standalone = Path.home() / ".local" / "bin" / "copilot"
        if standalone.is_file():
            return str(standalone)

        # 3. PATH fallback — skip if it resolves to the VS Code shim
        found = shutil.which("copilot")
        if found and cls._VSCODE_SHIM_MARKER not in found:
            return found

        return None

    def is_available(self) -> bool:
        return self._find_bin() is not None

    def run(self, prompt: PromptSpec, cwd: Path) -> AgentRawResult:
        bin_path = self._find_bin()
        if not bin_path:
            return AgentRawResult(
                success=False,
                provider=self.provider,
                error="copilot CLI not found — install from https://github.com/github/copilot-cli or set COPILOT_BIN",
            )

        env = os.environ.copy()
        # Remove any token env vars that would override the keychain credentials
        # and cause 402 "unable to verify membership benefits" errors.
        for key in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
            env.pop(key, None)

        env["COPILOT_ALLOW_ALL"] = "true"
        model = env.get("COPILOT_MODEL", self._DEFAULT_MODEL)
        env["COPILOT_MODEL"] = model

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as output_file:
            output_path = output_file.name

        try:
            with open(output_path, "w") as out_f:
                result = subprocess.run(
                    [
                        bin_path,
                        "--model", model,
                        "--prompt", prompt.text,
                        "--silent",
                        "--no-color",
                        "--no-ask-user",
                        "--disable-builtin-mcps",
                    ],
                    stdout=out_f,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(cwd),
                    timeout=prompt.timeout,
                    env=env,
                )

            output_text = Path(output_path).read_text() if Path(output_path).exists() else ""
            if result.returncode == 0:
                return AgentRawResult(success=True, provider=self.provider, output_text=output_text)

            if output_text and len(output_text) > 120:
                return AgentRawResult(
                    success=True,
                    provider=self.provider,
                    output_text=output_text,
                    error=f"Agent exited non-zero ({result.returncode}) but output captured",
                )

            return AgentRawResult(
                success=False,
                provider=self.provider,
                output_text=output_text,
                error=f"Exit code {result.returncode}: {result.stderr}",
            )
        except subprocess.TimeoutExpired:
            partial = Path(output_path).read_text() if Path(output_path).exists() else ""
            if partial and len(partial) > 120:
                return AgentRawResult(
                    success=True,
                    provider=self.provider,
                    output_text=partial,
                    error=f"Timed out after {prompt.timeout}s, partial output captured",
                )
            return AgentRawResult(success=False, provider=self.provider, error=f"Timeout after {prompt.timeout}s")
        except Exception as exc:
            partial = Path(output_path).read_text() if Path(output_path).exists() else ""
            return AgentRawResult(success=False, provider=self.provider, output_text=partial, error=str(exc))
        finally:
            try:
                if Path(output_path).exists():
                    os.unlink(output_path)
            except Exception:
                pass


def _adapter_from_env() -> AgentAdapter:
    """Resolve the adapter from AGENT_PROVIDER env var or env files, defaulting to Kimi."""
    # Shell env takes precedence
    provider = os.environ.get("AGENT_PROVIDER", "").lower().strip()

    if not provider:
        # Fall back to env files (automation/.env etc.) via EnvResolver
        try:
            from .env_resolver import EnvResolver
            env = EnvResolver(repo_root=Path.cwd()).build_env()
            provider = env.get("AGENT_PROVIDER", "kimi").lower().strip()
        except Exception:
            provider = "kimi"

    if provider == "copilot":
        return CopilotAdapter()
    return KimiAdapter()


class AgentRuntime:
    """Agent runtime that persists raw output artifacts."""

    def __init__(self, adapter: AgentAdapter | None = None):
        self.adapter = adapter if adapter is not None else _adapter_from_env()

    def run(self, step_id: str, prompt: PromptSpec, context: ExecutionContext) -> AgentRawResult:
        """Run agent prompt and persist raw output under task results."""
        raw_result = self.adapter.run(prompt, cwd=context.repo_root)

        if context.task_results_dir and context.task_id:
            raw_dir = context.task_results_dir / context.task_id / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            output_file = raw_dir / prompt.output_filename
            output_file.write_text(raw_result.output_text or "")
            raw_result.output_path = str(output_file)

        return raw_result
