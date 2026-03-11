"""Execution engine that routes tasks through explicit workflow handlers."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .normalizers import NormalizerRegistry
from .types import AgentRawResult, ExecutionContext, StepResult
from .workflows import RuntimeServices, default_workflow_handlers


class ExecutionEngine:
    """Coordinates workflow planning and execution for dashboard tasks."""

    def __init__(self, task_list, project, runners: dict[str, Any], handlers: list[Any] | None = None):
        self.task_list = task_list
        self.project = project
        self.runners = runners
        self.handlers = handlers or default_workflow_handlers()
        self.normalizers = NormalizerRegistry()

    def _find_handler(self, task: Any):
        for handler in self.handlers:
            if handler.supports(task):
                return handler
        return None

    def execute_task(self, task: Any) -> tuple[bool, str]:
        """Execute a task through a planned step graph.
        
        Returns:
            Tuple of (success: bool, error_message: str)
        """
        task.started_at = datetime.now().isoformat()
        if task.status == "todo":
            task.status = "in_progress"
            self.task_list.save()

        handler = self._find_handler(task)
        if not handler:
            error_msg = f"No workflow handler found for task type: {getattr(task, 'type', 'unknown')}"
            task.notes = error_msg
            self.task_list.save()
            return False, error_msg

        steps = handler.plan(task)
        services = RuntimeServices(runners=self.runners)
        latest_raw: AgentRawResult | None = None
        all_success = True
        last_error = ""

        for step in steps:
            if step.handler == "normalizer":
                if not latest_raw:
                    error_msg = f"Normalization skipped for step '{step.name}': no agent raw output available"
                    task.notes = error_msg
                    self.task_list.save()
                    return False, error_msg

                norm_context = {
                    "task_results_dir": str(self.task_list.task_results_dir),
                    "task_id": task.id,
                    "artifact_name": step.params.get("artifact_name", step.name),
                }
                norm = self.normalizers.normalize(step.params.get("normalizer_id", "passthrough_markdown"), latest_raw, norm_context)
                if not norm.success:
                    error_msg = f"Normalization failed ({step.name}): {norm.error}"
                    task.notes = error_msg
                    self.task_list.save()
                    return False, error_msg

                # Attach normalized artifact reference for downstream use.
                artifacts = getattr(task, "artifacts", None)
                if isinstance(artifacts, list):
                    artifacts.append(
                        {
                            "key": step.params.get("artifact_name", step.name),
                            "path": norm.output_path,
                            "type": "json",
                            "source": "normalizer",
                        }
                    )
                continue

            result = handler.execute(step, task, services)
            all_success = all_success and result.success
            
            # Capture error message from step result
            if not result.success and result.message:
                last_error = result.message

            raw = result.data.get("agent_raw") if isinstance(result.data, dict) else None
            if isinstance(raw, AgentRawResult):
                latest_raw = raw

            if not result.success:
                break

        self.task_list.save()
        
        # Return specific error message or generic one
        if not all_success:
            error_msg = last_error or "Task execution failed"
            task.notes = error_msg
            self.task_list.save()
            return False, error_msg
        
        return True, ""


def execution_context_for(task_list, project, task_id: str | None = None) -> ExecutionContext:
    """Create execution context for tool/agent calls."""
    return ExecutionContext(
        repo_root=Path(project.repo_root),
        task_id=task_id,
        task_results_dir=Path(task_list.task_results_dir),
    )
