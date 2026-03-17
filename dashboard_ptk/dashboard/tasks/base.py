"""Base task runner with centralized tool and agent runtimes."""
from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from rich.console import Console

from ..engine import AgentRawResult, AgentRuntime, PromptSpec, ToolRegistry
from ..engine.executor import execution_context_for
from ..models import Project, Task
from ..storage import TaskList

console = Console()


class TaskRunner(ABC):
    """Base class for task runners."""

    def __init__(self, task_list: TaskList, project: Project, session: PromptSession):
        self.task_list = task_list
        self.project = project
        self.session = session
        self.tool_registry = ToolRegistry()
        self.agent_runtime = AgentRuntime()
        self._active_task: Task | None = None
        self._last_agent_result: AgentRawResult | None = None
        self._execution_context: dict = {}
        self._last_error: str | None = None  # Batch-specific settings (e.g., default actions)

    def set_active_task(self, task: Task | None) -> None:
        """Set task context for runtime artifacts."""
        self._active_task = task
    
    def set_execution_context(self, context: dict) -> None:
        """Set batch execution context for automated processing.
        
        Args:
            context: Dict with task-type defaults, e.g.:
                {"reddit_reply": {"action": "copy_and_mark"}}
        """
        self._execution_context = context or {}
    
    def get_execution_context(self) -> dict:
        """Get current execution context."""
        return self._execution_context

    def is_non_interactive(self) -> bool:
        """Return True when runner should avoid interactive prompts."""
        return bool(self._execution_context.get("non_interactive"))

    def auto_confirm_enabled(self) -> bool:
        """Return True when yes/no confirmations should default to yes."""
        if "auto_confirm" in self._execution_context:
            return bool(self._execution_context.get("auto_confirm"))
        return self.is_non_interactive()

    def get_last_agent_result(self) -> AgentRawResult | None:
        """Expose last agent result for executor normalizers."""
        return self._last_agent_result
    
    def get_last_error(self) -> str | None:
        """Expose last error message for debugging."""
        return self._last_error
    
    def _set_error(self, message: str) -> None:
        """Set error message and log to console."""
        self._last_error = message
        console.print(f"[red]✗ {message}[/red]")

    def validate_articles_json(self) -> tuple[bool, list[dict]]:
        """Validate articles.json alignment with post files."""
        from ..utils import ArticleManager

        article_mgr = ArticleManager(self.project.website_id)
        repo_root = Path(self.project.repo_root)
        mismatches = article_mgr.check_slug_alignment(repo_root)

        if mismatches:
            console.print("\n[bold red]⚠️  CRITICAL: articles.json is out of sync[/bold red]")
            console.print(f"[red]{len(mismatches)} articles have url_slug/filename mismatches.[/red]")
            console.print("\n[yellow]This will cause 0% GSC article mapping and break downstream tasks.[/yellow]")
            console.print("\n[dim]Examples:[/dim]")
            for mismatch in mismatches[:3]:
                console.print(f"  ID {mismatch['id']}: url_slug='{mismatch['url_slug']}'")
                console.print(f"         file='{mismatch['filename']}'")
            if len(mismatches) > 3:
                console.print(f"  ... and {len(mismatches) - 3} more")

            console.print("\n[bold]Fix:[/bold] Update url_slug fields in articles.json to match filenames.")
            console.print("[dim]Run 'v. Verify Setup' for full details.[/dim]")
            return False, mismatches

        return True, []

    def _build_context(self, task_id: str | None = None):
        return execution_context_for(self.task_list, self.project, task_id=task_id)

    def run_kimi_agent(self, prompt: str, cwd: Path = None, timeout: int = 600, mode: str = "agent") -> tuple[bool, str]:
        """Run agent via central AgentRuntime and persist raw output artifacts.

        mode='text'  — agent produces plain text only; disables file/shell tools (faster).
        mode='agent' — agent has full tool access (read/write files, run commands).
        """
        task_id = self._active_task.id if self._active_task else None
        context = self._build_context(task_id=task_id)

        if cwd is not None:
            context.repo_root = Path(cwd)

        raw = self.agent_runtime.run(
            step_id="legacy_runner_agent_call",
            prompt=PromptSpec(text=prompt, timeout=timeout, mode=mode),
            context=context,
        )
        self._last_agent_result = raw

        if self._active_task and raw.output_path:
            self._active_task.metadata.setdefault("agent_raw_paths", [])
            if raw.output_path not in self._active_task.metadata["agent_raw_paths"]:
                self._active_task.metadata["agent_raw_paths"].append(raw.output_path)

        return raw.success, raw.output_text or (raw.error or "")

    def run_cli_command(
        self,
        cmd: list,
        cwd: Path = None,
        timeout: int = 300,
        env_overrides: dict = None,
    ) -> tuple[bool, str, str]:
        """Run deterministic commands via central ToolRegistry."""
        task_id = self._active_task.id if self._active_task else None
        context = self._build_context(task_id=task_id)
        if cwd is not None:
            context.repo_root = Path(cwd)

        result = self.tool_registry.run_command(
            command=[str(item) for item in cmd],
            context=context,
            timeout=timeout,
            env_overrides=env_overrides,
        )

        return result.success, result.stdout, result.stderr
