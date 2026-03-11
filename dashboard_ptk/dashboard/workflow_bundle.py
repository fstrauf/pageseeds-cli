"""Internal workflow bundle contract used to separate core/TUI/workflows."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .config import AUTONOMY_MODE_MAP, EXECUTION_MODE_MAP


RunnerBuilder = Callable[[Any, Any, Any], dict[str, Any]]
HandlerBuilder = Callable[[], list[Any]]


@dataclass(frozen=True)
class WorkflowBundle:
    """Workflow wiring contract (internal during v0.x)."""

    name: str
    required_clis: tuple[str, ...] = field(default_factory=tuple)
    check_reddit_auth: bool = False
    execution_mode_map: dict[str, str] = field(default_factory=dict)
    autonomy_mode_map: dict[str, str] = field(default_factory=dict)
    runner_builder: RunnerBuilder | None = None
    handler_builder: HandlerBuilder | None = None

    def build_runners(self, task_list, project, session) -> dict[str, Any]:
        if self.runner_builder is None:
            return {}
        return self.runner_builder(task_list, project, session)

    def build_handlers(self) -> list[Any]:
        if self.handler_builder is None:
            return []
        return self.handler_builder()


def legacy_seo_reddit_bundle() -> WorkflowBundle:
    """Legacy dashboard behavior packaged as a workflow bundle."""
    from .engine.workflows import default_workflow_handlers
    from .tasks import build_runner_registry

    return WorkflowBundle(
        name="seo_reddit",
        required_clis=("automation-cli", "seo-cli", "seo-content-cli"),
        check_reddit_auth=True,
        execution_mode_map=dict(EXECUTION_MODE_MAP),
        autonomy_mode_map=dict(AUTONOMY_MODE_MAP),
        runner_builder=build_runner_registry,
        handler_builder=default_workflow_handlers,
    )


def scheduler_default_bundle() -> WorkflowBundle:
    """Default bundle for scheduler/status flows without task runner imports."""
    return WorkflowBundle(
        name="seo_reddit_scheduler_default",
        required_clis=("automation-cli", "seo-cli", "seo-content-cli"),
        check_reddit_auth=True,
        execution_mode_map=dict(EXECUTION_MODE_MAP),
        autonomy_mode_map=dict(AUTONOMY_MODE_MAP),
    )
