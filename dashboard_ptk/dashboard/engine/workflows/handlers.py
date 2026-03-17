"""Workflow handlers with explicit step graphs for all task families."""
from __future__ import annotations

from typing import Any

from ..types import StepResult, WorkflowStep
from .base import RuntimeServices, WorkflowHandler


class _RunnerWorkflowHandler(WorkflowHandler):
    """Base handler for legacy runner-backed workflows."""

    runner_key: str = ""
    supported_types: set[str] = set()
    supported_prefixes: tuple[str, ...] = tuple()
    supported_phases: tuple[str, ...] = tuple()

    def supports(self, task: Any) -> bool:
        task_type = getattr(task, "type", "")
        task_phase = getattr(task, "phase", "")
        if task_type in self.supported_types:
            return True
        if any(task_type.startswith(prefix) for prefix in self.supported_prefixes):
            return True
        if task_phase in self.supported_phases:
            return True
        return False

    def plan(self, task: Any) -> list[WorkflowStep]:
        return [
            WorkflowStep(
                name=f"{self.runner_key}_execute",
                kind="workflow",
                handler="legacy_runner",
                params={"runner_key": self.runner_key},
            )
        ]

    def execute(self, step: WorkflowStep, task: Any, services: RuntimeServices) -> StepResult:
        runner_key = step.params.get("runner_key", self.runner_key)
        runner = services.runners.get(runner_key)
        if not runner:
            return StepResult(success=False, message=f"Runner not available: {runner_key}")

        if hasattr(runner, "set_active_task"):
            runner.set_active_task(task)
        success = runner.run(task)
        raw_result = None
        if hasattr(runner, "get_last_agent_result"):
            raw_result = runner.get_last_agent_result()
        
        # Capture error message if runner failed
        error_message = None
        if not success and hasattr(runner, "get_last_error"):
            error_message = runner.get_last_error()
        
        return StepResult(
            success=bool(success),
            message=error_message or f"Runner executed: {runner_key}",
            data={"agent_raw": raw_result} if raw_result else {},
        )


class CollectionWorkflowHandler(_RunnerWorkflowHandler):
    runner_key = "collection"
    supported_types = {"collect_gsc", "collect_posthog"}
    supported_phases = ("collection",)


class InvestigationWorkflowHandler(_RunnerWorkflowHandler):
    runner_key = "investigation"
    supported_types = {"investigate_gsc", "investigate_posthog"}
    supported_phases = ("investigation",)


class ResearchWorkflowHandler(_RunnerWorkflowHandler):
    runner_key = "research"
    supported_types = {"research_keywords", "custom_keyword_research", "research_landing_pages"}

    def plan(self, task: Any) -> list[WorkflowStep]:
        steps = [
            WorkflowStep(
                name="research_agent_stage",
                kind="agentic",
                handler="legacy_runner",
                params={"runner_key": self.runner_key},
            )
        ]

        if getattr(task, "type", "") == "custom_keyword_research":
            steps.append(
                WorkflowStep(
                    name="research_normalize_stage",
                    kind="deterministic",
                    handler="normalizer",
                    params={"normalizer_id": "keyword_research", "artifact_name": "keyword_research"},
                )
            )

        return steps


class ContentWorkflowHandler(_RunnerWorkflowHandler):
    runner_key = "content"
    supported_types = {"write_article", "optimize_article", "create_content", "optimize_content"}

    def plan(self, task: Any) -> list[WorkflowStep]:
        return [
            WorkflowStep(
                name="content_deterministic_setup",
                kind="deterministic",
                handler="legacy_runner",
                params={"runner_key": self.runner_key},
            )
        ]


class ImplementationWorkflowHandler(_RunnerWorkflowHandler):
    runner_key = "implementation"
    supported_types = {
        "cluster_and_link",
        "content_cleanup",
        "publish_content",
        "indexing_diagnostics",
        "content_strategy",
        "technical_fix",
        "landing_page_spec",
    }
    supported_prefixes = ("fix_",)
    supported_phases = ("implementation",)


class RedditWorkflowHandler(_RunnerWorkflowHandler):
    runner_key = "reddit"
    supported_prefixes = ("reddit_",)

    def plan(self, task: Any) -> list[WorkflowStep]:
        steps = [
            WorkflowStep(
                name="reddit_agent_stage",
                kind="agentic",
                handler="legacy_runner",
                params={"runner_key": self.runner_key},
            )
        ]
        if getattr(task, "type", "") == "reddit_opportunity_search":
            steps.append(
                WorkflowStep(
                    name="reddit_normalize_stage",
                    kind="deterministic",
                    handler="normalizer",
                    params={"normalizer_id": "reddit_opportunities", "artifact_name": "reddit_opportunities"},
                    optional=True,
                )
            )
        return steps


class PerformanceWorkflowHandler(_RunnerWorkflowHandler):
    runner_key = "performance"
    supported_types = {"analyze_gsc_performance"}


class ManualFallbackHandler(_RunnerWorkflowHandler):
    runner_key = "implementation"

    def supports(self, task: Any) -> bool:
        return True
