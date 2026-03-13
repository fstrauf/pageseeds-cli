"""Workflow handlers for execution engine."""

from .base import RuntimeServices, WorkflowHandler
from .handlers import (
    CollectionWorkflowHandler,
    ContentWorkflowHandler,
    ImplementationWorkflowHandler,
    InvestigationWorkflowHandler,
    ManualFallbackHandler,
    PerformanceWorkflowHandler,
    RedditWorkflowHandler,
    ResearchWorkflowHandler,
)


def default_workflow_handlers() -> list[WorkflowHandler]:
    """Return handlers in priority order."""
    return [
        CollectionWorkflowHandler(),
        InvestigationWorkflowHandler(),
        ResearchWorkflowHandler(),
        ContentWorkflowHandler(),
        RedditWorkflowHandler(),
        PerformanceWorkflowHandler(),
        ImplementationWorkflowHandler(),
        ManualFallbackHandler(),
    ]


__all__ = [
    "RuntimeServices",
    "WorkflowHandler",
    "default_workflow_handlers",
]
