"""Agent runtime with Kimi as the primary adapter."""
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


class AgentRuntime:
    """Agent runtime that persists raw output artifacts."""

    def __init__(self, adapter: AgentAdapter | None = None):
        self.adapter = adapter or KimiAdapter()

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
